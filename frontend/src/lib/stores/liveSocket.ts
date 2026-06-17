import { writable, derived } from 'svelte/store';

export type LiveMessage =
  | { type: 'odds_update'; match_id: number; data: Record<string, unknown>; timestamp: number }
  | { type: 'prediction_update'; run_id: number; status: string; progress: number | null; timestamp: number }
  | { type: 'match_event'; match_id: number; event: string; data: Record<string, unknown>; timestamp: number }
  | { type: 'pong' }
  | { type: 'subscribed'; channel: string }
  | { type: 'error'; message: string };

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

function createLiveSocketStore() {
  const { subscribe, set, update } = writable<{
    status: ConnectionStatus;
    lastMessage: LiveMessage | null;
    error: string | null;
  }>({
    status: 'disconnected',
    lastMessage: null,
    error: null,
  });

  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  const reconnectDelay = 3000;
  const maxReconnectDelay = 30000;
  let currentDelay = reconnectDelay;

  function getWsUrl(): string {
    // Compute at call time — never during SSR
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/api/v1/live/ws`;
  }

  function connect() {
    if (ws?.readyState === WebSocket.OPEN) return;
    if (typeof window === 'undefined') return;

    set({ status: 'connecting', lastMessage: null, error: null });

    try {
      const wsUrl = getWsUrl();
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        currentDelay = reconnectDelay;
        set({ status: 'connected', lastMessage: null, error: null });
        // Subscribe to all channels
        ws?.send(JSON.stringify({ action: 'subscribe', channel: 'all' }));
        // Start ping
        pingTimer = setInterval(() => {
          ws?.send(JSON.stringify({ action: 'ping' }));
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as LiveMessage;
          update((s) => ({ ...s, lastMessage: msg }));
        } catch {
          // ignore non-JSON messages
        }
      };

      ws.onclose = () => {
        if (pingTimer) {
          clearInterval(pingTimer);
          pingTimer = null;
        }
        update((s) => ({ ...s, status: 'disconnected' }));
        scheduleReconnect();
      };

      ws.onerror = () => {
        update((s) => ({ ...s, status: 'disconnected', error: 'WebSocket error' }));
      };
    } catch (err) {
      set({ status: 'disconnected', lastMessage: null, error: String(err) });
      scheduleReconnect();
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    update((s) => ({ ...s, status: 'reconnecting' }));
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      currentDelay = Math.min(currentDelay * 2, maxReconnectDelay);
      connect();
    }, currentDelay);
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (pingTimer) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
    ws?.close();
    ws = null;
    set({ status: 'disconnected', lastMessage: null, error: null });
  }

  return {
    subscribe,
    connect,
    disconnect,
  };
}

// Use same-origin WebSocket — Vite proxy forwards /api/* to the backend
export const liveSocket = createLiveSocketStore();

// Derived stores for specific message types
export const oddsUpdates = derived(
  liveSocket,
  ($s) => ($s.lastMessage?.type === 'odds_update' ? $s.lastMessage : null) as Extract<LiveMessage, { type: 'odds_update' }> | null
);

export const predictionUpdates = derived(
  liveSocket,
  ($s) => ($s.lastMessage?.type === 'prediction_update' ? $s.lastMessage : null) as Extract<LiveMessage, { type: 'prediction_update' }> | null
);

export const matchEvents = derived(
  liveSocket,
  ($s) => ($s.lastMessage?.type === 'match_event' ? $s.lastMessage : null) as Extract<LiveMessage, { type: 'match_event' }> | null
);
