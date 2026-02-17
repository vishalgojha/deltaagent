const TOKEN_KEY = "ta_token";
const CLIENT_KEY = "ta_client_id";

export function getSession() {
  return {
    token: localStorage.getItem(TOKEN_KEY) ?? "",
    clientId: localStorage.getItem(CLIENT_KEY) ?? ""
  };
}

export function saveSession(token: string, clientId: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(CLIENT_KEY, clientId);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(CLIENT_KEY);
}
