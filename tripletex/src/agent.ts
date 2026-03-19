import Anthropic from "@anthropic-ai/sdk";
import { TripletexClient, TripletexApiError } from "./tripletex-client.js";
import type { FileAttachment, ToolCall } from "./types.js";

const SYSTEM_PROMPT = `You are an expert accounting agent for Tripletex, a Norwegian accounting system.
You receive a task prompt (possibly in Norwegian, English, Spanish, Portuguese, Nynorsk, German, or French) and must execute it using the Tripletex REST API.

You have access to a tool "tripletex_api" that makes HTTP requests to the Tripletex API.

Key API patterns:
- GET /employee - list employees. POST /employee - create. PUT /employee/{id} - update.
- GET /customer - list customers. POST /customer - create. PUT /customer/{id} - update.
- GET /product - list products. POST /product - create.
- POST /order - create order. POST /invoice - create invoice from order.
- GET /department - list departments. POST /department - create.
- GET /project - list projects. POST /project - create.
- GET /travelExpense - list travel expenses. POST /travelExpense - create. DELETE /travelExpense/{id} - delete.
- GET /ledger/account - chart of accounts. GET /ledger/voucher - vouchers. POST /ledger/voucher - create voucher.
- POST /invoice/{id}/:payment - register payment on invoice.
- POST /invoice/{id}/:creditCreditNote or POST /invoice/{id}/:createCreditNote - credit notes.
- GET /company - company info. PUT /company/settings/altinn - enable modules.
- Use ?fields=* to get all fields. Use ?fields=id,name,etc for specific fields.
- POST/PUT bodies are JSON. Linked entities use {"id": number} format.
- List responses: {"values": [...], "fullResultSize": N}
- Single responses: {"value": {...}}
- Auth is handled automatically. Just specify the path starting with /.

Efficiency rules:
- Plan all steps before making calls.
- Never make unnecessary GET calls. Use IDs from POST responses directly.
- Avoid trial-and-error. Get it right the first time.
- Batch operations when the API supports /list endpoints.
- Minimize total API calls.

When creating employees, common required fields: firstName, lastName, email.
When creating customers: name, isCustomer (true).
When creating products: name, number (unique), priceExcludingVat, vatType (use GET /ledger/vatType to find correct one).
When creating invoices: first create an order with orderLines, then create invoice referencing the order.
When creating departments: name, departmentNumber.
When creating projects: name, number, projectManager (employee ref), customer (optional).

When files are attached (CSV, text, etc.), use the "query_file" tool to inspect them:
- Start with action "info" to see headers, row count, and a preview.
- Use "read_rows" to read CSV data as objects (paginated with from/count).
- Use "search" to find specific rows by value, optionally filtering by column.
- Extract the data you need from the file, then make the appropriate Tripletex API calls.

After completing all API calls, respond with DONE.`;

interface ParsedFile {
  filename: string;
  mime_type: string;
  raw: string;
  lines: string[];
  headers: string[] | null;
  rows: string[][] | null;
}

function parseFiles(files: FileAttachment[]): Map<string, ParsedFile> {
  const map = new Map<string, ParsedFile>();
  for (const file of files) {
    if (file.mime_type === "application/pdf" || file.mime_type.startsWith("image/")) continue;
    const raw = Buffer.from(file.content_base64, "base64").toString("utf-8");
    const lines = raw.split(/\r?\n/).filter((l) => l.trim() !== "");
    const isCSV =
      file.filename.endsWith(".csv") ||
      file.mime_type === "text/csv" ||
      (lines.length > 1 && lines[0].includes(";") || lines[0].includes(","));
    let headers: string[] | null = null;
    let rows: string[][] | null = null;
    if (isCSV && lines.length > 0) {
      const sep = lines[0].includes(";") ? ";" : ",";
      headers = lines[0].split(sep).map((h) => h.trim().replace(/^"|"$/g, ""));
      rows = lines.slice(1).map((l) => l.split(sep).map((c) => c.trim().replace(/^"|"$/g, "")));
    }
    map.set(file.filename, { filename: file.filename, mime_type: file.mime_type, raw, lines, headers, rows });
  }
  return map;
}

