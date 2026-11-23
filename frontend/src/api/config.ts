/** Where the backend lives. Override with VITE_API_URL in frontend/.env.local. */
export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

/** WebSocket endpoint derived from the REST base URL (http -> ws, https -> wss). */
export function wsUrl(base: string = API_URL): string {
  return `${base.replace(/\/+$/, "").replace(/^http/, "ws")}/ws/state`;
}
