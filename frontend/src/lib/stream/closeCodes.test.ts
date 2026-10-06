import { describe, expect, it } from "vitest";

import {
  CLOSE_EXPERIMENT_ENDED,
  CLOSE_RESYNC,
  CLOSE_UNKNOWN_EXPERIMENT,
  isFinalClose,
} from "./closeCodes";

describe("stream close codes", () => {
  it("match the backend's literal values", () => {
    // Pinned on the backend side too (tests/test_ws_lifecycle.py).
    expect([CLOSE_RESYNC, CLOSE_EXPERIMENT_ENDED, CLOSE_UNKNOWN_EXPERIMENT]).toEqual([
      4000, 4001, 4004,
    ]);
  });

  it("treats an ended or unknown run as final", () => {
    expect(isFinalClose(CLOSE_EXPERIMENT_ENDED)).toBe(true);
    expect(isFinalClose(CLOSE_UNKNOWN_EXPERIMENT)).toBe(true);
  });

  it("reconnects after a resync request or an abnormal drop", () => {
    expect(isFinalClose(CLOSE_RESYNC)).toBe(false);
    expect(isFinalClose(1006)).toBe(false);
    expect(isFinalClose(1000)).toBe(false);
  });
});
