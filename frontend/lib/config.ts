export const config = {
  apiBase: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000",
  authMode: (process.env.NEXT_PUBLIC_AUTH_MODE ?? "mock") as "mock" | "entra",
  tenantId: process.env.NEXT_PUBLIC_ENTRA_TENANT_ID ?? "",
  clientId: process.env.NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID ?? "",
  apiScope: process.env.NEXT_PUBLIC_ENTRA_API_SCOPE ?? "",
};
