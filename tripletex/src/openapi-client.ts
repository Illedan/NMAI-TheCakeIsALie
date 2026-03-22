import createClient, { type Middleware } from "openapi-fetch";
import type { paths, components } from "./openapi-types.js";
import type { TripletexCredentials } from "./types.js";

export type Schemas = components["schemas"];

/**
 * Create a type-safe Tripletex API client from the OpenAPI spec.
 *
 * Usage:
 *   const api = createTripletexApi(credentials);
 *   const { data, error } = await api.GET("/employee", { params: { query: { fields: "*" } } });
 */
export function createTripletexApi(credentials: TripletexCredentials) {
  const baseUrl = credentials.base_url.replace(/\/$/, "");
  const authHeader =
    "Basic " + Buffer.from(`0:${credentials.session_token}`).toString("base64");

  const authMiddleware: Middleware = {
    async onRequest({ request }) {
      request.headers.set("Authorization", authHeader);
      request.headers.set("Content-Type", "application/json");
      request.headers.set("Accept", "application/json");
      return request;
    },
  };

  const client = createClient<paths>({ baseUrl });
  client.use(authMiddleware);

  return client;
}

export type TripletexApi = ReturnType<typeof createTripletexApi>;
