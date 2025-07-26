import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Database, Download, FileUp } from "lucide-react";
import { api } from "../api/client";
import type { ImportOptions, Preview, Upload } from "../api/contracts";
import {
  ErrorState,
  Field,
  Inspector,
  Metric,
  Notice,
  Panel,
  Tag,
} from "../components/Common";
import { bytes, downloadJSON, hash, number } from "../lib/format";

export function ImportLab({
  workspace,
  onJob,
}: {
  workspace: string;
  onJob: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [options, setOptions] = useState<ImportOptions>({
    format: "legacy",
    namespace: "browser-export",
    learner: "local-learner",
  });
  const [upload, setUpload] = useState<Upload | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [text, setText] = useState("");
  const [migration, setMigration] = useState<string | null>(null);
  const [backupDone, setBackupDone] = useState(false);
  const [localError, setLocalError] = useState<unknown>(null);
  const previewMutation = useMutation({
    mutationFn: async (file: File) => {
      const result = await api.upload(file);
      const sample = await api.preview(result.upload_id, options);
      return { result, sample };
    },
    onSuccess: ({ result, sample }) => {
      setUpload(result);
      setPreview(sample);
    },
  });
  const importMutation = useMutation({
    mutationFn: () => api.import(workspace, upload!.upload_id, options),
    onSuccess: (job) => {
      void queryClient.invalidateQueries({ queryKey: ["jobs", workspace] });
      onJob(job.id);
    },
  });
  function changeOptions(change: Partial<ImportOptions>) {
    setOptions((value) => ({ ...value, ...change }));
    setPreview(null);
    setUpload(null);
  }
  function fileSelected(file: File | undefined) {
    if (!file) return;
    setMigration(null);
    setBackupDone(false);
    setLocalError(null);
    setPreview(null);
    previewMutation.mutate(file);
  }
  function readBrowserStorage() {
    try {
      const stored = localStorage.getItem("quizSubmissions");
      if (stored === null)
        throw new Error(
          "This browser origin has no quizSubmissions key. Export JSON from the original origin and upload it here.",
        );
      const parsed: unknown = JSON.parse(stored);
      if (!parsed || typeof parsed !== "object")
        throw new Error(
          "Browser storage does not contain a submission object.",
        );
      setMigration(stored);
      setBackupDone(false);
      setLocalError(null);
      previewMutation.mutate(
        new File([stored], "browser-storage-backup.json", {
          type: "application/json",
        }),
      );
    } catch (error) {
      setLocalError(error);
    }
  }
  function backup() {
    if (!migration) return;
    downloadJSON(
      JSON.parse(migration),
      "metricon-original-browser-backup.json",
    );
    setBackupDone(true);
  }
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <p className="eyebrow">02 / Import laboratory</p>
          <h1>Keep the source. Inspect the contract.</h1>
          <p>
            Preview schema and quality before publishing a new immutable dataset
            version.
          </p>
        </div>
        <Database size={40} className="intro-icon" />
      </div>
      <div className="two-columns">
        <Panel
          title="Source adapter"
          description="Namespaces identify stable event IDs. Reusing an ID with changed content creates a conflict."
        >
          <div className="form-grid">
            <Field label="Format">
              <select
                value={options.format}
                onChange={(event) =>
                  changeOptions({
                    format: event.target.value as ImportOptions["format"],
                  })
                }
              >
                <option value="legacy">Original browser JSON</option>
                <option value="ndjson">Canonical NDJSON</option>
                <option value="csv">Canonical CSV</option>
                <option value="parquet">Canonical Parquet</option>
                <option value="json">Canonical JSON array</option>
              </select>
            </Field>
            <Field label="Source namespace">
              <input
                value={options.namespace}
                onChange={(event) =>
                  changeOptions({ namespace: event.target.value })
                }
              />
            </Field>
            <Field
              label="Local learner pseudonym"
              hint="Used when the original export does not identify a learner."
            >
              <input
                value={options.learner}
                onChange={(event) =>
                  changeOptions({ learner: event.target.value })
                }
              />
            </Field>
          </div>
          <label className="upload-zone">
            <FileUp size={26} />
            <strong>Choose a source file</strong>
            <span>JSON, CSV, NDJSON or Parquet</span>
            <input
              type="file"
              accept=".json,.csv,.ndjson,.jsonl,.parquet"
              onChange={(event) => fileSelected(event.target.files?.[0])}
            />
          </label>
          <Field label="Or paste an export">
            <textarea
              rows={6}
              placeholder="Paste the original question-keyed export"
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </Field>
          <button
            className="secondary"
            disabled={!text.trim() || previewMutation.isPending}
            onClick={() =>
              fileSelected(
                new File([text], "pasted-export.json", {
                  type: "application/json",
                }),
              )
            }
          >
            Preview pasted source
          </button>
        </Panel>
        <Panel
          title="Explicit browser migration"
          description="The original application stored submissions under quizSubmissions."
        >
          <Notice>
            Storage is read only when you click preview. The original key is
            retained. Migration requires a downloaded backup and a reviewed
            sample.
          </Notice>
          <p className="muted">
            Browser storage belongs to an origin. If the old application used a
            different URL, export its JSON there and upload the file. Older
            versions also wrote sample data into this key, so verify that the
            preview is your history.
          </p>
          <div className="button-row">
            <button
              className="secondary"
              disabled={
                options.format !== "legacy" || previewMutation.isPending
              }
              onClick={readBrowserStorage}
            >
              Preview browser storage
            </button>
            {migration ? (
              <button className="secondary" onClick={backup}>
                <Download size={16} />
                Download original backup
              </button>
            ) : null}
          </div>
          {backupDone ? <Tag tone="green">Backup downloaded</Tag> : null}
          <div className="contract-note">
            <strong>Unknown stays unknown.</strong>
            <p>
              Original exports contain no timestamps, durations or global
              chronology. Metricon preserves per-question sequence and never
              creates dates.
            </p>
          </div>
        </Panel>
      </div>
      {localError ? <ErrorState error={localError} /> : null}
      {previewMutation.error ? (
        <ErrorState error={previewMutation.error} />
      ) : null}
      {importMutation.error ? (
        <ErrorState error={importMutation.error} />
      ) : null}
      {preview && upload ? (
        <Panel
          title="Schema preview"
          eyebrow="Bounded sample, not full-file validation"
          description={`Source ${upload.filename}, ${bytes(upload.bytes)}, SHA-256 ${hash(upload.sha256, 20)}`}
          action={
            <button
              disabled={
                preview.report.accepted === 0 ||
                importMutation.isPending ||
                Boolean(migration && !backupDone)
              }
              onClick={() => importMutation.mutate()}
            >
              {importMutation.isPending
                ? "Queueing import"
                : "Publish import job"}
            </button>
          }
        >
          <div className="metrics-grid">
            <Metric
              label="Sampled rows"
              value={number(preview.report.received)}
              detail="First bounded adapter records"
            />
            <Metric
              label="Schema valid"
              value={number(preview.report.accepted)}
              detail="Identity checks run during full import"
            />
            <Metric
              label="Rejected"
              value={number(preview.report.rejected)}
              detail="Explicit validation failures"
            />
            <Metric
              label="Timestamp policy"
              value={options.format === "legacy" ? "Unknown" : "Source"}
              detail="No fabricated metadata"
            />
          </div>
          {preview.report.warnings.map((warning) => (
            <Notice key={warning.code} tone="warning">
              <strong>{warning.count} rows:</strong> {warning.message}
            </Notice>
          ))}
          {migration && !backupDone ? (
            <Notice tone="warning">
              Download the original backup before publishing this migration.
            </Notice>
          ) : null}
          <Inspector
            value={preview.events}
            title="Normalized schema examples"
            initiallyOpen
          />
          <Inspector value={preview.report.samples} title="Rejection samples" />
          <p className="footnote">
            The full job verifies every row, checks stable identities, writes
            immutable partitions, and atomically commits its manifest. An exact
            duplicate creates no extra attempt.
          </p>
        </Panel>
      ) : null}
    </div>
  );
}
