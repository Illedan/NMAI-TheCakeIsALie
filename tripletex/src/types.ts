export interface SolveRequest {
  prompt: string;
  files: FileAttachment[];
  tripletex_credentials: TripletexCredentials;
}

export interface FileAttachment {
  filename: string;
  content_base64: string;
  mime_type: string;
}

export interface TripletexCredentials {
  base_url: string;
  session_token: string;
}

export interface TripletexListResponse<T> {
  fullResultSize: number;
  from: number;
  count: number;
  versionDigest: string | null;
  values: T[];
}

export interface TripletexSingleResponse<T> {
  value: T;
}

export interface TripletexError {
  status: number;
  code: number;
  message: string;
  developerMessage: string;
  validationMessages: { field: string; message: string }[];
  requestId: string;
}

export interface ToolCall {
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
  params?: Record<string, string | number | boolean>;
  body?: Record<string, unknown>;
}
