export function timelinePositions(
  series: { x_start: number; x_end: number }[],
  axis: string | undefined,
): number[] {
  if (axis !== "elapsed UTC seconds")
    return series.map((_, index) => (index + 0.5) / Math.max(series.length, 1));
  const lower = Math.min(...series.map((point) => point.x_start));
  const upper = Math.max(...series.map((point) => point.x_end));
  return series.map((point) =>
    upper > lower
      ? ((point.x_start + point.x_end) / 2 - lower) / (upper - lower)
      : 0.5,
  );
}
