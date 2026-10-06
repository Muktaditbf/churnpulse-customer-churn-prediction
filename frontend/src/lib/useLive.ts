import { useEffect, useRef, useState } from "react";
import type { LiveItem } from "./api";

export type LiveMessage =
  | { type: "prediction"; data: LiveItem }
  | { type: "stats"; data: Record<string, number> }
  | { type: "snapshot_progress"; scored: number };

/** WebSocket connection to /ws/live with automatic reconnect. */
export function useLive(onMessage: (m: LiveMessage) => void) {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onMessage);
  handler.current = onMessage;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout>;
    let closed = false;

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${window.location.host}/ws/live`);
      socket.onopen = () => setConnected(true);
      socket.onmessage = (e) => handler.current(JSON.parse(e.data));
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, []);

  return connected;
}
