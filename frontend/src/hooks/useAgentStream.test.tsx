import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAgentStream } from "./useAgentStream";

const wsUrlMock = vi.fn(() => "ws://localhost:8000/clients/client-1/stream?token=token-1");

vi.mock("../api/client", () => ({
  wsUrl: (...args: [string, string]) => wsUrlMock(...args)
}));

class FakeWebSocket {
  static lastInstance: FakeWebSocket | null = null;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  closed = false;

  constructor(public readonly url: string) {
    FakeWebSocket.lastInstance = this;
  }

  close() {
    this.closed = true;
  }
}

function StreamProbe({ clientId, token }: { clientId: string; token: string }) {
  const { connected, lastEvent } = useAgentStream(clientId, token);
  return (
    <div>
      <span data-testid="connected">{String(connected)}</span>
      <span data-testid="event">{lastEvent ? JSON.stringify(lastEvent) : ""}</span>
    </div>
  );
}

describe("useAgentStream", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    FakeWebSocket.lastInstance = null;
  });

  it("tracks websocket connection and incoming event payloads", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    render(<StreamProbe clientId="client-1" token="token-1" />);

    expect(wsUrlMock).toHaveBeenCalledWith("client-1", "token-1");
    const instance = FakeWebSocket.lastInstance;
    expect(instance).toBeTruthy();

    act(() => {
      instance?.onopen?.();
    });
    await waitFor(() => expect(screen.getByTestId("connected")).toHaveTextContent("true"));

    act(() => {
      instance?.onmessage?.({ data: '{"event":"proposal_created"}' });
    });
    await waitFor(() =>
      expect(screen.getByTestId("event")).toHaveTextContent('{"event":"proposal_created"}')
    );

    act(() => {
      instance?.onclose?.();
    });
    await waitFor(() => expect(screen.getByTestId("connected")).toHaveTextContent("false"));
  });
});
