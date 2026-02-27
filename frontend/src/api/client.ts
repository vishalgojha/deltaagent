import { getSession } from "../store/session";
import { clearSession } from "../store/session";
import { ApiError } from "./errors";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function getApiBaseUrl(): string {
  return API_BASE;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { token } = getSession();
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    if (response.status === 401 || response.status === 403) clearSession();
    throw new ApiError(response.status, text);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function wsUrl(clientId: string): string {
  const raw = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000";
  return `${raw}/clients/${clientId}/stream`;
}
