import { useEffect, useState } from "react";
import { wsUrl } from "../api/client";

export function useAgentStream(clientId: string, token: string) {
  const [lastEvent, setLastEvent] = useState<Record<string, unknown> | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!clientId || !token) return;
    const socket = new WebSocket(wsUrl(clientId, token));
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);
    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        setLastEvent(parsed);
      } catch {
        setLastEvent({ raw: event.data });
      }
    };
    return () => socket.close();
  }, [clientId, token]);

  return { connected, lastEvent };
}
