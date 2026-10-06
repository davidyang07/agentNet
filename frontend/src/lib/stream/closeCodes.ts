/**
 * WebSocket close codes from backend/app/api/ws.py, pinned on both sides
 * (closeCodes.test.ts / backend tests/test_ws_lifecycle.py).
 *
 * After a final close nothing more will ever arrive — the run ended and its
 * last event was delivered, or the run doesn't exist — so the client must
 * not reconnect. CLOSE_RESYNC means the client fell too far behind; it
 * reconnects with its last seq and the server resyncs it.
 */
export const CLOSE_RESYNC = 4000;
export const CLOSE_EXPERIMENT_ENDED = 4001;
export const CLOSE_UNKNOWN_EXPERIMENT = 4004;

export function isFinalClose(code: number): boolean {
  return code === CLOSE_EXPERIMENT_ENDED || code === CLOSE_UNKNOWN_EXPERIMENT;
}
