import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DOCS_PATH = resolve(__dirname, "../TripleTexAPI.md");

let docsContent: string | null = null;
let endpointIndex: EndpointEntry[] = [];
let schemaIndex: SchemaEntry[] = [];

interface EndpointEntry {
  method: string;
  path: string;
  category: string;
  summary: string;
  lineStart: number;
  lineEnd: number;
}

interface SchemaEntry {
  name: string;
  lineStart: number;
  lineEnd: number;
}

function loadDocs(): string {
  if (!docsContent) {
    docsContent = readFileSync(DOCS_PATH, "utf-8");
    buildIndex();
  }
  return docsContent;
}

function buildIndex() {
  const lines = docsContent!.split("\n");
  let currentCategory = "";

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Match category headers: ### category (N endpoints)
    const catMatch = line.match(/^### (.+?) \(\d+ endpoints?\)/);
    if (catMatch) {
      currentCategory = catMatch[1];
      continue;
    }

    // Match endpoint entries: #### `METHOD /path`
    const endpointMatch = line.match(/^#### `(GET|POST|PUT|DELETE|PATCH) (.+?)`/);
    if (endpointMatch) {
      const method = endpointMatch[1];
      const path = endpointMatch[2];
      // Find summary on next lines
      let summary = "";
      for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
        const sumMatch = lines[j].match(/^\*\*Summary:\*\* (.+)/);
        if (sumMatch) {
          summary = sumMatch[1];
          break;
        }
      }
      // Find end of this endpoint section (next #### or ### or ---)
      let lineEnd = i + 1;
      for (let j = i + 1; j < lines.length; j++) {
        if (lines[j].match(/^#{3,4} /) || lines[j] === "---") {
          lineEnd = j;
          break;
        }
        lineEnd = j;
      }
      endpointIndex.push({ method, path, category: currentCategory, summary, lineStart: i, lineEnd });
      continue;
    }

    // Match schema definitions: ### `ModelName`
    const schemaMatch = line.match(/^### `(.+?)`$/);
    if (schemaMatch) {
      const name = schemaMatch[1];
      let lineEnd = i + 1;
      for (let j = i + 1; j < lines.length; j++) {
        if (lines[j].match(/^### `/) || lines[j].match(/^## /)) {
          lineEnd = j;
          break;
        }
        lineEnd = j;
      }
      schemaIndex.push({ name, lineStart: i, lineEnd });
    }
  }
}

function getLines(start: number, end: number): string {
  const lines = docsContent!.split("\n");
  return lines.slice(start, end).join("\n");
}

export function handleApiDocsQuery(input: {
  action: string;
  query?: string;
  method?: string;
  path?: string;
  schema?: string;
  category?: string;
}): unknown {
  loadDocs();

  switch (input.action) {
    case "list_categories": {
      const categories = new Map<string, number>();
      for (const ep of endpointIndex) {
        categories.set(ep.category, (categories.get(ep.category) || 0) + 1);
      }
      return {
        totalEndpoints: endpointIndex.length,
        totalSchemas: schemaIndex.length,
        categories: Array.from(categories.entries()).map(([name, count]) => ({ name, count })),
      };
    }

    case "list_endpoints": {
      let results = endpointIndex;
      if (input.category) {
        const cat = input.category.toLowerCase();
        results = results.filter((e) => e.category.toLowerCase().includes(cat));
      }
      if (input.method) {
        results = results.filter((e) => e.method === input.method.toUpperCase());
      }
      if (input.query) {
        const q = input.query.toLowerCase();
        results = results.filter(
          (e) => e.path.toLowerCase().includes(q) || e.summary.toLowerCase().includes(q) || e.category.toLowerCase().includes(q)
        );
      }
      return {
        count: results.length,
        endpoints: results.slice(0, 50).map((e) => ({
          method: e.method,
          path: e.path,
          category: e.category,
          summary: e.summary,
        })),
      };
    }

    case "get_endpoint": {
      if (!input.path) return { error: true, message: "path is required" };
      const pathLower = input.path.toLowerCase();
      const method = input.method?.toUpperCase();
      const match = endpointIndex.find((e) => {
        const pathMatch = e.path.toLowerCase() === pathLower ||
          e.path.toLowerCase().replace(/\{[^}]+\}/g, "{id}") === pathLower.replace(/\{[^}]+\}/g, "{id}");
        return pathMatch && (!method || e.method === method);
      });
      if (!match) {
        // Try fuzzy match
        const fuzzy = endpointIndex.filter((e) =>
          e.path.toLowerCase().includes(pathLower) && (!method || e.method === method)
        );
        if (fuzzy.length > 0) {
          return {
            exactMatch: false,
            suggestions: fuzzy.slice(0, 10).map((e) => ({ method: e.method, path: e.path, summary: e.summary })),
          };
        }
        return { error: true, message: `Endpoint not found: ${input.method || ""} ${input.path}` };
      }
      return {
        method: match.method,
        path: match.path,
        category: match.category,
        summary: match.summary,
        documentation: getLines(match.lineStart, match.lineEnd),
      };
    }

    case "get_schema": {
      if (!input.schema) return { error: true, message: "schema name is required" };
      const schemaLower = input.schema.toLowerCase();
      const match = schemaIndex.find((s) => s.name.toLowerCase() === schemaLower);
      if (!match) {
        const fuzzy = schemaIndex.filter((s) => s.name.toLowerCase().includes(schemaLower));
        if (fuzzy.length > 0) {
          return {
            exactMatch: false,
            suggestions: fuzzy.slice(0, 20).map((s) => s.name),
          };
        }
        return { error: true, message: `Schema not found: ${input.schema}` };
      }
      return {
        name: match.name,
        documentation: getLines(match.lineStart, match.lineEnd),
      };
    }

    case "search": {
      if (!input.query) return { error: true, message: "query is required" };
      const q = input.query.toLowerCase();
      const lines = docsContent!.split("\n");
      const matches: { line: number; text: string; context: string }[] = [];
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].toLowerCase().includes(q)) {
          const contextStart = Math.max(0, i - 2);
          const contextEnd = Math.min(lines.length, i + 3);
          matches.push({
            line: i + 1,
            text: lines[i].trim(),
            context: lines.slice(contextStart, contextEnd).join("\n"),
          });
          if (matches.length >= 20) break;
        }
      }
      return { query: input.query, matchCount: matches.length, matches };
    }

    default:
      return { error: true, message: `Unknown action: ${input.action}. Use: list_categories, list_endpoints, get_endpoint, get_schema, search` };
  }
}
