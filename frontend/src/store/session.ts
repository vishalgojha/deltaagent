const TOKEN_KEY = "ta_token";
const CLIENT_KEY = "ta_client_id";
const SESSION_EVENT = "ta:session-updated";

type SessionListener = () => void;
const listeners = new Set<SessionListener>();

function emitSessionUpdate() {
  listeners.forEach((listener) => listener());
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key === TOKEN_KEY || event.key === CLIENT_KEY) emitSessionUpdate();
  });
  window.addEventListener(SESSION_EVENT, emitSessionUpdate);
}

export function getSession() {
  return {
    token: localStorage.getItem(TOKEN_KEY) ?? "",
    clientId: localStorage.getItem(CLIENT_KEY) ?? ""
  };
}

export function subscribeSession(listener: SessionListener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function saveSession(token: string, clientId: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(CLIENT_KEY, clientId);
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_EVENT));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(CLIENT_KEY);
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_EVENT));
}
