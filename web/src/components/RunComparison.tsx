import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Panel, Field, ErrorState, Inspector, Notice } from "./Common";
import { hash } from "../lib/format";

export function RunComparison({ current }: { current: string }) {
  const [right, setRight] = useState("");
  const [leftModel, setLeftModel] = useState("bkt");
  const [rightModel, setRightModel] = useState("global");
  const runs = useQuery({
    queryKey: ["all-experiments"],
    queryFn: api.allExperiments,
  });
  const comparing = useMutation({
    mutationFn: () => api.compare(current, right, leftModel, rightModel),
  });
  return (
    <Panel
      title="Compare immutable runs"
      description="Choose another dataset or model through the API. Paired uncertainty is available only for identical held-out targets."
    >
      <div className="form-grid">
        <Field label="Comparison run">
          <select
            value={right}
            onChange={(event) => setRight(event.target.value)}
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
          <input
            value={leftModel}
            onChange={(event) => setLeftModel(event.target.value)}
          />
        </Field>
        <Field label="Comparison model">
          <input
            value={rightModel}
            onChange={(event) => setRightModel(event.target.value)}
          />
        </Field>
      </div>
      <button
        disabled={!current || !right || comparing.isPending}
        onClick={() => comparing.mutate()}
      >
        Compare saved predictions
      </button>
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
