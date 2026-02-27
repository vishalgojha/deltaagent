const ADMIN_TOKEN_KEY = "ta_admin_token";

function getStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function getAdminSessionToken(): string {
  return getStorage()?.getItem(ADMIN_TOKEN_KEY) ?? "";
}

export function saveAdminSessionToken(token: string): void {
  getStorage()?.setItem(ADMIN_TOKEN_KEY, token);
}

export function clearAdminSessionToken(): void {
  getStorage()?.removeItem(ADMIN_TOKEN_KEY);
}
