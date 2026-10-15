import { describe, expect, it } from "vitest";

import { withHistory, type OutbreakSample } from "./useOutbreakSeries";

const point = (tick: number, infectious: number, quarantined: number) => ({
  tick,
  infectious,
  quarantined,
  immune: 0,
});

const sample = (tick: number, compromised: number, quarantined: number): OutbreakSample => ({
  tick,
  compromised,
  quarantined,
  healthy: 10 - compromised - quarantined,
  total: 10,
});

describe("withHistory", () => {
  it("fills the ticks streamed before the screen opened from prevalence", () => {
    const merged = withHistory(
      [sample(3, 4, 1), sample(4, 5, 1)],
      [point(0, 1, 0), point(1, 2, 0), point(2, 3, 1), point(3, 9, 9)],
      10,
    );

    expect(merged.map((s) => s.tick)).toEqual([0, 1, 2, 3, 4]);
    expect(merged[2]).toEqual({ tick: 2, compromised: 3, quarantined: 1, healthy: 6, total: 10 });
    // Where both exist, the streamed sample wins.
    expect(merged[3]).toEqual(sample(3, 4, 1));
  });

  it("draws the whole curve from prevalence when nothing was streamed", () => {
    const merged = withHistory([], [point(0, 1, 0), point(1, 2, 1)], 10);

    expect(merged.map((s) => [s.tick, s.compromised, s.quarantined, s.healthy])).toEqual([
      [0, 1, 0, 9],
      [1, 2, 1, 7],
    ]);
  });

  it("leaves the streamed series alone without history or nodes", () => {
    const series = [sample(0, 1, 0)];

    expect(withHistory(series, null, 10)).toBe(series);
    expect(withHistory(series, [point(0, 1, 0)], 0)).toBe(series);
  });
});
