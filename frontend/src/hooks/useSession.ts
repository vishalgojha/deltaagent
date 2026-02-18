import { useSyncExternalStore } from "react";
import { getSession, subscribeSession } from "../store/session";

export function useSession() {
  return useSyncExternalStore(subscribeSession, getSession, getSession);
}
