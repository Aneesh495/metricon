import { DataTools } from "../components/DataTools";
import { VirtualRows } from "../components/VirtualRows";
import { useDeferredValue, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { CalibrationChart, TrendChart } from "../components/Charts";
import {
  Empty,
  ErrorState,
  Field,
  Inspector,
  IntervalBar,
  Loading,
  Metric,
  Notice,
  Pagination,
  Panel,
  Tag,
} from "../components/Common";
import { number, percentage } from "../lib/format";
import type { Metrics } from "../api/contracts";

export function Observations({
  dataset,
  learner,
  onLearner,
}: {
  dataset: string;
  learner: string;
  onLearner: (value: string) => void;
}) {
  const [dimension, setDimension] = useState("question");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [offset, setOffset] = useState(0);
  const [question, setQuestion] = useState("");
  const [axis, setAxis] = useState<"order" | "time">("order");
  const [historyOffset, setHistoryOffset] = useState(0);
  const overview = useQuery({
    queryKey: ["overview", dataset, learner],
    queryFn: () => api.overview(dataset, learner || undefined),
  });
  const groups = useQuery({
    queryKey: ["groups", dataset, dimension, offset, learner, deferredSearch],
    queryFn: () =>
      api.groups(
        dataset,
        dimension,
        offset,
        learner || undefined,
        deferredSearch,
      ),
  });
  const [learnerSearch, setLearnerSearch] = useState("");
  const learners = useQuery({
    queryKey: ["learners", dataset, learnerSearch],
    queryFn: () => api.groups(dataset, "learner", 0, undefined, learnerSearch),
  });
  const trend = useQuery({
    queryKey: ["trend", dataset, learner, axis, question],
    queryFn: () => api.trend(dataset, learner, axis, question || undefined),
    enabled: Boolean(learner),
  });
  const history = useQuery({
    queryKey: ["history", dataset, learner, historyOffset, question],
    queryFn: () =>
      api.history(dataset, learner, historyOffset, question || undefined),
    enabled: Boolean(learner),
  });
  const cohort = useQuery({
    queryKey: ["cohort", dataset, learner],
    queryFn: () => api.cohort(dataset, learner),
    enabled: Boolean(learner),
  });
  const streaks = useQuery({
    queryKey: ["streaks", dataset, learner],
    queryFn: () => api.streaks(dataset, learner),
    enabled: Boolean(learner),
  });
  const summary = overview.data;
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <p className="eyebrow">01 / Observations</p>
          <h1>Evidence before inference.</h1>
          <p>
            Inspect the population, denominator, and uncertainty behind every
            result.
          </p>
        </div>
        <Field label="Find learner ID">
          <input
            value={learnerSearch}
            onChange={(event) => setLearnerSearch(event.target.value)}
            placeholder="Search all learners"
          />
        </Field>
        <Field label="Learner">
          <select
            value={learner}
            onChange={(event) => {
              onLearner(event.target.value);
              setOffset(0);
              setHistoryOffset(0);
            }}
          >
            <option value="">Whole dataset</option>
            {learner &&
            !learners.data?.rows.some((row) => row.id === learner) ? (
              <option value={learner}>{learner}</option>
            ) : null}
            {learners.data?.rows.map((row) => (
              <option key={row.id}>{row.id}</option>
            ))}
          </select>
        </Field>
      </div>
      {overview.isPending ? (
        <Loading />
      ) : overview.error ? (
        <ErrorState error={overview.error} />
      ) : summary ? (
        <>
          <div className="metrics-grid">
            <Metric
              label="All attempts"
              value={percentage(summary.accuracy.estimate)}
              detail={`${number(summary.accuracy.successes)} correct / ${number(summary.accuracy.n)} attempts`}
              accent
            />
            <Metric
              label="First attempts"
              value={percentage(summary.first_attempt_accuracy.estimate)}
              detail={`${number(summary.first_attempt_accuracy.n)} eligible learner/question pairs`}
            />
            <Metric
              label="Observed population"
              value={number(summary.coverage.learners)}
              detail={`${number(summary.coverage.questions)} questions`}
            />
            <Metric
              label="Known duration median"
              value={
                summary.durations.median_ms === null
                  ? "Unknown"
                  : `${number(summary.durations.median_ms / 1000, 1)} s`
              }
              detail={`${number(summary.durations.n)} eligible duration observations`}
            />
          </div>
          {summary.small_sample ? (
            <Notice tone="warning">
              Small sample: fewer than 30 accepted attempts. Wide intervals are
              expected.
            </Notice>
          ) : null}
          {summary.coverage.shifted ? (
            <Notice tone="warning">
              {number(summary.coverage.shifted)} timestamps are shifted.
              Calendar interpretation is unavailable.
            </Notice>
          ) : null}
          {summary.coverage.question_only ? (
            <Notice>
              Legacy exports establish per-question order. Select a question to
              inspect a sequence; a global learning timeline cannot be
              reconstructed.
            </Notice>
          ) : null}
          <div className="two-columns">
            <Panel
              title="Observed performance"
              description="95% Wilson intervals widen with sparse observations."
            >
              <div className="interval-section">
                <p>All attempts</p>
                <IntervalBar value={summary.accuracy} />
                <p>First attempts</p>
                <IntervalBar value={summary.first_attempt_accuracy} />
              </div>
              <p className="footnote">{summary.mastery_interpretation}</p>
            </Panel>
            <Panel
              title="Attempts before first success"
              description="Unsolved questions are censored, not assigned zero retries."
            >
              <div className="mini-metrics">
                <Metric
                  label="Solved"
                  value={number(summary.retries.solved)}
                  detail={`${number(summary.retries.questions)} learner/question histories`}
                />
                <Metric
                  label="Censored"
                  value={number(summary.retries.censored)}
                  detail="No recorded correct answer"
                />
                <Metric
                  label="Median retries"
                  value={number(
                    summary.retries.median_retries_before_success,
                    1,
                  )}
                  detail="Among solved histories"
                />
              </div>
            </Panel>
          </div>
        </>
      ) : null}
      <Panel
        title="Question and skill evidence"
        description="Search and paginate aggregates computed from immutable Parquet partitions."
        action={
          <div className="inline-controls">
            <select
              aria-label="Group dimension"
              value={dimension}
              onChange={(event) => {
                setDimension(event.target.value);
                setOffset(0);
              }}
            >
              <option value="question">Questions</option>
              <option value="skill">Skills</option>
              <option value="learner">Learners</option>
            </select>
            <input
              aria-label="Search group IDs"
              placeholder="Filter IDs"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
            />
          </div>
        }
      >
        {groups.isPending ? (
          <Loading />
        ) : groups.error ? (
          <ErrorState error={groups.error} />
        ) : groups.data ? (
          <>
            <VirtualRows
              rows={groups.data.rows}
              columns={[
                "Identity",
                "Observed accuracy and uncertainty",
                "Learners",
                "Duration coverage",
                "Inspect",
              ]}
              rowKey={(row) => row.id}
              label="Question and skill aggregate table"
              render={(row) => (
                <>
                  {" "}
                  <td>
                    <strong>{row.id}</strong>
                    {row.accuracy.n < 10 ? (
                      <Tag tone="amber">Sparse</Tag>
                    ) : null}
                  </td>
                  <td>
                    <IntervalBar value={row.accuracy} />
                  </td>
                  <td>{number(row.learners)}</td>
                  <td>
                    {number(row.known_durations)} / {number(row.accuracy.n)}
                  </td>
                  <td>
                    {dimension === "question" ? (
                      <button
                        className="text-button"
                        onClick={() => {
                          setQuestion(row.id);
                          setHistoryOffset(0);
                        }}
                      >
                        History
                      </button>
                    ) : dimension === "learner" ? (
                      <button
                        className="text-button"
                        onClick={() => onLearner(row.id)}
                      >
                        Select
                      </button>
                    ) : (
                      <span className="muted">Tagged attempts</span>
                    )}
                  </td>
                </>
              )}
            />
            {groups.data.overlapping_denominators ? (
              <p className="footnote">
                Each multi-skill answer contributes once per explicit tag. Skill
                denominators overlap.
              </p>
            ) : null}
            <Pagination
              offset={offset}
              limit={groups.data.limit}
              total={groups.data.total}
              onChange={setOffset}
            />
          </>
        ) : null}
      </Panel>
      <Panel
        title="Sequence microscope"
        description="The axis states whether observations have real elapsed time or only known event order."
        action={
          <div className="inline-controls">
            <input
              aria-label="Question filter"
              placeholder="Optional question ID"
              value={question}
              onChange={(event) => {
                setQuestion(event.target.value);
                setHistoryOffset(0);
              }}
            />
            <select
              aria-label="Trend axis"
              value={axis}
              onChange={(event) =>
                setAxis(event.target.value as "order" | "time")
              }
            >
              <option value="order">Known event order</option>
              <option value="time">Real elapsed time</option>
            </select>
          </div>
        }
      >
        {!learner ? (
          <Empty title="Choose a learner">
            A sequence is meaningful only within a known learner and order
            domain.
          </Empty>
        ) : trend.isPending ? (
          <Loading />
        ) : trend.error ? (
          <ErrorState error={trend.error} />
        ) : trend.data ? (
          <TrendChart trend={trend.data} />
        ) : null}
        {learner && history.data ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Source sequence</th>
                    <th>Question</th>
                    <th>Answer</th>
                    <th>Source timestamp</th>
                    <th>Session</th>
                    <th>Provenance</th>
                  </tr>
                </thead>
                <tbody>
                  {history.data.rows.map((row) => (
                    <tr key={`${row.source_namespace}:${row.event_id}`}>
                      <td>
                        <code>{row.source_sequence}</code>
                      </td>
                      <td>{row.question_id}</td>
                      <td>
                        <Tag tone={row.correct ? "green" : "rose"}>
                          {row.correct ? "Correct" : "Incorrect"}
                        </Tag>
                      </td>
                      <td>
                        {row.timestamp ? (
                          <>
                            <code>{row.timestamp}</code>
                            {row.time_semantics === "shifted" ? (
                              <Tag tone="amber">Shifted</Tag>
                            ) : null}
                          </>
                        ) : (
                          "Unknown"
                        )}
                      </td>
                      <td>{row.session_id ?? "Unknown"}</td>
                      <td>
                        <Inspector value={row.provenance} title="Source row" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="footnote">{history.data.ordering}</p>
            <Pagination
              offset={historyOffset}
              limit={history.data.limit}
              total={history.data.total}
              onChange={setHistoryOffset}
            />
          </>
        ) : null}
      </Panel>
      {learner ? (
        <div className="two-columns">
          <Panel
            title="Cohort comparison"
            description="Only observed eligible peers. No fabricated benchmark bands."
          >
            {cohort.data ? (
              cohort.data.available === true ? (
                <>
                  <Metric
                    label="Descriptive percentile"
                    value={`${number(Number(cohort.data.percentile), 1)}%`}
                    detail={`${String(cohort.data.eligible_peers)} eligible peers; midrank ties`}
                  />
                  <Inspector value={cohort.data} title="Cohort definition" />
                </>
              ) : (
                <Notice>{String(cohort.data.reason)}</Notice>
              )
            ) : (
              <Loading />
            )}
          </Panel>
          <Panel
            title="Consecutive correct answers"
            description="A streak resets on every incorrect answer within its known order domain."
          >
            {streaks.data ? (
              <Inspector
                value={streaks.data}
                title="Inspect real streaks"
                initiallyOpen
              />
            ) : (
              <Loading />
            )}
          </Panel>
        </div>
      ) : null}
      <DataTools dataset={dataset} learner={learner} />
      {summary ? (
        <Inspector
          value={summary.definitions}
          title="Metric definitions and eligibility"
        />
      ) : null}
    </div>
  );
}

export function CalibrationView({ metrics }: { metrics: Metrics }) {
  return (
    <Panel
      title="Calibration reliability"
      description="A good predicted probability agrees with observed outcomes across supported bins."
    >
      <CalibrationChart metrics={metrics} />
    </Panel>
  );
}
