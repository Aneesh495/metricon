import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Report } from "../api/contracts";
import { Panel, Field, ErrorState, Inspector, Notice } from "./Common";
import { hash } from "../lib/format";

function eligibleModels(report: Report | undefined, fold: number) {
  return Object.entries(report?.folds[fold]?.models ?? {})
    .filter(([, result]) => result.eligible)
    .map(([name]) => name);
}

export function RunComparison({
  current,
  fold = 0,
}: {
  current: string;
  fold?: number;
}) {
  const [right, setRight] = useState("");
  const [leftChoice, setLeftChoice] = useState("bkt");
  const [rightChoice, setRightChoice] = useState("global");
  const runs = useQuery({
    queryKey: ["all-experiments"],
    queryFn: api.allExperiments,
  });
  const leftReport = useQuery({
    queryKey: ["report", current],
    queryFn: () => api.report(current),
    enabled: Boolean(current),
  });
  const rightReport = useQuery({
    queryKey: ["report", right],
    queryFn: () => api.report(right),
    enabled: Boolean(right),
  });
  const leftNames = eligibleModels(leftReport.data, fold);
  const rightNames = eligibleModels(rightReport.data, fold);
  const leftModel = leftNames.includes(leftChoice)
    ? leftChoice
    : (leftNames[0] ?? "");
  const rightModel = rightNames.includes(rightChoice)
    ? rightChoice
    : (rightNames[0] ?? "");
  const comparing = useMutation({
    mutationFn: () => api.compare(current, right, leftModel, rightModel, fold),
  });
  return (
    <Panel
      title="Compare immutable runs"
      description={`Compare temporal fold ${fold + 1} in both runs. Paired uncertainty requires identical held-out targets.`}
    >
      <div className="form-grid">
        <Field label="Comparison run">
          <select
            value={right}
            disabled={comparing.isPending}
            onChange={(event) => {
              setRight(event.target.value);
              comparing.reset();
            }}
          >
            <option value="">Select an actual run</option>
            {runs.data?.map((run) => (
              <option key={run.id} value={run.id}>
                {run.workspace_name} / {hash(run.dataset_id)} / {hash(run.id)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Current run model">
          <select
            value={leftModel}
            disabled={!leftNames.length || comparing.isPending}
            onChange={(event) => {
              setLeftChoice(event.target.value);
              comparing.reset();
            }}
          >
            {leftNames.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </Field>
        <Field label="Comparison model">
          <select
            value={rightModel}
            disabled={!rightNames.length || comparing.isPending}
            onChange={(event) => {
              setRightChoice(event.target.value);
              comparing.reset();
            }}
          >
            {rightNames.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </Field>
      </div>
      <button
        disabled={!leftModel || !rightModel || comparing.isPending}
        onClick={() => comparing.mutate()}
      >
        Compare saved predictions
      </button>
      {runs.error ? (
        <ErrorState error={runs.error} retry={() => void runs.refetch()} />
      ) : null}
      {leftReport.error ? <ErrorState error={leftReport.error} /> : null}
      {right && rightReport.error ? (
        <ErrorState error={rightReport.error} />
      ) : null}
      {right && rightReport.data && !rightNames.length ? (
        <Notice>
          This comparison run has no eligible fitted model in temporal fold{" "}
          {fold + 1}. Choose another run or fold.
        </Notice>
      ) : null}
      {comparing.error ? <ErrorState error={comparing.error} /> : null}
      {comparing.data ? (
        <>
          <Notice>{String(comparing.data.interpretation)}</Notice>
          <Inspector
            title="Observed comparison, metrics, calibration and paired uncertainty"
            value={comparing.data}
          />
        </>
      ) : null}
    </Panel>
  );
}
