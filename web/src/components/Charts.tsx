import { useState } from "react";
import type { Metrics, Trend } from "../api/contracts";
import { number, percentage } from "../lib/format";
import { timelinePositions } from "../lib/chart-geometry";

const WIDTH = 760;
const HEIGHT = 280;
const LEFT = 48;
const RIGHT = 24;
const TOP = 18;
const BOTTOM = 40;
const plotWidth = WIDTH - LEFT - RIGHT;
const plotHeight = HEIGHT - TOP - BOTTOM;
const y = (value: number) => TOP + (1 - value) * plotHeight;

function Grid() {
  return (
    <g className="chart-grid">
      {[0, 0.25, 0.5, 0.75, 1].map((value) => (
        <g key={value}>
          <line x1={LEFT} x2={WIDTH - RIGHT} y1={y(value)} y2={y(value)} />
          <text x={LEFT - 10} y={y(value) + 4} textAnchor="end">
            {value * 100}%
          </text>
        </g>
      ))}
    </g>
  );
}

export function TrendChart({ trend }: { trend: Trend }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const positions = timelinePositions(trend.series, trend.axis);
  const x = (index: number) => LEFT + positions[index] * plotWidth;
  const valid = trend.series.filter(
    (point) => point.accuracy.estimate !== null,
  );
  if (!trend.available || !valid.length)
    return (
      <div className="chart-empty">
        {trend.reason ??
          "No eligible time observations. Missing or shifted timestamps cannot produce calendar trends."}
      </div>
    );
  const line = trend.series
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(point.accuracy.estimate ?? 0).toFixed(2)}`,
    )
    .join(" ");
  const upper = trend.series
    .map((point, index) => `${x(index)},${y(point.accuracy.upper ?? 1)}`)
    .join(" ");
  const lower = [...trend.series]
    .reverse()
    .map(
      (point, index) =>
        `${x(trend.series.length - 1 - index)},${y(point.accuracy.lower ?? 0)}`,
    )
    .join(" ");
  const selectedIndex = hovered ?? chosen;
  const selected = selectedIndex === null ? null : trend.series[selectedIndex];
  return (
    <div className="chart">
      <label className="field">
        <span>Inspect timeline bin</span>
        <select
          value={chosen ?? ""}
          onChange={(event) =>
            setChosen(
              event.target.value === "" ? null : Number(event.target.value),
            )
          }
        >
          <option value="">Choose a supported bin</option>
          {trend.series.map((point, index) => (
            <option key={point.bucket} value={index}>
              Bin {point.bucket} / n={point.accuracy.n}
            </option>
          ))}
        </select>
      </label>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Observed accuracy over ${trend.axis}, with Wilson uncertainty and retained extrema`}
        onMouseLeave={() => setHovered(null)}
      >
        <Grid />
        <polygon points={`${upper} ${lower}`} className="chart-band" />
        <path d={line} className="chart-line" />
        {trend.series.map((point, index) => (
          <g key={point.bucket}>
            <line
              x1={x(index)}
              x2={x(index)}
              y1={y(point.maximum)}
              y2={y(point.minimum)}
              className="chart-extrema"
            />
            <circle
              cx={x(index)}
              cy={y(point.accuracy.estimate ?? 0)}
              r={hovered === index ? 5 : 2.5}
              className="chart-dot"
            />
            <rect
              x={x(index) - plotWidth / trend.series.length / 2}
              y={TOP}
              width={plotWidth / trend.series.length}
              height={plotHeight}
              fill="transparent"
              onMouseEnter={() => setHovered(index)}
              onPointerDown={() => setChosen(index)}
            />
          </g>
        ))}
        <text x={LEFT} y={HEIGHT - 10} className="chart-axis">
          {trend.axis}
        </text>
        <text
          x={WIDTH - RIGHT}
          y={HEIGHT - 10}
          textAnchor="end"
          className="chart-axis"
        >
          {number(trend.series.reduce((n, point) => n + point.accuracy.n, 0))}{" "}
          observations
        </text>
      </svg>
      <div className="chart-caption">
        {selected ? (
          <>
            Bin {selected.bucket}: {percentage(selected.accuracy.estimate)}, 95%
            interval {percentage(selected.accuracy.lower)} to{" "}
            {percentage(selected.accuracy.upper)}, n={selected.accuracy.n}.
            Source range {number(selected.x_start)} to {number(selected.x_end)}.
          </>
        ) : (
          <>
            Line: observed accuracy. Band: 95% Wilson interval. Faint ranges
            preserve answer extrema. Hover, tap or select a bin to inspect
            denominators.
          </>
        )}
      </div>
    </div>
  );
}

