import { getSession } from "../store/session";
import { clearSession } from "../store/session";
import { ApiError } from "./errors";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 15000);

export function getApiBaseUrl(): string {
  return API_BASE;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { token } = getSession();
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: options.signal ?? controller.signal
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(
        408,
        `Request timed out after ${REQUEST_TIMEOUT_MS}ms. Check that backend is running at ${API_BASE}.`
      );
    }
    throw new ApiError(0, `Network error. Check that backend is running at ${API_BASE}.`);
  } finally {
    clearTimeout(timeoutHandle);
  }

  if (!response.ok) {
    const text = await response.text();
    const message = parseApiErrorText(text);
    if (response.status === 401 || response.status === 403) clearSession();
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function wsUrl(clientId: string): string {
  const raw = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000";
  return `${raw}/clients/${clientId}/stream`;
}

function parseApiErrorText(raw: string): string {
  const text = raw?.trim();
  if (!text) return "Request failed";
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; message?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) return parsed.detail;
    if (typeof parsed.message === "string" && parsed.message.trim()) return parsed.message;
  } catch {
    return text;
  }
  return text;
}
