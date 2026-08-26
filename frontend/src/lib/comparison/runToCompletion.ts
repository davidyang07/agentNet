import {
  createExperiment,
  getExperiment,
  stopExperiment,
  backendWsUrl,
  type ExperimentConfig,
} from "@/lib/api/client";
import {
  reduce,
  initialGraphState,
  selectMetrics,
  type GraphState,
  type StreamFrame,
} from "@/lib/stream/reducer";

const STATUS_POLL_INTERVAL_MS = 1000;

export type RunResult = {
  experimentId: string;
  metrics: ReturnType<typeof selectMetrics>;
};

/**
 * Headless (non-React) helper that creates an experiment, observes it live
 * over WS (feeding every frame through the same pure `reduce()` the
 * dashboard's `useExperimentStream` hook uses), and detects natural
 * completion via REST polling of `getExperiment` — WS alone never surfaces
 * a status change on natural finish, so polling is the only reliable
 * terminal-state signal (see the equivalent status-poll `useEffect` in
 * `app/page.tsx`).
 *
 * On both the success path and the cancellation (AbortSignal) path,
 * `stopExperiment` is called best-effort after the outcome is otherwise
 * determined, and the WebSocket is always closed.
 */
export async function runExperimentToCompletion(
  config: ExperimentConfig,
  opts?: { signal?: AbortSignal },
): Promise<RunResult> {
  const summary = await createExperiment(config);
  const experimentId = summary.experiment_id;

  let graphState: GraphState = initialGraphState;
  const ws = new WebSocket(backendWsUrl(experimentId));
  ws.onmessage = (ev) => {
    const frame = JSON.parse(ev.data as string) as StreamFrame;
    graphState = reduce(graphState, frame);
  };

  try {
    await new Promise<void>((resolve, reject) => {
      if (opts?.signal?.aborted) {
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      let cancelled = false;
      let timer: ReturnType<typeof setTimeout>;

      const cleanup = () => {
        cancelled = true;
        clearTimeout(timer);
        opts?.signal?.removeEventListener("abort", onAbort);
      };
      function onAbort() {
        cleanup();
        reject(new DOMException("Aborted", "AbortError"));
      }
      opts?.signal?.addEventListener("abort", onAbort);

      const poll = () => {
        if (cancelled) return;
        getExperiment(experimentId)
          .then((s) => {
            if (cancelled) return;
            if (s.status === "finished" || s.status === "stopped") {
              cleanup();
              resolve();
            } else {
              timer = setTimeout(poll, STATUS_POLL_INTERVAL_MS);
            }
          })
          .catch(() => {
            if (!cancelled) timer = setTimeout(poll, STATUS_POLL_INTERVAL_MS);
          });
      };
      timer = setTimeout(poll, STATUS_POLL_INTERVAL_MS);
    });
  } catch (err) {
    // Deviates from a bare try/finally: the cancellation path must still
    // best-effort stop the experiment (guarantee 3), which a plain
    // try/finally can't do since a rejection would skip the code after it.
    ws.close();
    await stopExperiment(experimentId).catch(() => {});
    throw err;
  }

  ws.close();
  const metrics = selectMetrics(graphState);
  await stopExperiment(experimentId).catch(() => {});
  return { experimentId, metrics };
}
