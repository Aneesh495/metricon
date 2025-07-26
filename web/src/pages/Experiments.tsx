import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Play } from "lucide-react";
import { PredictionInspector } from "../components/PredictionInspector";
import { api } from "../api/client";
import type { ExperimentOptions } from "../api/contracts";
import { CalibrationView } from "./Observations";
import {
  CheckField,
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
import { date, hash, number } from "../lib/format";

export function Experiments({
  workspace,
  dataset,
  onArtifact,
  onJob,
}: {
  workspace: string;
  dataset: string;
  onArtifact: (id: string) => void;
  onJob: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [options, setOptions] = useState<ExperimentOptions>({
    seed: 2026,
    split: "forward",
    bootstrap_repetitions: 200,
    bkt_starts: 3,
    online_updates: true,
    ablations: true,
    calibration: true,
  });
  const [selected, setSelected] = useState("");
  const [foldIndex, setFoldIndex] = useState(0);
  const [modelName, setModelName] = useState("global");
  const artifacts = useQuery({
    queryKey: ["artifacts", dataset, "experiment"],
    queryFn: () => api.artifacts(dataset, "experiment"),
  });
  const artifactId = selected || artifacts.data?.[0]?.id || "";
  const report = useQuery({
    queryKey: ["report", artifactId],
    queryFn: () => api.report(artifactId),
    enabled: Boolean(artifactId),
  });
  const mutation = useMutation({
    mutationFn: () => api.experiment(workspace, options),
    onSuccess: (job) => {
      onJob(job.id);
      void queryClient.invalidateQueries({ queryKey: ["jobs", workspace] });
    },
  });
  const fold = report.data?.folds[foldIndex];
  const model = fold?.models[modelName];
  function change(values: Partial<ExperimentOptions>) {
    setOptions((current) => ({ ...current, ...values }));
  }
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <p className="eyebrow">03 / Experiment bench</p>
          <h1>A prediction earns its number.</h1>
          <p>
            Freeze the split, fit on training, calibrate on validation, then
            evaluate untouched test rows.
          </p>
        </div>
        <FlaskConical size={40} className="intro-icon" />
      </div>
      <Panel
        title="Reproducible run"
        description="Every model is evaluated on the same rows. Baselines and negative results remain visible."
        action={
          <button
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            <Play size={16} />
            Run experiment
          </button>
        }
      >
        <div className="form-grid">
          <Field label="Evaluation design">
            <select
              value={options.split}
              onChange={(event) =>
                change({
                  split: event.target.value as ExperimentOptions["split"],
                })
              }
            >
              <option value="forward">Per-learner forward chaining</option>
              <option value="learner">Learner held out</option>
              <option value="rolling">Rolling temporal folds</option>
            </select>
          </Field>
          <Field label="Seed">
            <input
              type="number"
              value={options.seed}
              onChange={(event) => change({ seed: Number(event.target.value) })}
            />
          </Field>
          <Field label="Learner bootstrap draws">
            <input
              type="number"
              min={20}
              max={5000}
              value={options.bootstrap_repetitions}
              onChange={(event) =>
                change({ bootstrap_repetitions: Number(event.target.value) })
              }
            />
          </Field>
          <Field label="BKT initialization starts">
            <input
              type="number"
              min={1}
              max={10}
              value={options.bkt_starts}
              onChange={(event) =>
                change({ bkt_starts: Number(event.target.value) })
              }
            />
          </Field>
        </div>
        <div className="checks">
          <CheckField
            label="Update online history"
            checked={options.online_updates}
            onChange={(value) => change({ online_updates: value })}
            hint="Only earlier observed answers update later state; fitted parameters stay frozen."
          />
          <CheckField
            label="Validation-only calibration"
            checked={options.calibration}
            onChange={(value) => change({ calibration: value })}
          />
          <CheckField
            label="Scientific ablations"
            checked={options.ablations}
            onChange={(value) => change({ ablations: value })}
            hint="Skills, time, shrinkage, forgetting and multi-skill policy."
          />
        </div>
        <Notice>
          Sessions and timestamp ties stay together. Logistic regularization
          uses a fixed candidate list and validation log loss. IRT appears only
          when cohort eligibility is met.
        </Notice>
        {mutation.error ? <ErrorState error={mutation.error} /> : null}
      </Panel>
      <Panel
        title="Committed experiments"
        description="A report exists only after all outputs are hashed and published."
        action={
          <select
            aria-label="Choose experiment"
            value={artifactId}
            onChange={(event) => {
              setSelected(event.target.value);
              setFoldIndex(0);
            }}
          >
            <option value="">Choose a committed run</option>
            {artifacts.data?.map((artifact) => (
              <option key={artifact.id} value={artifact.id}>
                {hash(artifact.id)} / {date(artifact.created_at)}
              </option>
            ))}
          </select>
        }
      >
        {!artifactId ? (
          <Empty title="No committed run yet">
            Launch an experiment or inspect the job queue. Incomplete runs never
            become research results.
          </Empty>
        ) : report.isPending ? (
          <Loading label="Reading hashed research artifacts" />
        ) : report.error ? (
          <ErrorState error={report.error} />
        ) : report.data && fold ? (
          <>
            <div className="report-meta">
              <Tag tone="green">Split audited</Tag>
              <code>{hash(fold.split_hash, 24)}</code>
              <select
                aria-label="Select temporal fold"
                value={foldIndex}
                onChange={(event) => setFoldIndex(Number(event.target.value))}
              >
                {report.data.folds.map((_, index) => (
                  <option key={index} value={index}>
                    Fold {index + 1}
                  </option>
                ))}
              </select>
              <button
                className="secondary"
                onClick={() => onArtifact(artifactId)}
              >
                Inspect lineage
              </button>
              <a
                className="button-link secondary"
                href={api.fileURL(artifactId, "report.md")}
                download
              >
                Download report
              </a>
            </div>
            <div className="metrics-grid">
              <Metric
                label="Training"
                value={number(fold.audit.counts.train)}
                detail="Parameters and vocabulary"
              />
              <Metric
                label="Validation"
                value={number(fold.audit.counts.validation)}
                detail="Hyperparameters and calibration"
              />
              <Metric
                label="Test"
                value={number(fold.audit.counts.test)}
                detail="Final performance comparison"
              />
              <Metric
                label="Runtime"
                value={`${number(report.data.runtime_seconds, 1)} s`}
                detail={`${number(report.data.peak_process_rss_bytes / 1024 ** 2, 0)} MB process peak RSS`}
              />
            </div>
            <div className="table-scroll">
              <table className="model-table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Test n</th>
                    <th>Log loss</th>
                    <th>Brier</th>
                    <th>AUROC</th>
                    <th>Calibrated loss</th>
                    <th>Inspect</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(fold.models).map(([name, result]) => (
                    <tr
                      key={name}
                      className={name === modelName ? "selected-row" : ""}
                    >
                      <td>
                        <strong>{name}</strong>
                        {name === fold.selected_logistic ? (
                          <Tag tone="green">Validation choice</Tag>
                        ) : null}
                      </td>
                      {result.eligible && result.test ? (
                        <>
                          <td>{number(result.test.n)}</td>
                          <td>{number(result.test.log_loss, 5)}</td>
                          <td>{number(result.test.brier, 5)}</td>
                          <td>{number(result.test.auroc, 4)}</td>
                          <td>{number(result.calibrated_test?.log_loss, 5)}</td>
                          <td>
                            <button
                              className="text-button"
                              onClick={() => setModelName(name)}
                            >
                              Diagnostics
                            </button>
                          </td>
                        </>
                      ) : (
                        <td colSpan={6} className="muted">
                          Unavailable: {result.reason}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="footnote">
              {fold.selection_rule}. Lower loss and Brier are better. AUROC is
              unknown when only one answer class is present.
            </p>
            {model?.test ? (
              <>
                <CalibrationView metrics={model.test} />
                <PredictionInspector
                  key={`${artifactId}:${modelName}`}
                  artifact={artifactId}
                  model={modelName}
                />
                <div className="two-columns">
                  <Panel
                    title={`${modelName}: fit diagnostics`}
                    description="A successful optimizer does not establish model adequacy."
                  >
                    <Inspector
                      value={model.diagnostics}
                      title="Convergence and support"
                      initiallyOpen
                    />
                  </Panel>
                  <Panel
                    title="Learner-cluster uncertainty"
                    description="Whole histories are resampled together."
                  >
                    <Inspector
                      value={model.cluster_intervals}
                      title="Confidence intervals"
                      initiallyOpen
                    />
                  </Panel>
                </div>
                <Inspector
                  value={fold.comparisons_to_global[modelName]}
                  title="Paired comparison against global baseline"
                />
                <Inspector
                  value={model.calibration_parameters}
                  title="Validation-only calibration parameters"
                />
              </>
            ) : null}
            <Inspector
              value={{
                configuration: report.data.configuration,
                environment: report.data.environment,
                feature_version: report.data.feature_version,
                parameter_policy: fold.parameter_policy,
                bundle_policy: fold.bundle_policy,
                memory_method: report.data.memory_method,
              }}
              title="Reproduction contract"
            />
          </>
        ) : null}
      </Panel>
    </div>
  );
}
