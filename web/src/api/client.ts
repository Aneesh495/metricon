import { z } from "zod";
import {
  ArtifactSchema,
  ArtifactSummarySchema,
  DatasetSchema,
  GroupsSchema,
  HistorySchema,
  JobSchema,
  OverviewSchema,
  MetricsSchema,
  PlanSchema,
  PreviewSchema,
  ReportSchema,
  SimulationSchema,
  TrendSchema,
  UploadSchema,
  VersionSchema,
  WorkspaceSchema,
  type ExperimentOptions,
  type ImportOptions,
} from "./contracts";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "X-Metricon-Client": "1",
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const detail = z.object({ detail: z.unknown() }).safeParse(payload);
    const message =
      detail.success && typeof detail.data.detail === "string"
        ? detail.data.detail
        : `Request failed (${response.status})`;
    throw new ApiError(response.status, message, payload);
  }
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError(
      502,
      "Server response does not match the workbench contract",
      parsed.error.issues,
    );
  }
  return parsed.data;
}

function parameters(
  values: Record<string, string | number | boolean | undefined>,
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const result = query.toString();
  return result ? `?${result}` : "";
}

function post<T>(
  path: string,
  schema: z.ZodType<T>,
  body: unknown,
): Promise<T> {
  return request(path, schema, { method: "POST", body: JSON.stringify(body) });
}

export const api = {
  workspaces: () => request("/workspaces", z.array(WorkspaceSchema)),
  workspace: (id: string) => request(`/workspaces/${id}`, WorkspaceSchema),
  createWorkspace: (name: string) =>
    post("/workspaces", WorkspaceSchema, { name }),
  demo: () =>
    post(
      "/demo",
      z.object({ workspace: WorkspaceSchema, synthetic: z.literal(true) }),
      {},
    ),
  versions: (id: string) =>
    request(`/workspaces/${id}/datasets`, z.array(VersionSchema)),
  dataset: (id: string) => request(`/datasets/${id}`, DatasetSchema),
  overview: (id: string, learner?: string) =>
    request(
      `/datasets/${id}/overview${parameters({ learner_id: learner })}`,
      OverviewSchema,
    ),
  groups: (
    id: string,
    dimension: string,
    offset = 0,
    learner?: string,
    search = "",
  ) =>
    request(
      `/datasets/${id}/groups${parameters({ dimension, offset, learner_id: learner, search })}`,
      GroupsSchema,
    ),
  history: (id: string, learner: string, offset = 0, question?: string) =>
    request(
      `/datasets/${id}/history${parameters({ learner_id: learner, offset, question_id: question })}`,
      HistorySchema,
    ),
  trend: (
    id: string,
    learner: string,
    axis: "order" | "time",
    question?: string,
  ) =>
    request(
      `/datasets/${id}/trend${parameters({ learner_id: learner, axis, question_id: question })}`,
      TrendSchema,
    ),
  cohort: (id: string, learner: string) =>
    request(
      `/datasets/${id}/cohort${parameters({ learner_id: learner })}`,
      z.record(z.unknown()),
    ),
  streaks: (id: string, learner: string) =>
    request(
      `/datasets/${id}/streaks${parameters({ learner_id: learner })}`,
      z.record(z.unknown()),
    ),
  audit: (id: string, checksums = false) =>
    request(
      `/datasets/${id}/audit${parameters({ verify_checksums: checksums })}`,
      z.record(z.unknown()),
    ),
  upload: (file: File) => {
    const body = new FormData();
    body.set("file", file);
    return request("/uploads", UploadSchema, { method: "POST", body });
  },
  preview: (id: string, options: ImportOptions) =>
    post(`/uploads/${id}/preview`, PreviewSchema, options),
  import: (workspace: string, upload: string, options: ImportOptions) =>
    post(`/workspaces/${workspace}/import`, JobSchema, {
      upload_id: upload,
      options,
    }),
  experiment: (workspace: string, options: ExperimentOptions) =>
    post(`/workspaces/${workspace}/experiments`, JobSchema, options),
  jobs: (workspace: string) =>
    request(`/workspaces/${workspace}/jobs`, z.array(JobSchema)),
  job: (id: string) => request(`/jobs/${id}`, JobSchema),
  cancel: (id: string) => post(`/jobs/${id}/cancel`, JobSchema, {}),
  artifacts: (dataset: string, kind?: string) =>
    request(
      `/datasets/${dataset}/artifacts${parameters({ kind })}`,
      z.array(ArtifactSummarySchema),
    ),
  artifact: (id: string) => request(`/artifacts/${id}`, ArtifactSchema),
  verify: (id: string) =>
    request(
      `/artifacts/${id}/verify`,
      z.object({
        id: z.string(),
        valid: z.boolean(),
        invalid_files: z.array(z.string()),
      }),
    ),
  report: (id: string) => request(`/artifacts/${id}/report`, ReportSchema),
  model: (id: string, name: string, fold = 0) =>
    request(
      `/artifacts/${id}/models/${encodeURIComponent(name)}/parameters${parameters({ fold })}`,
      z.record(z.unknown()),
    ),
  plan: (id: string, body: unknown) =>
    post(`/datasets/${id}/plan`, PlanSchema, body),
  simulate: (workspace: string, body: unknown) =>
    post(`/workspaces/${workspace}/simulations`, JobSchema, body),
  simulation: (id: string) =>
    request(`/artifacts/${id}/report`, SimulationSchema),
  lineage: (id: string) => request(`/lineage/${id}`, z.record(z.unknown())),
  verifyLineage: (id: string) =>
    request(`/lineage/${id}/verify`, z.record(z.unknown())),
  descendants: (id: string) =>
    request(`/lineage/${id}/descendants`, z.record(z.unknown())),
  replay: (id: string, name: string, learner: string, offset: number) =>
    request(
      `/artifacts/${id}/models/${encodeURIComponent(name)}/replay${parameters({ learner_id: learner, offset })}`,
      z.record(z.unknown()),
    ),
  predictions: (
    id: string,
    model: string,
    offset: number,
    sort: string,
    learner?: string,
  ) =>
    request(
      `/artifacts/${id}/predictions${parameters({ model, offset, sort, learner_id: learner })}`,
      z.record(z.unknown()),
    ),
  predictionSlice: (
    id: string,
    model: string,
    learner?: string,
    skill?: string,
  ) =>
    request(
      `/artifacts/${id}/prediction-slice${parameters({ model, learner_id: learner, skill })}`,
      z.object({
        metrics: MetricsSchema,
        population: z.string(),
        selection_limit: z.string(),
      }),
    ),
  fileURL: (id: string, file: string) =>
    `/api/artifacts/${id}/files/${file.split("/").map(encodeURIComponent).join("/")}`,
};
