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
    return this.request(call.method, call.path, {
      params: call.params,
      body: body as Record<string, unknown>,
    });
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
