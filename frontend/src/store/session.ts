const TOKEN_KEY = "ta_token";
const CLIENT_KEY = "ta_client_id";
const SESSION_EVENT = "ta:session-updated";

export type Session = {
  token: string;
  clientId: string;
};

type SessionListener = () => void;
const listeners = new Set<SessionListener>();
let cachedSession: Session = { token: "", clientId: "" };

function emitSessionUpdate() {
  cachedSession = readSession();
  listeners.forEach((listener) => listener());
}

function getStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function readSession(): Session {
  const storage = getStorage();
  return {
    token: storage?.getItem(TOKEN_KEY) ?? "",
    clientId: storage?.getItem(CLIENT_KEY) ?? ""
  };
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key === TOKEN_KEY || event.key === CLIENT_KEY) emitSessionUpdate();
  });
  window.addEventListener(SESSION_EVENT, emitSessionUpdate);
}

export function getSession() {
  const next = readSession();
  if (cachedSession.token === next.token && cachedSession.clientId === next.clientId) {
    return cachedSession;
  }
  cachedSession = next;
  return cachedSession;
}

export function subscribeSession(listener: SessionListener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function saveSession(token: string, clientId: string) {
  const storage = getStorage();
  storage?.setItem(TOKEN_KEY, token);
  storage?.setItem(CLIENT_KEY, clientId);
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_EVENT));
}

export function clearSession() {
  const storage = getStorage();
  storage?.removeItem(TOKEN_KEY);
  storage?.removeItem(CLIENT_KEY);
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_EVENT));
}
