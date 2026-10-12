import createClient from "openapi-fetch";

import type { paths } from "./schema";

// `credentials: "include"` is required for the httpOnly auth cookie to be sent/received
// across the frontend (localhost:3000) <-> backend (localhost:8000) origins in dev.
export const apiClient = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  credentials: "include",
});
