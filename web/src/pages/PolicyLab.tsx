import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  Empty,
  ErrorState,
  Field,
  Inspector,
  Loading,
  Metric,
  Notice,
  Panel,
  Tag,
} from "../components/Common";
import { hash, number, parseObject, percentage } from "../lib/format";
import type { Action } from "../api/contracts";

function ActionList({
  actions,
  timed,
  workspace,
  dataset,
}: {
  actions: Action[];
  timed: boolean;
  workspace: string;
  dataset: string;
}) {
  function artifactLink(artifact: string) {
    const query = new URLSearchParams(window.location.search);
    query.set("workspace", workspace);
    query.set("version", dataset);
    query.set("tab", "provenance");
    query.set("artifact", artifact);
    return `?${query.toString()}`;
  }
  return (
    <div className="action-list">
      {actions.map((action, index) => (
        <article className="study-action" key={action.question_id}>
          <div className="action-number">
            {String(index + 1).padStart(2, "0")}
          </div>
          <div className="action-detail">
            <div>
              <strong>{action.question_id}</strong>
              <span className="muted">
                {action.skills.join(", ") || "Skills unknown"}
              </span>
            </div>
            <div className="factor-bars">
              {Object.entries(action.contributions).map(([name, value]) => (
                <span
                  key={name}
                  className={value < 0 ? "factor negative" : "factor"}
                  title={`${name}: ${value.toFixed(4)}`}
                >
                  {name.replaceAll("_", " ")} <code>{number(value, 3)}</code>
                </span>
              ))}
            </div>
            {action.model_artifact_id ? (
              <a href={artifactLink(action.model_artifact_id)}>
                Inspect fitted run {hash(action.model_artifact_id)}
              </a>
            ) : null}
            <small>
              Observed performance{" "}
              {percentage(action.observed_performance.mean)}, interval{" "}
              {percentage(action.observed_performance.lower)} to{" "}
              {percentage(action.observed_performance.upper)}, n=
              {action.observed_performance.n}
            </small>
          </div>
          <div className="action-time">
            {timed && action.planned_seconds ? (
              <>
                <strong>{number(action.planned_seconds, 0)}s</strong>
                <small>n={action.duration?.n} durations</small>
              </>
            ) : (
              <Tag tone="amber">Time unknown</Tag>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

export function PolicyLab({
  workspace,
  dataset,
  learner,
  onJob,
}: {
  workspace: string;
  dataset: string;
  learner: string;
  onJob: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [modelArtifact, setModelArtifact] = useState("");
  const [regime, setRegime] = useState("nominal");
  const [budgetMode, setBudgetMode] = useState("time");
  const models = useQuery({
    queryKey: ["artifacts", dataset, "experiment"],
    queryFn: () => api.artifacts(dataset, "experiment"),
  });
  const [budget, setBudget] = useState(15);
  const [priorities, setPriorities] = useState("{}");
  const [prerequisites, setPrerequisites] = useState("{}");
  const [seed, setSeed] = useState(2026);
  const [repetitions, setRepetitions] = useState(200);
  const [skills, setSkills] = useState("algebra,logic,probability");
  const [duration, setDuration] = useState(60);
  const [simulationId, setSimulationId] = useState("");
  const planner = useMutation({
    mutationFn: () =>
      api.plan(dataset, {
        learner_id: learner,
        budget_seconds: budget * 60,
        priorities: parseObject(priorities, "Priorities"),
        prerequisites: parseObject(prerequisites, "Prerequisites"),
        model_artifact_id: modelArtifact || null,
      }),
  });
  const simulationJob = useMutation({
    mutationFn: () =>
      api.simulate(
        workspace,
        {
          seed,
          repetitions,
          regime,
          budget_mode: budgetMode,
          budget_seconds: budget * 60,
          skills: skills
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          assumed_duration_seconds: duration,
        },
        dataset,
      ),
    onSuccess: (job) => {
      onJob(job.id);
      void queryClient.invalidateQueries({ queryKey: ["jobs", workspace] });
    },
  });
  const simulations = useQuery({
    queryKey: ["artifacts", dataset, "simulation"],
    queryFn: () => api.artifacts(dataset, "simulation"),
  });
  const artifactId = simulationId || simulations.data?.[0]?.id || "";
  const simulation = useQuery({
    queryKey: ["simulation", artifactId],
    queryFn: () => api.simulation(artifactId),
    enabled: Boolean(artifactId),
  });
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <p className="eyebrow">05 / Policy laboratory</p>
          <h1>A plan with inspectable reasons.</h1>
          <p>
            Observed evidence informs planning. Simulated knowledge belongs to a
            separate experiment.
          </p>
        </div>
      </div>
      <Panel
        title="Observed-history study planner"
        description="Rank actions by performance uncertainty, observed deficits, recent repetitions and your priorities."
        action={
          <button
            disabled={!learner || planner.isPending}
            onClick={() => planner.mutate()}
          >
            Build study plan
          </button>
        }
      >
        <div className="form-grid">
          <Field label="Time budget in minutes">
            <input
              type="number"
              min={1}
              max={1440}
              value={budget}
              onChange={(event) => setBudget(Number(event.target.value))}
            />
          </Field>
          <Field label="Selected learner">
            <input
              readOnly
              value={learner || "Select a learner in Observations"}
            />
          </Field>
          <Field
            label="Skill priorities as JSON"
            hint='Example: {"probability": 2, "logic": 1}'
          >
            <textarea
              rows={3}
              value={priorities}
              onChange={(event) => setPriorities(event.target.value)}
            />
          </Field>
          <Field
            label="Prerequisites as JSON"
            hint='Example: {"calculus": ["algebra"]}'
          >
            <textarea
              rows={3}
              value={prerequisites}
              onChange={(event) => setPrerequisites(event.target.value)}
            />
          </Field>
        </div>
        <Notice>
          Timed actions require at least three known item-duration observations.
          Missing or bundle-level duration never becomes an invented
          per-question time estimate.
        </Notice>
        {planner.error ? <ErrorState error={planner.error} /> : null}
        {planner.data ? (
          <>
            <div className="mini-metrics">
              <Metric
                label="Budget"
                value={`${number(planner.data.budget_seconds / 60, 1)} min`}
                detail="User supplied"
              />
              <Metric
                label="Allocated"
                value={`${number(planner.data.planned_seconds / 60, 1)} min`}
                detail="Observed median durations"
              />
              <Metric
                label="Remaining"
                value={`${number(planner.data.remaining_seconds / 60, 1)} min`}
                detail="No fabricated filler actions"
              />
            </div>
            {planner.data.actions.length ? (
              <ActionList
                actions={planner.data.actions}
                timed
                workspace={workspace}
                dataset={dataset}
              />
            ) : (
              <Empty title="No supported timed actions">
                Inspect untimed suggestions below or import reliable item-level
                duration data.
              </Empty>
            )}
            {planner.data.unknown_time_actions.length ? (
              <>
                <h3>Ranked suggestions with unknown time</h3>
                <ActionList
                  actions={planner.data.unknown_time_actions.slice(0, 15)}
                  timed={false}
                  workspace={workspace}
                  dataset={dataset}
                />
              </>
            ) : null}
            {planner.data.blocked_actions.length ? (
              <Inspector
                value={planner.data.blocked_actions}
                title="Prerequisite blocks"
              />
            ) : null}
            <Inspector
              value={{
                method: planner.data.method,
                limits: planner.data.limits,
                configuration: planner.data.configuration,
                plan_hash: planner.data.plan_hash,
                recent_order_available: planner.data.recent_order_available,
              }}
              title="Plan assumptions and factors"
            />
          </>
        ) : null}
      </Panel>
      <Panel
        title="Model state for planning"
        description="Optional fitted BKT replay of observed history. Its posterior is an estimate, not certified knowledge."
      >
        <Field label="Planner model run">
          <select
            value={modelArtifact}
            onChange={(event) => setModelArtifact(event.target.value)}
          >
            <option value="">Observed uncertainty only</option>
            {models.data?.map((run) => (
              <option key={run.id} value={run.id}>
                {hash(run.id, 20)}
              </option>
            ))}
          </select>
        </Field>
      </Panel>
      <Panel
        title="Synthetic policy experiment"
        eyebrow="Simulation only"
        description="Policies receive answer-conditioned beliefs, never the simulated latent state."
        action={
          <button
            disabled={simulationJob.isPending}
            onClick={() => simulationJob.mutate()}
          >
            Compare policies
          </button>
        }
      >
        <div className="form-grid">
          <Field label="Simulator regime">
            <select
              value={regime}
              onChange={(event) => setRegime(event.target.value)}
            >
              <option value="nominal">Nominal BKT environment</option>
              <option value="slow_learning">Slow learning</option>
              <option value="forgetting">Forgetting</option>
              <option value="misspecified">Deliberately misspecified</option>
            </select>
          </Field>
          <Field label="Equal simulation budget">
            <select
              value={budgetMode}
              onChange={(event) => setBudgetMode(event.target.value)}
            >
              <option value="time">Same time allowance</option>
              <option value="questions">Same question allowance</option>
            </select>
          </Field>
          <Field label="Simulation skill IDs">
            <input
              value={skills}
              onChange={(event) => setSkills(event.target.value)}
            />
          </Field>
          <Field label="Assumed seconds per simulated answer">
            <input
              type="number"
              min={1}
              value={duration}
              onChange={(event) => setDuration(Number(event.target.value))}
            />
          </Field>
          <Field label="Monte Carlo repetitions">
            <input
              type="number"
              min={2}
              max={5000}
              value={repetitions}
              onChange={(event) => setRepetitions(Number(event.target.value))}
            />
          </Field>
          <Field label="Simulation seed">
            <input
              type="number"
              value={seed}
              onChange={(event) => setSeed(Number(event.target.value))}
            />
          </Field>
        </div>
        <Notice tone="warning">
          These duration and learning parameters are explicit simulation
          assumptions. A winning synthetic policy does not prove a benefit for
          actual learners.
        </Notice>
        {simulationJob.error ? (
          <ErrorState error={simulationJob.error} />
        ) : null}
      </Panel>
      <Panel
        title="Committed simulation results"
        action={
          <select
            aria-label="Simulation artifact"
            value={artifactId}
            onChange={(event) => setSimulationId(event.target.value)}
          >
            <option value="">Choose a simulation</option>
            {simulations.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {hash(row.id, 20)}
              </option>
            ))}
          </select>
        }
      >
        {!artifactId ? (
          <Empty title="No simulation artifact yet">
            Run a reproducible comparison of random, weakest, uncertainty,
            spaced and budget policies.
          </Empty>
        ) : simulation.isPending ? (
          <Loading />
        ) : simulation.error ? (
          <ErrorState error={simulation.error} />
        ) : simulation.data ? (
          <>
            <Tag tone="amber">Synthetic latent state</Tag>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Policy</th>
                    <th>Simulated known fraction</th>
                    <th>Monte Carlo interval</th>
                    <th>Observed simulated accuracy</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(simulation.data.summaries).map(
                    ([policy, result]) => (
                      <tr key={policy}>
                        <td>{policy}</td>
                        <td>
                          {percentage(
                            result.simulated_latent_known_fraction?.mean,
                          )}
                        </td>
                        <td>
                          {percentage(
                            result.simulated_latent_known_fraction?.lower,
                          )}{" "}
                          to{" "}
                          {percentage(
                            result.simulated_latent_known_fraction?.upper,
                          )}
                        </td>
                        <td>{percentage(result.accuracy?.mean)}</td>
                        <td>{number(result.actions?.mean, 1)}</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
            <Inspector
              value={simulation.data.paired_comparisons}
              title="Paired Monte Carlo comparisons"
            />
            <Inspector
              value={simulation.data.assumptions}
              title="Environment and information assumptions"
              initiallyOpen
            />
            <Inspector
              value={simulation.data.trajectories}
              title="Inspect simulated trajectories"
            />
          </>
        ) : null}
      </Panel>
    </div>
  );
}
