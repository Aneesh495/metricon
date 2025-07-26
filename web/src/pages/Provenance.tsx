import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, GitBranch, ShieldCheck } from "lucide-react";
import { LineageGraph } from "../components/LineageGraph";
import { api } from "../api/client";
import {
  Empty,
  ErrorState,
  Inspector,
  Loading,
  Metric,
  Notice,
  Panel,
  Tag,
} from "../components/Common";
import { hash, number } from "../lib/format";

export function Provenance({
  dataset,
  requestedArtifact,
}: {
  dataset: string;
  requestedArtifact: string;
}) {
  const [selected, setSelected] = useState("");
  const source = useQuery({
    queryKey: ["dataset", dataset],
    queryFn: () => api.dataset(dataset),
  });
  const audit = useQuery({
    queryKey: ["audit", dataset],
    queryFn: () => api.audit(dataset),
  });
  const artifacts = useQuery({
    queryKey: ["artifacts", dataset],
    queryFn: () => api.artifacts(dataset),
  });
  const id = selected || requestedArtifact || artifacts.data?.[0]?.id || "";
  const artifact = useQuery({
    queryKey: ["artifact", id],
    queryFn: () => api.artifact(id),
    enabled: Boolean(id),
  });
  const verify = useMutation({ mutationFn: () => api.verify(id) });
  const datasetVerify = useMutation({
    mutationFn: () => api.audit(dataset, true),
  });
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <p className="eyebrow">06 / Provenance</p>
          <h1>Follow the result to its source.</h1>
          <p>
            Content hashes connect original bytes, normalized partitions, splits
            and fitted models.
          </p>
        </div>
        <GitBranch size={40} className="intro-icon" />
      </div>
      <Panel
        title="Immutable dataset"
        description="Workspace pointers are transactional. Published partition files are immutable."
        action={
          <button
            className="secondary"
            disabled={datasetVerify.isPending}
            onClick={() => datasetVerify.mutate()}
          >
            <ShieldCheck size={16} />
            Verify partition checksums
          </button>
        }
      >
        {source.isPending ? (
          <Loading />
        ) : source.error ? (
          <ErrorState error={source.error} />
        ) : source.data ? (
          <>
            <div className="metrics-grid">
              <Metric
                label="Accepted canonical events"
                value={number(source.data.row_count)}
                detail="Unique source/event identities"
              />
              <Metric
                label="Parquet partitions"
                value={number(source.data.partition_count)}
                detail="Bounded row-group scans"
              />
              <Metric
                label="Schema"
                value={source.data.schema_version}
                detail={source.data.source.format}
              />
              <Metric
                label="Source namespace"
                value={source.data.source.namespace}
                detail="Identity ownership"
              />
            </div>
            <div className="hash-block">
              <span>Dataset version</span>
              <code>{dataset}</code>
              <span>Original source SHA-256</span>
              <code>{source.data.source.sha256}</code>
            </div>
            <Inspector
              value={source.data.quality}
              title="Import report"
              initiallyOpen
            />
          </>
        ) : null}
        {audit.data ? (
          <Inspector value={audit.data} title="Dataset quality audit" />
        ) : null}
        {datasetVerify.data ? (
          <Notice tone={datasetVerify.data.valid ? "success" : "danger"}>
            {datasetVerify.data.valid
              ? "All committed partition checksums match."
              : "Dataset verification found invalid partitions."}
          </Notice>
        ) : null}
        {datasetVerify.error ? (
          <ErrorState error={datasetVerify.error} />
        ) : null}
      </Panel>
      <Panel
        title="Artifact lineage"
        description="A change to input, split, feature vocabulary or fitted parameters produces a different result identity."
        action={
          <select
            aria-label="Artifact selection"
            value={id}
            onChange={(event) => setSelected(event.target.value)}
          >
            <option value="">Choose artifact</option>
            {artifacts.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {row.kind} / {hash(row.id)}
              </option>
            ))}
          </select>
        }
      >
        {!id ? (
          <Empty title="No committed artifacts">
            Run analytics, experiments or simulations to create inspectable
            hashed outputs.
          </Empty>
        ) : artifact.isPending ? (
          <Loading />
        ) : artifact.error ? (
          <ErrorState error={artifact.error} />
        ) : artifact.data ? (
          <>
            <div className="report-meta">
              <Tag>{artifact.data.kind}</Tag>
              <code>{hash(id, 24)}</code>
              <button
                className="secondary"
                disabled={verify.isPending}
                onClick={() => verify.mutate()}
              >
                Verify artifact
              </button>
            </div>
            {verify.data ? (
              <Notice tone={verify.data.valid ? "success" : "danger"}>
                {verify.data.valid
                  ? "Every committed artifact checksum matches."
                  : `Invalid files: ${verify.data.invalid_files.join(", ")}`}
              </Notice>
            ) : null}
            {verify.error ? <ErrorState error={verify.error} /> : null}
            <LineageGraph artifact={id} />
            <div className="lineage-list">
              {artifact.data.lineage.map((edge) => (
                <div
                  className="lineage-edge"
                  key={`${edge.child}:${edge.parent}:${edge.role}`}
                >
                  <code title={edge.parent}>{hash(edge.parent, 20)}</code>
                  <span>{edge.role}</span>
                  <i aria-hidden="true">→</i>
                  <code title={edge.child}>{hash(edge.child, 20)}</code>
                </div>
              ))}
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Committed file</th>
                    <th>SHA-256</th>
                    <th>Export</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(artifact.data.manifest.files).map(
                    ([name, checksum]) => (
                      <tr key={name}>
                        <td>
                          <code>{name}</code>
                        </td>
                        <td>
                          <code title={checksum}>{hash(checksum, 24)}</code>
                        </td>
                        <td>
                          <a
                            className="text-button"
                            href={api.fileURL(id, name)}
                            download
                          >
                            <Download size={14} />
                            Download
                          </a>
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
            <Inspector
              value={artifact.data.manifest.metadata}
              title="Artifact metadata"
            />
            <p className="footnote">
              Reports include dependency lock hash, seed, dataset and split
              hashes, feature versions, fit diagnostics, runtime and memory
              measurements.
            </p>
          </>
        ) : null}
      </Panel>
    </div>
  );
}
