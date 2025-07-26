import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useJobs } from "../hooks/useLab";
import {
  Empty,
  ErrorState,
  Inspector,
  Loading,
  Panel,
  Tag,
} from "../components/Common";
import { date, hash, number } from "../lib/format";

export function Jobs({
  workspace,
  onArtifact,
}: {
  workspace: string;
  onArtifact: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const jobs = useJobs(workspace);
  const [expanded, setExpanded] = useState("");
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancel(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs", workspace] });
    },
  });
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <p className="eyebrow">07 / Job coordinator</p>
          <h1>Observe the work in flight.</h1>
          <p>
            One coordinator owns metadata transitions and artifact publication.
            Each job pins its dataset.
          </p>
        </div>
      </div>
      <Panel
        title="Workspace jobs"
        description="Interrupted work is explicit. Complete results are committed atomically."
      >
        {jobs.isPending ? (
          <Loading />
        ) : jobs.error ? (
          <ErrorState error={jobs.error} />
        ) : jobs.data?.length ? (
          <div className="job-list">
            {jobs.data.map((job) => (
              <article className="job-card" key={job.id}>
                <header>
                  <div>
                    <Tag
                      tone={
                        job.status === "succeeded"
                          ? "green"
                          : job.status === "failed"
                            ? "rose"
                            : "amber"
                      }
                    >
                      {job.status}
                    </Tag>
                    <strong>{job.kind}</strong>
                    <code>{hash(job.id)}</code>
                  </div>
                  <time>{date(job.created_at)}</time>
                </header>
                <p>
                  {job.kind === "import" && job.status === "succeeded"
                    ? "Full import report is available below."
                    : job.message || "Waiting for the coordinator"}
                </p>
                <progress
                  max={1}
                  value={job.progress}
                  aria-label={`${job.kind} progress`}
                />
                <div className="job-actions">
                  <span className="muted">
                    {number(job.progress * 100, 0)}% / dataset{" "}
                    {hash(job.dataset_id)}
                  </span>
                  {["queued", "running"].includes(job.status) ? (
                    <button
                      className="secondary"
                      disabled={job.cancel_requested || cancel.isPending}
                      onClick={() => cancel.mutate(job.id)}
                    >
                      {job.cancel_requested
                        ? "Cancellation requested"
                        : "Cancel job"}
                    </button>
                  ) : null}
                  {job.result_id && job.kind !== "import" ? (
                    <button
                      className="secondary"
                      onClick={() => onArtifact(job.result_id!)}
                    >
                      Inspect result
                    </button>
                  ) : null}
                  <button
                    className="text-button"
                    onClick={() =>
                      setExpanded((value) => (value === job.id ? "" : job.id))
                    }
                  >
                    Details
                  </button>
                </div>
                {expanded === job.id ? (
                  <Inspector
                    value={{
                      ...job,
                      message:
                        job.kind === "import" && job.status === "succeeded"
                          ? safeParse(job.message)
                          : job.message,
                    }}
                    title="Job record"
                    initiallyOpen
                  />
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <Empty title="The queue is empty">
            Imports and experiments run here. A blank workspace does not enqueue
            demonstration data.
          </Empty>
        )}
        {cancel.error ? <ErrorState error={cancel.error} /> : null}
      </Panel>
    </div>
  );
}

function safeParse(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}
