import { describe, it, expect } from "vitest";
import { scalarBKT } from "../pages/ModelMicroscope";
import { number, percentage, parseObject } from "./format";

describe("Model explanation contract", () => {
  it("conditions a correct answer before the learning transition", () => {
    const result = scalarBKT(0.2, true, {
      initial: 0.2,
      learning: 0.1,
      slip: 0.1,
      guess: 0.2,
      forgetting: 0,
    });
    expect(result.prediction).toBeCloseTo(0.34, 12);
    expect(result.posterior).toBeCloseTo(0.18 / 0.34, 12);
    expect(result.next).toBeCloseTo(0.18 / 0.34 + (1 - 0.18 / 0.34) * 0.1, 12);
  });
  it("unknown metrics are never formatted as zero", () => {
    expect(number(null)).toBe("Unknown");
    expect(percentage(null)).toBe("Unknown");
  });
  it("rejects arrays where planner maps are required", () => {
    expect(() => parseObject("[]", "Priorities")).toThrow();
  });
});
