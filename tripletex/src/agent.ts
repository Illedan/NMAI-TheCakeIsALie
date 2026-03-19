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

After completing all API calls, respond with DONE.`;

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
      tools: [TRIPLETEX_TOOL],
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
      const call = toolUse.input as ToolCall;
      let result: unknown;
      let isError = false;

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