export function CalibrationChart({ metrics }: { metrics: Metrics }) {
  const x = (value: number) => LEFT + value * plotWidth;
  const points = metrics.calibration.bins.filter(
    (bin) => bin.n && bin.prediction !== null && bin.observed.estimate !== null,
  );
  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Calibration diagram comparing predicted and observed correctness; circles scale with bin counts"
      >
        <Grid />
        <line
          x1={x(0)}
          x2={x(1)}
          y1={y(0)}
          y2={y(1)}
          className="chart-reference"
        />
        {points.map((bin) => (
          <g key={bin.bin}>
            <title>
              Bin {bin.bin}: predicted {percentage(bin.prediction)}, observed{" "}
              {percentage(bin.observed.estimate)}, n={number(bin.n)}
            </title>
            <line
              x1={x(bin.prediction!)}
              x2={x(bin.prediction!)}
              y1={y(bin.observed.lower!)}
              y2={y(bin.observed.upper!)}
              className="calibration-whisker"
            />
            <circle
              cx={x(bin.prediction!)}
              cy={y(bin.observed.estimate!)}
              r={Math.min(14, 3 + Math.sqrt(bin.n) / 8)}
              className="calibration-point"
            />
          </g>
        ))}
        <text x={LEFT} y={HEIGHT - 10} className="chart-axis">
          Predicted correctness
        </text>
        <text
          x={WIDTH - RIGHT}
          y={HEIGHT - 10}
          textAnchor="end"
          className="chart-axis"
        >
          ECE {number(metrics.calibration.ece, 4)}
        </text>
      </svg>
      <p className="chart-caption">
        {metrics.calibration.method}. Whiskers show Wilson intervals. Empty bins
        are unknown. Circle sizes reflect observations.
      </p>
      <details className="chart-data">
        <summary>Show calibration data table</summary>
        <div
          className="table-scroll"
          tabIndex={0}
          aria-label="Calibration data table"
        >
          <table>
            <thead>
              <tr>
                <th scope="col">Probability bin</th>
                <th scope="col">Observations</th>
                <th scope="col">Predicted</th>
                <th scope="col">Observed</th>
                <th scope="col">95% Wilson interval</th>
              </tr>
            </thead>
            <tbody>
              {metrics.calibration.bins.map((bin) => (
                <tr key={bin.bin}>
                  <td>
                    {number(bin.left, 2)} to {number(bin.right, 2)}
                  </td>
                  <td>{number(bin.n)}</td>
                  <td>{percentage(bin.prediction)}</td>
                  <td>{percentage(bin.observed.estimate)}</td>
                  <td>
                    {percentage(bin.observed.lower)} to{" "}
                    {percentage(bin.observed.upper)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

export function CoefficientChart({
  associations,
}: {
  associations: { feature: string; coefficient: number }[];
}) {
  const maximum = Math.max(
    1,
    ...associations.map((row) => Math.abs(row.coefficient)),
  );
  return (
    <div className="coefficients">
      {associations.map((row) => (
        <div className="coefficient" key={row.feature}>
          <span title={row.feature}>{row.feature}</span>
          <div className="coefficient-track">
            <i
              style={{
                left:
                  row.coefficient >= 0
                    ? "50%"
                    : `${50 + (row.coefficient / maximum) * 50}%`,
                width: `${(Math.abs(row.coefficient) / maximum) * 50}%`,
              }}
              className={row.coefficient >= 0 ? "positive" : "negative"}
            />
            <b />
          </div>
          <code>{number(row.coefficient, 3)}</code>
        </div>
      ))}
    </div>
  );
}
