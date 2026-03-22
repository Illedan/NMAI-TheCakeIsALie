import type {
  TripletexCredentials,
  TripletexListResponse,
  TripletexSingleResponse,
  TripletexError,
} from "./types.js";

export interface ApiCallLog {
  timestamp: string;
  method: string;
  path: string;
  params?: Record<string, string | number | boolean>;
  body?: Record<string, unknown>;
  status: number;
  durationMs: number;
  response?: unknown;
  error?: unknown;
}

export class TripletexClient {
  private baseUrl: string;
  private authHeader: string;
  callCount = 0;
  errorCount = 0;
  apiCalls: ApiCallLog[] = [];
  bankAccountChecked = false;
  private forbiddenByPath = new Map<string, number>();
  private total403s = 0;
  private occupationCodeSearchCount = 0;

  constructor(credentials: TripletexCredentials) {
    this.baseUrl = credentials.base_url.replace(/\/$/, "");
    this.authHeader =
      "Basic " +
      Buffer.from(`0:${credentials.session_token}`).toString("base64");
  }

  private async request<T>(
    method: string,
    path: string,
    options: {
      params?: Record<string, string | number | boolean>;
      body?: Record<string, unknown>;
    } = {}
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`);
    if (options.params) {
      for (const [k, v] of Object.entries(options.params)) {
        url.searchParams.set(k, String(v));
      }
    }

    this.callCount++;
    const start = Date.now();

    const res = await fetch(url.toString(), {
      method,
      headers: {
        Authorization: this.authHeader,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      ...(options.body ? { body: JSON.stringify(options.body) } : {}),
    });

    const durationMs = Date.now() - start;

    if (!res.ok) {
      this.errorCount++;
      if (res.status === 403) {
        this.total403s++;
        this.forbiddenByPath.set(path, (this.forbiddenByPath.get(path) || 0) + 1);
      }
      const err = (await res.json().catch(() => ({}))) as TripletexError;
      this.apiCalls.push({
        timestamp: new Date().toISOString(),
        method, path,
        params: options.params,
        body: options.body,
        status: res.status,
        durationMs,
        error: err,
      });
      throw new TripletexApiError(res.status, err);
    }

    if (res.status === 204) {
      this.apiCalls.push({ timestamp: new Date().toISOString(), method, path, params: options.params, body: options.body, status: 204, durationMs });
      return undefined as T;
    }

    const json = await res.json() as T;

    // Warn if account lookup returns wrong number (fuzzy match)
    if (method === "GET" && path === "/ledger/account" && options.params?.number) {
      const requested = String(options.params.number).split(",").map(n => n.trim());
      const result = json as Record<string, unknown>;
      const values = (result as any)?.values as Array<Record<string, unknown>> | undefined;
      if (values) {
        for (const v of values) {
          const num = String(v.number || "");
          if (num && !requested.includes(num)) {
            // Inject a warning into the response so the agent sees it
            (v as any)._warning = `Account ${num} returned but ${requested.join(",")} was requested. Verify this is the correct account.`;
          }
        }
      }
    }

    this.apiCalls.push({
      timestamp: new Date().toISOString(),
      method, path,
      params: options.params,
      body: options.body,
      status: res.status,
      durationMs,
      response: json,
    });
    return json;
  }

  async get<T>(
    path: string,
    params?: Record<string, string | number | boolean>
  ): Promise<TripletexSingleResponse<T>> {
    return this.request("GET", path, { params });
  }

  async list<T>(
    path: string,
    params?: Record<string, string | number | boolean>
  ): Promise<TripletexListResponse<T>> {
    return this.request("GET", path, { params });
  }

  async post<T>(
    path: string,
    body: Record<string, unknown>,
    params?: Record<string, string | number | boolean>
  ): Promise<TripletexSingleResponse<T>> {
    return this.request("POST", path, { body, params });
  }

  async put<T>(
    path: string,
    body: Record<string, unknown>,
    params?: Record<string, string | number | boolean>
  ): Promise<TripletexSingleResponse<T>> {
    return this.request("PUT", path, { body, params });
  }

  async del(path: string): Promise<void> {
    return this.request("DELETE", path);
  }

  async execute(call: {
    method: string;
    path: string;
    params?: Record<string, string | number | boolean>;
    body?: Record<string, unknown> | unknown[] | string;
  }): Promise<unknown> {
    let body = call.body;
    // Handle stringified JSON bodies (LLM sometimes sends arrays as strings)
    if (typeof body === "string") {
      try { body = JSON.parse(body); } catch { /* keep as-is */ }
    }
    // Basic path validation
    if (!call.path || typeof call.path !== "string" || !call.path.startsWith("/")) {
      return { error: true, message: "BLOCKED: API path must start with '/'." };
    }
    // Reject query strings embedded in path
    if (call.path.includes("?")) {
      return { error: true, message: "BLOCKED: Do not put query strings inside path. Use params field." };
    }
    // 403 circuit breaker — stop retrying after permission failures
    if ((this.forbiddenByPath.get(call.path) || 0) >= 1) {
      return { error: true, message: `BLOCKED: ${call.path} already returned 403 in this run. Do not retry.` };
    }
    if (this.total403s >= 3) {
      return { error: true, message: "BLOCKED: repeated 403 permission errors. Stop retrying — the proxy token may be expired." };
    }
    // Block POST/PUT with null/empty body — return error without hitting API
    if ((call.method === "POST" || call.method === "PUT") && !body && !["/invoice"].includes(call.path) && !call.path?.includes("/:")) {
      return { error: true, message: `${call.method} ${call.path} requires a request body. Send fields in the JSON body, not as query params.` };
    }
    // Block known failing batch endpoints
    if (call.method === "POST" && (call.path === "/ledger/account/list" || call.path === "/product/list")) {
      return { error: true, message: `POST ${call.path} is not supported. Create items individually.` };
    }
    // Auto-fix known bad paths
    if (call.path === "/travelExpense/rateType") call.path = "/travelExpense/rateCategory";
    if (call.path === "/supplierInvoice/paymentType") call.path = "/invoice/paymentType";
    if (call.method === "POST" && call.path === "/project/projectActivity/list") {
      return { error: true, message: "BLOCKED: POST /project/projectActivity/list does not exist (only DELETE). Use POST /project/projectActivity to link activities individually." };
    }
    // Block tool names used as API paths
    if (call.path === "/query_api_docs" || call.path === "/calculate" || call.path === "/query_file") {
      return { error: true, message: `${call.path} is a TOOL, not an API endpoint. Use it as a tool call (name="${call.path.slice(1)}"), not as tripletex_api path.` };
    }
    // Auto-fix: strip invalid "name" field from PaymentType queries (field doesn't exist — causes 400)
    if (call.method === "GET" && (call.path === "/invoice/paymentType" || call.path === "/ledger/paymentTypeOut" || call.path === "/travelExpense/paymentType")) {
      const fields = String(call.params?.fields || "");
      if (fields.includes("name")) {
        call.params = { ...call.params, fields: fields.replace(/\bname\b,?/g, "").replace(/,$/,"").replace(/^,/,"") || "id,description" };
      }
    }
    // Cap occupation code searches at 3 to prevent search spirals
    if (call.method === "GET" && call.path === "/employee/employment/occupationCode") {
      this.occupationCodeSearchCount++;
      if (this.occupationCodeSearchCount > 3) {
        return { error: true, message: "BLOCKED: Max 3 occupation code searches reached. Use the best match from previous results and proceed to POST /employee/employment/details. Pick the closest code even if not exact." };
      }
    }
    // Track bank account checks
    if (call.method === "GET" && call.path === "/ledger/account" && String(call.params?.isBankAccount) === "true") {
      this.bankAccountChecked = true;
    }
    if (call.method === "PUT" && call.path?.startsWith("/ledger/account/")) {
      this.bankAccountChecked = true;
    }
    // Block POST /invoice if bank account hasn't been checked yet
    if (call.method === "POST" && call.path === "/invoice" && !this.bankAccountChecked) {
      return { error: true, message: "BLOCKED: You must check/set up the bank account BEFORE creating an invoice. Do GET /ledger/account?isBankAccount=true first, then PUT to set bankAccountNumber if empty." };
    }
    // Auto-send invoices — ALWAYS set sendToCustomer=true on POST /invoice
    if (call.method === "POST" && call.path === "/invoice") {
      if (!call.params) call.params = {};
      call.params.sendToCustomer = true;
    }
    // Auto-add paidAmountCurrency on invoice payment if missing
    if (call.method === "PUT" && call.path?.includes("/:payment") && call.params) {
      const params = call.params as Record<string, unknown>;
      if (params.paidAmount && !params.paidAmountCurrency) {
        // Log warning — paidAmountCurrency is required for foreign currency invoices
        console.log("Warning: paidAmountCurrency not set on payment — may fail for foreign currency invoices");
      }
    }
    // Auto-set fields on customer/supplier creation
    if (call.method === "POST" && (call.path === "/customer" || call.path === "/supplier") && body && typeof body === "object" && !Array.isArray(body)) {
      const obj = body as Record<string, unknown>;
      if (obj.email && !obj.invoiceEmail) {
        obj.invoiceEmail = obj.email;
      }
      // Do NOT auto-set isCustomer on suppliers — only set if the task explicitly says so
      // Convert deprecated bankAccounts to bankAccountPresentation
      if (obj.bankAccounts && Array.isArray(obj.bankAccounts) && !obj.bankAccountPresentation) {
        obj.bankAccountPresentation = (obj.bankAccounts as string[]).map((bban: string) => ({ bban }));
      }
    }
    // Auto-fix incomingInvoice: ensure orderLines have externalId
    if (call.method === "POST" && call.path === "/incomingInvoice" && body && typeof body === "object" && !Array.isArray(body)) {
      const obj = body as Record<string, unknown>;
      const orderLines = obj.orderLines as Array<Record<string, unknown>> | undefined;
      if (orderLines) {
        for (let i = 0; i < orderLines.length; i++) {
          if (!orderLines[i].externalId) {
            orderLines[i].externalId = `line-${i + 1}`;
          }
        }
      }
    }
    // Auto-enhance vouchers with supplier postings
    if (call.method === "POST" && call.path === "/ledger/voucher" && body && typeof body === "object" && !Array.isArray(body)) {
      const obj = body as Record<string, unknown>;
      const postings = obj.postings as Array<Record<string, unknown>> | undefined;
      const hasSupplier = postings?.some(p => p.supplier);
      if (hasSupplier) {
        // Extract invoice number from description if not explicitly set (safety net)
        if (!obj.vendorInvoiceNumber) {
          const desc = String(obj.description || "");
          const invMatch =
            desc.match(/\b(?:Faktura|Invoice)\s*(?:nr\.?|no\.?|#|:)?\s*(INV-\d{4}-\d+|\d{4,})\b/i)
            ?? desc.match(/\b(INV-\d{4}-\d+)\b/i);
          if (invMatch) obj.vendorInvoiceNumber = invMatch[1];
        }
        // Copy vendorInvoiceNumber to externalVoucherNumber (vendorInvoiceNumber doesn't persist on API)
        if (obj.vendorInvoiceNumber && !obj.externalVoucherNumber) {
          obj.externalVoucherNumber = obj.vendorInvoiceNumber;
        }
        // Set invoiceNumber on each posting from vendorInvoiceNumber
        if (obj.vendorInvoiceNumber && postings) {
          for (const p of postings) {
            if (!p.invoiceNumber) p.invoiceNumber = obj.vendorInvoiceNumber;
          }
        }
      }
    }
    // === PRE-CALL VALIDATION ===
    // Pre-call validation — catches errors BEFORE hitting the API (no call/error counted)
    const validationError = this.validate(call.method, call.path, call.params, body as Record<string, unknown>);
    if (validationError) {
      // Return error to Gemini without counting as API call — this is a local validation
      return { error: true, message: validationError, _validation: true } as unknown;
    }

    return this.request(call.method, call.path, {
      params: call.params,
      body: body as Record<string, unknown>,
    });
  }

  private validate(method: string, path: string, params?: Record<string, string | number | boolean>, body?: Record<string, unknown>): string | null {
    // Block/fix invalid field filters that always cause 400
    if (method === "GET" && params) {
      // Strip fields entirely for payment-type endpoints (they don't support filtering)
      if (path === "/invoice/paymentType" || path === "/ledger/paymentTypeOut") {
        delete params.fields;
      }
      // Ensure supplierInvoice has required date params
      if (path === "/supplierInvoice" && !params.invoiceDateFrom) {
        params.invoiceDateFrom = "2020-01-01";
        params.invoiceDateTo = "2030-12-31";
      }
      let fields = String(params.fields || "");
      if (fields) {
        fields = fields.replace(/isoCode|isoName/g, "code");
        fields = fields.replace(/\bsymbol\b/g, "code");
        if (path.includes("/invoice")) {
          fields = fields.replace(/\bdueDate\b/g, "invoiceDueDate");
          fields = fields.replace(/\border\b(?!\w)/g, "");
          fields = fields.replace(/\bdescription\b/g, "");
          fields = fields.replace(/\bisPaid\b/g, "");
        }
        if (path.includes("/supplierInvoice")) {
          fields = fields.replace(/\bamountOutstanding\b/g, "outstandingAmount");
          fields = fields.replace(/\bname\b/g, "");
        }
        fields = fields.replace(/\btypeOfVat\b/g, "");
        fields = fields.replace(/,,/g, ",").replace(/^,|,$/g, "");
        if (fields) params.fields = fields;
        else delete params.fields;
      }
    }

    // Voucher validation
    if (method === "POST" && path === "/ledger/voucher" && body) {
      const postings = body.postings as Array<Record<string, unknown>> | undefined;
      if (postings) {
        // Ensure every posting has row field
        for (let i = 0; i < postings.length; i++) {
          if (!postings[i].row) postings[i].row = i + 1;
        }
        // Ensure all 4 amount fields are set and coerce types
        for (const p of postings) {
          // Coerce row to number
          if (p.row && typeof p.row !== "number") p.row = Number(p.row);
          // Coerce amounts to number
          for (const key of ["amount", "amountCurrency", "amountGross", "amountGrossCurrency"]) {
            if (p[key] !== undefined && typeof p[key] !== "number") p[key] = Number(p[key]);
          }
          const amt = p.amount as number;
          if (amt !== undefined) {
            if (p.amountCurrency === undefined) p.amountCurrency = amt;
            if (p.amountGross === undefined) p.amountGross = amt;
            if (p.amountGrossCurrency === undefined) p.amountGrossCurrency = amt;
          }
        }
        // Check AP postings (2400) have supplier
        // Check revenue postings (3000+) have customer
        // (Don't block — just auto-fix or warn)
      }
    }

    // Block POST /ledger/account with invalid type
    if (method === "POST" && path === "/ledger/account" && body) {
      const validTypes = [
        "ASSETS", "EQUITY", "LIABILITIES", "OPERATING_REVENUES", "OPERATING_EXPENSES",
        "INVESTMENT_INCOME", "COST_OF_CAPITAL", "TAX_ON_ORDINARY_ACTIVITIES",
        "EXTRAORDINARY_INCOME", "EXTRAORDINARY_COST", "TAX_ON_EXTRAORDINARY_ACTIVITIES",
        "ANNUAL_RESULT", "TRANSFERS_AND_ALLOCATIONS",
      ];
      if (body.type && !validTypes.includes(body.type as string)) {
        // Remove invalid type — let Tripletex assign default
        delete body.type;
      }
    }

    // Invoice semantic validation
    if (path === "/invoice") {
      if (method === "GET" && params) {
        const p = params as Record<string, unknown>;
        if ("invoiceDate" in p || "invoiceDueDate" in p || "orders" in p) {
          return "GET /invoice is for search only. To create an invoice, use POST /invoice with body { invoiceDate, invoiceDueDate, orders }.";
        }
      }
      if (method === "POST" && body) {
        if (!body.invoiceDate) return "POST /invoice requires invoiceDate.";
        if (!body.invoiceDueDate) return "POST /invoice requires invoiceDueDate.";
        const orders = body.orders as Array<unknown> | undefined;
        if (!Array.isArray(orders) || orders.length === 0) return "POST /invoice requires orders: [{id: ...}]. Create the order first.";
      }
    }

    // Per diem validation
    if (method === "POST" && path === "/travelExpense/perDiemCompensation" && body) {
      for (const key of ["travelExpense", "rateCategory", "count", "location", "overnightAccommodation"]) {
        if (!(key in body)) return `POST /travelExpense/perDiemCompensation requires '${key}'.`;
      }
    }

    // Order validation
    if (method === "POST" && path === "/order" && body) {
      const orderLines = (body as any).orderLines;
      if (!Array.isArray(orderLines) || orderLines.length === 0) {
        return "POST /order requires a non-empty orderLines array with product references.";
      }
      for (const line of orderLines) {
        if (!line.product || typeof line.product.id !== "number") {
          return "Each order line must reference an existing product by product:{id:number}. Do not embed product objects inline.";
        }
      }
    }

    return null; // No blocking error
  }
}

export class TripletexApiError extends Error {
  status: number;
  details: TripletexError;

  constructor(status: number, details: TripletexError) {
    super(details.message || `Tripletex API error ${status}`);
    this.name = "TripletexApiError";
    this.status = status;
    this.details = details;
  }
}