function handleFileQuery(
  fileMap: Map<string, ParsedFile>,
  input: { filename: string; action: string; from?: number; count?: number; search?: string; column?: string }
): unknown {
  const file = fileMap.get(input.filename);
  if (!file) {
    return {
      error: true,
      message: `File not found: ${input.filename}`,
      available: Array.from(fileMap.keys()),
    };
  }

  switch (input.action) {
    case "info": {
      return {
        filename: file.filename,
        mime_type: file.mime_type,
        totalLines: file.lines.length,
        isCSV: !!file.headers,
        headers: file.headers,
        totalRows: file.rows?.length ?? null,
        preview: file.lines.slice(0, 5),
      };
    }
    case "read_rows": {
      if (!file.rows || !file.headers) {
        return { error: true, message: "File is not CSV. Use read_lines instead." };
      }
      const from = input.from ?? 0;
      const count = input.count ?? 50;
      const slice = file.rows.slice(from, from + count);
      const asObjects = slice.map((row) =>
        Object.fromEntries(file.headers!.map((h, i) => [h, row[i] ?? ""]))
      );
      return { headers: file.headers, from, count: slice.length, totalRows: file.rows.length, rows: asObjects };
    }
    case "read_lines": {
      const from = input.from ?? 0;
      const count = input.count ?? 50;
      const slice = file.lines.slice(from, from + count);
      return { from, count: slice.length, totalLines: file.lines.length, lines: slice };
    }
    case "search": {
      if (!input.search) return { error: true, message: "search parameter required" };
      const query = input.search.toLowerCase();
      if (file.rows && file.headers) {
        const matches = file.rows
          .map((row, i) => ({ index: i, row: Object.fromEntries(file.headers!.map((h, j) => [h, row[j] ?? ""])) }))
          .filter(({ row }) => {
            const values = input.column ? [row[input.column] ?? ""] : Object.values(row);
            return values.some((v) => v.toLowerCase().includes(query));
          })
          .slice(0, 50);
        return { headers: file.headers, matchCount: matches.length, matches };
      } else {
        const matches = file.lines
          .map((line, i) => ({ index: i, line }))
          .filter(({ line }) => line.toLowerCase().includes(query))
          .slice(0, 50);
        return { matchCount: matches.length, matches };
      }
    }
    default:
      return { error: true, message: `Unknown action: ${input.action}. Use: info, read_rows, read_lines, search` };
  }
}

const QUERY_FILE_TOOL: Anthropic.Messages.Tool = {
  name: "query_file",
  description:
    "Query an attached file (CSV, text, etc). Use 'info' to see headers/row count, 'read_rows' to read CSV rows, 'read_lines' for raw lines, 'search' to find matching rows/lines.",
  input_schema: {
    type: "object" as const,
    properties: {
      filename: {
        type: "string",
        description: "The filename to query",
      },
      action: {
        type: "string",
        enum: ["info", "read_rows", "read_lines", "search"],
        description: "info: get file metadata and headers. read_rows: read CSV rows as objects. read_lines: read raw lines. search: find rows/lines matching a query.",
      },
      from: {
        type: "number",
        description: "Start index for read_rows/read_lines (default 0)",
      },
      count: {
        type: "number",
        description: "Number of rows/lines to return (default 50)",
      },
      search: {
        type: "string",
        description: "Search query string (for action=search)",
      },
      column: {
        type: "string",
        description: "Limit search to a specific column (for action=search on CSV files)",
      },
    },
    required: ["filename", "action"],
  },
};

