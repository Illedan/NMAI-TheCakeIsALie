import { z, type ZodTypeAny } from "zod";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

interface OpenApiSpec {
  paths: Record<string, Record<string, OpenApiOperation>>;
  components: { schemas: Record<string, OpenApiSchema> };
}

interface OpenApiOperation {
  parameters?: OpenApiParameter[];
  requestBody?: {
    required?: boolean;
    content: Record<string, { schema: OpenApiSchema }>;
  };
}

interface OpenApiParameter {
  name: string;
  in: "query" | "path" | "header" | "cookie";
  required?: boolean;
  schema: OpenApiSchema;
  description?: string;
}

interface OpenApiSchema {
  $ref?: string;
  type?: string;
  format?: string;
  enum?: string[];
  properties?: Record<string, OpenApiSchema>;
  required?: string[];
  items?: OpenApiSchema;
  readOnly?: boolean;
  description?: string;
  additionalProperties?: boolean | OpenApiSchema;
}

let spec: OpenApiSpec | null = null;
const zodCache = new Map<string, ZodTypeAny>();

function loadSpec(): OpenApiSpec {
  if (!spec) {
    const specPath = resolve(__dirname, "openapi.json");
    spec = JSON.parse(readFileSync(specPath, "utf-8")) as OpenApiSpec;
  }
  return spec;
}

function resolveRef(schema: OpenApiSchema): OpenApiSchema {
  if (schema.$ref) {
    const refPath = schema.$ref.replace("#/", "").split("/");
    let current: any = loadSpec();
    for (const part of refPath) {
      current = current[part];
    }
    return current as OpenApiSchema;
  }
  return schema;
}

/**
 * Convert an OpenAPI schema to a Zod schema for runtime validation.
 * Uses a depth limit to avoid infinite recursion on circular refs.
 */
function toZod(schema: OpenApiSchema, depth = 0): ZodTypeAny {
  if (depth > 4) return z.any();

  const resolved = resolveRef(schema);

  // Check cache for named schemas
  if (schema.$ref) {
    const refName = schema.$ref.split("/").pop()!;
    const cacheKey = `${refName}:${depth}`;
    const cached = zodCache.get(cacheKey);
    if (cached) return cached;
  }

  let result: ZodTypeAny;

  switch (resolved.type) {
    case "string":
      if (resolved.enum) {
        result = z.enum(resolved.enum as [string, ...string[]]);
      } else {
        result = z.string();
      }
      break;

    case "integer":
    case "number":
      result = z.number();
      break;

    case "boolean":
      result = z.boolean();
      break;

    case "array":
      result = z.array(resolved.items ? toZod(resolved.items, depth + 1) : z.any());
      break;

    case "object":
    default:
      if (resolved.properties) {
        const shape: Record<string, ZodTypeAny> = {};
        const requiredFields = new Set(resolved.required || []);

        for (const [key, propSchema] of Object.entries(resolved.properties)) {
          const propResolved = resolveRef(propSchema);
          // Skip read-only fields — LLM should not send them
          if (propResolved.readOnly) continue;

          let fieldSchema = toZod(propSchema, depth + 1);
          if (!requiredFields.has(key)) {
            fieldSchema = fieldSchema.optional();
          }
          shape[key] = fieldSchema;
        }

        // Use passthrough to allow extra fields (API may accept fields not in schema)
        result = z.object(shape).passthrough();
      } else {
        result = z.any();
      }
      break;
  }

  if (schema.$ref) {
    const refName = schema.$ref.split("/").pop()!;
    zodCache.set(`${refName}:${depth}`, result);
  }

  return result;
}

/**
 * Find the OpenAPI operation for a given method + path.
 * Handles path params like /employee/{id} matching /employee/123.
 */
function findOperation(method: string, path: string): {
  operation: OpenApiOperation;
  specPath: string;
} | null {
  if (!method || !path) return null;
  const s = loadSpec();
  const lowerMethod = method.toLowerCase();

  // Try exact match first
  if (s.paths[path]?.[lowerMethod]) {
    return { operation: s.paths[path][lowerMethod], specPath: path };
  }

  // Try template matching: /employee/123 -> /employee/{id}
  const pathParts = path.split("/");
  for (const [specPath, methods] of Object.entries(s.paths)) {
    if (!methods[lowerMethod]) continue;
    const specParts = specPath.split("/");
    if (specParts.length !== pathParts.length) continue;

    let match = true;
    for (let i = 0; i < specParts.length; i++) {
      if (specParts[i].startsWith("{") && specParts[i].endsWith("}")) continue;
      if (specParts[i] !== pathParts[i]) { match = false; break; }
    }
    if (match) return { operation: methods[lowerMethod], specPath };
  }

  return null;
}

