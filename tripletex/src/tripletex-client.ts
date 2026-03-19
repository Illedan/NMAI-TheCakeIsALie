import type {
  TripletexCredentials,
  TripletexListResponse,
  TripletexSingleResponse,
  TripletexError,
} from "./types.js";

export class TripletexClient {
  private baseUrl: string;
  private authHeader: string;
  callCount = 0;
  errorCount = 0;

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

    const res = await fetch(url.toString(), {
      method,
      headers: {
        Authorization: this.authHeader,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      ...(options.body ? { body: JSON.stringify(options.body) } : {}),
    });

    if (!res.ok) {
      this.errorCount++;
      const err = (await res.json().catch(() => ({}))) as TripletexError;
      throw new TripletexApiError(res.status, err);
    }

    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
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
    body?: Record<string, unknown>;
  }): Promise<unknown> {
    return this.request(call.method, call.path, {
      params: call.params,
      body: call.body,
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