const TRIPLETEX_TOOL: Anthropic.Messages.Tool = {
  name: "tripletex_api",
  description:
    "Make an HTTP request to the Tripletex API. Returns the JSON response.",
  input_schema: {
    type: "object" as const,
    properties: {
      method: {
        type: "string",
        enum: ["GET", "POST", "PUT", "DELETE"],
        description: "HTTP method",
      },
      path: {
        type: "string",
        description:
          "API path starting with /, e.g. /employee or /customer/123",
      },
      params: {
        type: "object",
        description:
          "Query parameters as key-value pairs, e.g. {fields: '*', count: 100}",
        additionalProperties: true,
      },
      body: {
        type: "object",
        description: "JSON request body for POST/PUT requests",
        additionalProperties: true,
      },
    },
    required: ["method", "path"],
  },
};

function buildUserContent(
  prompt: string,
  files: FileAttachment[]
): Anthropic.Messages.ContentBlockParam[] {
  const content: Anthropic.Messages.ContentBlockParam[] = [];

  for (const file of files) {
    if (file.mime_type === "application/pdf") {
      content.push({
        type: "document",
        source: {
          type: "base64",
          media_type: "application/pdf",
          data: file.content_base64,
        },
      });
    } else if (file.mime_type.startsWith("image/")) {
      content.push({
        type: "image",
        source: {
          type: "base64",
          media_type: file.mime_type as
            | "image/jpeg"
            | "image/png"
            | "image/gif"
            | "image/webp",
          data: file.content_base64,
        },
      });
    } else {
      content.push({
        type: "text",
        text: `Attached file: "${file.filename}" (${file.mime_type}) — use the query_file tool to read its contents.`,
      });
    }
  }

  content.push({ type: "text", text: prompt });
  return content;
}

export async function runAgent(
  client: TripletexClient,
  prompt: string,
  files: FileAttachment[]
): Promise<{ callCount: number; errorCount: number; messages: Anthropic.Messages.MessageParam[] }> {
  const anthropic = new Anthropic();
  const fileMap = parseFiles(files);
  const hasQueryableFiles = fileMap.size > 0;
  const tools = hasQueryableFiles ? [TRIPLETEX_TOOL, QUERY_FILE_TOOL] : [TRIPLETEX_TOOL];

  const messages: Anthropic.Messages.MessageParam[] = [
    { role: "user", content: buildUserContent(prompt, files) },
  ];

  let iterations = 0;
  const maxIterations = 30;

  while (iterations < maxIterations) {
    iterations++;

    const response = await anthropic.messages.create({
      model: "claude-sonnet-4-20250514",
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
      tools,
      messages,
    });

    if (response.stop_reason === "end_turn") break;

    const toolUseBlocks = response.content.filter(
      (b): b is Anthropic.Messages.ToolUseBlock => b.type === "tool_use"
    );

    if (toolUseBlocks.length === 0) break;

    messages.push({ role: "assistant", content: response.content });

    const toolResults: Anthropic.Messages.ToolResultBlockParam[] = [];

    for (const toolUse of toolUseBlocks) {
      let result: unknown;
      let isError = false;

      if (toolUse.name === "query_file") {
        result = handleFileQuery(fileMap, toolUse.input as Parameters<typeof handleFileQuery>[1]);
        isError = !!(result as Record<string, unknown>).error;
      } else {
        const call = toolUse.input as ToolCall;
        try {
          result = await client.execute(call);
        } catch (e) {
          isError = true;
          if (e instanceof TripletexApiError) {
            result = {
              error: true,
              status: e.status,
              message: e.details.message || e.message,
              developerMessage: e.details.developerMessage,
              validationMessages: e.details.validationMessages,
            };
          } else {
            result = { error: true, message: String(e) };
          }
        }
      }

      toolResults.push({
        type: "tool_result",
        tool_use_id: toolUse.id,
        content: JSON.stringify(result),
        is_error: isError,
      });
    }

    messages.push({ role: "user", content: toolResults });
  }

  return { callCount: client.callCount, errorCount: client.errorCount, messages };
}