/**
 * Get allowed query parameter names for a given endpoint.
 */
function getAllowedQueryParams(operation: OpenApiOperation): Map<string, OpenApiParameter> {
  const params = new Map<string, OpenApiParameter>();
  for (const p of operation.parameters || []) {
    if (p.in === "query") {
      params.set(p.name, p);
    }
  }
  return params;
}

export interface ValidationError {
  type: "invalid_body" | "invalid_params" | "unknown_endpoint" | "unknown_params";
  message: string;
  details: string[];
  hint?: string;
}

/**
 * Validate an API call against the OpenAPI spec.
 * Returns null if valid, or a ValidationError with actionable feedback for the LLM.
 */
export function validateApiCall(
  method: string,
  path: string,
  params?: Record<string, unknown>,
  body?: unknown,
): ValidationError | null {
  const found = findOperation(method, path);

  if (!found) {
    // Find close matches for better error messages
    const s = loadSpec();
    const suggestions: string[] = [];
    const pathBase = path.split("/").slice(0, 2).join("/");
    for (const specPath of Object.keys(s.paths)) {
      if (specPath.startsWith(pathBase)) {
        const methods = Object.keys(s.paths[specPath]).filter(m => m !== "parameters");
        suggestions.push(`${methods.map(m => m.toUpperCase()).join("|")} ${specPath}`);
      }
    }
    return {
      type: "unknown_endpoint",
      message: `No endpoint found for ${method} ${path}`,
      details: suggestions.length > 0
        ? [`Did you mean one of: ${suggestions.slice(0, 5).join(", ")}?`]
        : [`Path "${path}" does not exist in the API spec.`],
    };
  }

  const { operation, specPath } = found;
  const errors: string[] = [];

  // Validate query params
  if (params && Object.keys(params).length > 0) {
    const allowed = getAllowedQueryParams(operation);
    const unknownParams: string[] = [];
    for (const key of Object.keys(params)) {
      if (!allowed.has(key)) {
        unknownParams.push(key);
      }
    }
    if (unknownParams.length > 0) {
      // Warn but don't block — the spec may be incomplete and the API may accept extra params
      const allowedNames = Array.from(allowed.keys());
      console.log(`OpenAPI warning: unknown query param(s) ${unknownParams.join(", ")} for ${method} ${specPath}`);
    }

    // Validate required query params
    for (const [name, param] of allowed) {
      if (param.required && !(name in params)) {
        errors.push(`Missing required query parameter: "${name}"`);
      }
    }
  }

  // Validate request body for POST/PUT
  if (body && (method === "POST" || method === "PUT")) {
    const requestBody = operation.requestBody;
    if (!requestBody) {
      errors.push(`${method} ${specPath} does not accept a request body, but one was provided.`);
    } else {
      // Find the schema — try both content types
      const contentTypes = Object.keys(requestBody.content);
      const contentSchema = requestBody.content[contentTypes[0]]?.schema;
      if (contentSchema) {
        const zodSchema = toZod(contentSchema);
        const result = zodSchema.safeParse(body);
        if (!result.success) {
          for (const issue of result.error.issues) {
            const fieldPath = issue.path.join(".");
            if (issue.code === "invalid_value" && "values" in issue) {
              errors.push(
                `Field "${fieldPath}": ${issue.message}. Must be one of: ${(issue.values as string[]).join(", ")}`
              );
            } else if (issue.code === "invalid_type" && "expected" in issue) {
              errors.push(
                `Field "${fieldPath}": expected ${issue.expected}, got actual value`
              );
            } else {
              errors.push(`Field "${fieldPath}": ${issue.message}`);
            }
          }
        }
      }
    }
  } else if (method === "POST" || method === "PUT") {
    const requestBody = operation.requestBody;
    if (requestBody?.required && !body) {
      errors.push(`${method} ${specPath} requires a request body but none was provided.`);
    }
  }

  if (errors.length > 0) {
    return {
      type: "invalid_body",
      message: `Validation failed for ${method} ${specPath}`,
      details: errors,
    };
  }

  return null;
}

/**
 * Format a validation error into a string suitable for LLM feedback.
 */
export function formatValidationError(err: ValidationError): string {
  const lines = [`VALIDATION ERROR (${err.type}): ${err.message}`];
  for (const detail of err.details) {
    lines.push(`  - ${detail}`);
  }
  if (err.hint) {
    lines.push(`HINT: ${err.hint}`);
  }
  lines.push("Fix the issue and retry. Do NOT repeat the same mistake.");
  return lines.join("\n");
}
