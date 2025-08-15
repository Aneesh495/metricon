import { expect, test } from "vitest";
import { readSelection, selectionQuery } from "./selection";
import { timelinePositions } from "./chart-geometry";

test("deep links retain independent version, learner and artifact identities", () => {
  const selection = readSelection(
    "?workspace=w&version=old&learner=%E5%AD%A6%E7%94%9F%2F1&artifact=run&tab=provenance",
  );
  expect(selection.learner).toBe("学生/1");
  expect(readSelection(selectionQuery(selection))).toEqual(selection);
  expect(readSelection("?tab=unknown").tab).toBe("observations");
  expect(readSelection("").workspace).toBe("");
});

test("elapsed-time charts preserve unequal gaps rather than equal answer spacing", () => {
  const series = [0, 1, 100].map((value) => ({ x_start: value, x_end: value }));
  expect(timelinePositions(series, "elapsed UTC seconds")).toEqual([
    0, 0.01, 1,
  ]);
  expect(timelinePositions(series, "source event order")).toEqual([
    1 / 6,
    1 / 2,
    5 / 6,
  ]);
  expect(
    timelinePositions([{ x_start: 5, x_end: 5 }], "elapsed UTC seconds"),
  ).toEqual([0.5]);
  expect(timelinePositions([], "elapsed UTC seconds")).toEqual([]);
});
