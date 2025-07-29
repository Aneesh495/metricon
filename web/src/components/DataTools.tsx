import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  Panel,
  Field,
  ErrorState,
  Inspector,
  Notice,
  Loading,
  Pagination,
} from "./Common";

export function DataTools({
  dataset,
  learner,
}: {
  dataset: string;
  learner: string;
}) {
  const [format, setFormat] = useState("json");
  const [window, setWindow] = useState(100);
  const [offset, setOffset] = useState(0);
  const exporting = useMutation({
    mutationFn: () => api.exportDataset(dataset, format),
  });
  const drift = useMutation({
    mutationFn: () => api.drift(dataset, learner, window),
  });
  const sessions = useQuery({
    queryKey: ["sessions", dataset, learner, offset],
    queryFn: () => api.sessions(dataset, learner, offset),
  });
  return (
    <>
      <Panel
        title="Canonical export"
        description="Exports accepted events from this exact immutable dataset version. CSV literal encoding protects spreadsheet cells and round trips through Metricon."
      >
        <div className="toolbar">
          <Field label="Canonical export format">
            <select
              value={format}
              onChange={(event) => setFormat(event.target.value)}
            >
              <option value="json">JSON</option>
              <option value="csv">CSV with literal cells</option>
              <option value="parquet">Parquet</option>
              <option value="ndjson">NDJSON</option>
            </select>
          </Field>
          <button
            disabled={exporting.isPending}
            onClick={() => exporting.mutate()}
          >
            Prepare export
          </button>
        </div>
        {exporting.error ? <ErrorState error={exporting.error} /> : null}
        {exporting.data ? (
          <Notice tone="success">
            <a download href={exporting.data.download_url}>
              Download {exporting.data.filename}
            </a>
            <p>Dataset {exporting.data.dataset_id}</p>
          </Notice>
        ) : null}
      </Panel>
      <Panel
        title="Session behavior"
        description="Only explicit session IDs contribute. Repeated bundle elapsed times count once."
      >
        {sessions.isPending ? (
          <Loading />
        ) : sessions.error ? (
          <ErrorState error={sessions.error} />
        ) : sessions.data ? (
          <>
            <Inspector
              title="Session observations and eligible durations"
              value={sessions.data.rows}
            />
            <Pagination
              offset={offset}
              limit={50}
              total={Number(sessions.data.total)}
              onChange={setOffset}
            />
          </>
        ) : null}
      </Panel>
      <Panel
        title="Inspect distribution drift"
        description="Adjacent observed learner windows. Warnings explain changes and never silently replace a fitted model."
      >
        <div className="toolbar">
          <Field label="Events per drift window">
            <input
              type="number"
              min={30}
              max={10000}
              value={window}
              onChange={(event) => setWindow(Number(event.target.value))}
            />
          </Field>
          <button
            disabled={!learner || drift.isPending}
            onClick={() => drift.mutate()}
          >
            Inspect actual windows
          </button>
        </div>
        {!learner ? (
          <Notice>Choose a learner to define a known order domain.</Notice>
        ) : null}
        {drift.error ? <ErrorState error={drift.error} /> : null}
        {drift.data ? (
          <Inspector title="Window evidence and alerts" value={drift.data} />
        ) : null}
      </Panel>
    </>
  );
}
