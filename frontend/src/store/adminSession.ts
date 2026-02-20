const ADMIN_TOKEN_KEY = "ta_admin_token";

export function getAdminSessionToken(): string {
  return localStorage.getItem(ADMIN_TOKEN_KEY) ?? "";
}

export function saveAdminSessionToken(token: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
}

export function clearAdminSessionToken(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY);
}
