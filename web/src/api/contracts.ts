import { z } from "zod";

export const WorkspaceSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.enum(["user", "synthetic", "research"]),
  dataset_id: z.string().nullable(),
  created_at: z.number(),
});
export type Workspace = z.infer<typeof WorkspaceSchema>;

export const IntervalSchema = z.object({
  estimate: z.number().nullable(),
  lower: z.number().nullable(),
  upper: z.number().nullable(),
  n: z.number().int(),
  successes: z.number().int(),
  method: z.string(),
  confidence: z.number(),
});
export type Interval = z.infer<typeof IntervalSchema>;

export const WarningSchema = z.object({
  code: z.string(),
  count: z.number(),
  message: z.string(),
});
export const QualitySchema = z.object({
  received: z.number(),
  accepted: z.number(),
  duplicates: z.number(),
  conflicts: z.number(),
  rejected: z.number(),
  warnings: z.array(WarningSchema),
  samples: z.array(
    z.object({
      category: z.string(),
      row: z.number(),
      reason: z.string(),
      identity: z.string().nullable(),
    }),
  ),
  sample_limit: z.number(),
  balanced: z.boolean(),
});
export type Quality = z.infer<typeof QualitySchema>;

export const DatasetSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  parent_id: z.string().nullable(),
  row_count: z.number(),
  created_at: z.number(),
  schema_version: z.string(),
  source: z.object({
    sha256: z.string(),
    format: z.string(),
    namespace: z.string(),
  }),
  quality: QualitySchema,
  partition_count: z.number(),
});
export type Dataset = z.infer<typeof DatasetSchema>;
export const VersionSchema = z.object({
  id: z.string(),
  parent_id: z.string().nullable(),
  row_count: z.number(),
  created_at: z.number(),
});
export type Version = z.infer<typeof VersionSchema>;

export const OverviewSchema = z.object({
  dataset_id: z.string(),
  learner_id: z.string().nullable(),
  accuracy: IntervalSchema,
  first_attempt_accuracy: IntervalSchema,
  coverage: z.object({
    learners: z.number(),
    questions: z.number(),
    timestamped: z.number(),
    duration_known: z.number(),
    question_only: z.number(),
    shifted: z.number(),
  }),
  durations: z.object({
    n: z.number(),
    median_ms: z.number().nullable(),
    q25_ms: z.number().nullable(),
    q75_ms: z.number().nullable(),
    p90_ms: z.number().nullable(),
    total_ms: z.number().nullable(),
  }),
  retries: z.object({
    questions: z.number(),
    solved: z.number(),
    censored: z.number(),
    mean_retries_before_success: z.number().nullable(),
    median_retries_before_success: z.number().nullable(),
  }),
  definitions: z.record(z.string()),
  small_sample: z.boolean(),
  mastery_interpretation: z.string(),
  artifact_id: z.string().optional(),
});
export type Overview = z.infer<typeof OverviewSchema>;

export const GroupSchema = z.object({
  id: z.string(),
  accuracy: IntervalSchema,
  learners: z.number(),
  questions: z.number(),
  known_durations: z.number(),
  first_timestamp: z.string().nullable(),
  last_timestamp: z.string().nullable(),
});
export type Group = z.infer<typeof GroupSchema>;
export const GroupsSchema = z.object({
  rows: z.array(GroupSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  dimension: z.string(),
  overlapping_denominators: z.boolean(),
});
export type Groups = z.infer<typeof GroupsSchema>;

export const JobSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  dataset_id: z.string(),
  kind: z.string(),
  parameters: z.record(z.unknown()),
  status: z.enum([
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
  ]),
  progress: z.number(),
  message: z.string(),
  result_id: z.string().nullable(),
  error: z.string().nullable(),
  cancel_requested: z.boolean(),
  created_at: z.number(),
  updated_at: z.number(),
});
export type Job = z.infer<typeof JobSchema>;

export const CalibrationSchema = z.object({
  bins: z.array(
    z.object({
      bin: z.number(),
      left: z.number(),
      right: z.number(),
      n: z.number(),
      prediction: z.number().nullable(),
      observed: IntervalSchema,
    }),
  ),
  ece: z.number().nullable(),
  method: z.string(),
  empty_bins: z.string(),
  bin_count: z.number(),
});
export const MetricsSchema = z.object({
  n: z.number(),
  positives: z.number(),
  class_balance: z.number().nullable(),
  log_loss: z.number().nullable(),
  brier: z.number().nullable(),
  auroc: z.number().nullable(),
  accuracy: IntervalSchema,
  calibration: CalibrationSchema,
});
export type Metrics = z.infer<typeof MetricsSchema>;

export const ModelResultSchema = z.object({
  eligible: z.boolean(),
  reason: z.string().optional(),
  parameters_hash: z.string().optional(),
  validation: MetricsSchema.optional(),
  test: MetricsSchema.optional(),
  calibrated_test: MetricsSchema.optional(),
  cluster_intervals: z.record(z.unknown()).optional(),
  diagnostics: z.record(z.unknown()).optional(),
  runtime_seconds: z.number().optional(),
  calibration_parameters: z.record(z.unknown()).optional(),
});
export type ModelResult = z.infer<typeof ModelResultSchema>;
export const FoldSchema = z.object({
  split_hash: z.string(),
  audit: z.object({
    valid: z.boolean(),
    counts: z.record(z.number()),
    split_hash: z.string(),
  }),
  models: z.record(ModelResultSchema),
  comparisons_to_global: z.record(z.record(z.unknown())),
  selected_logistic: z.string().nullable(),
  selection_rule: z.string(),
  online_updates: z.boolean(),
  parameter_policy: z.string(),
  bundle_policy: z.string(),
});
export const ReportSchema = z.object({
  dataset_id: z.string(),
  configuration: z.record(z.unknown()),
  environment: z.record(z.unknown()),
  feature_version: z.string(),
  folds: z.array(FoldSchema),
  interpretation: z.string(),
  runtime_seconds: z.number(),
  peak_process_rss_bytes: z.number(),
  memory_method: z.string(),
});
export type Report = z.infer<typeof ReportSchema>;

export const ArtifactSummarySchema = z.object({
  id: z.string(),
  kind: z.string(),
  created_at: z.number(),
});
export type ArtifactSummary = z.infer<typeof ArtifactSummarySchema>;
export const ArtifactSchema = z.object({
  id: z.string(),
  kind: z.string(),
  dataset_id: z.string(),
  manifest: z.object({
    files: z.record(z.string()),
    metadata: z.record(z.unknown()),
    artifact_version: z.string(),
  }),
  lineage: z.array(
    z.object({ child: z.string(), parent: z.string(), role: z.string() }),
  ),
});
export type Artifact = z.infer<typeof ArtifactSchema>;

export const HistorySchema = z.object({
  rows: z.array(
    z.object({
      event_id: z.string(),
      source_namespace: z.string(),
      question_id: z.string(),
      skills: z.array(z.string()),
      correct: z.boolean(),
      attempt_kind: z.string(),
      source_sequence: z.number(),
      timestamp: z.string().nullable(),
      duration_ms: z.number().nullable(),
      session_id: z.string().nullable(),
      bundle_id: z.string().nullable(),
      order_scope: z.string(),
      time_semantics: z.string(),
      provenance: z.record(z.unknown()),
    }),
  ),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  ordering: z.string(),
});
export type History = z.infer<typeof HistorySchema>;

export const TrendSchema = z.object({
  available: z.boolean(),
  reason: z.string().optional(),
  axis: z.string().optional(),
  series: z.array(
    z.object({
      bucket: z.number(),
      x_start: z.number(),
      x_end: z.number(),
      accuracy: IntervalSchema,
      minimum: z.number(),
      maximum: z.number(),
    }),
  ),
  retains_extrema: z.boolean().optional(),
  eligible: z.string().optional(),
});
export type Trend = z.infer<typeof TrendSchema>;

export const PosteriorSchema = z.object({
  mean: z.number(),
  lower: z.number(),
  upper: z.number(),
  n: z.number(),
  successes: z.number(),
  interpretation: z.string(),
});
export const ActionSchema = z.object({
  question_id: z.string(),
  skills: z.array(z.string()),
  score: z.number(),
  contributions: z.record(z.number()),
  observed_performance: PosteriorSchema,
  duration: z
    .object({
      n: z.number(),
      median_seconds: z.number(),
      q25_seconds: z.number(),
      q75_seconds: z.number(),
      method: z.string(),
    })
    .nullable(),
  timed_eligible: z.boolean(),
  prerequisite_blocks: z.array(z.record(z.unknown())),
  ranking_basis: z.string(),
  planned_seconds: z.number().optional(),
});
export type Action = z.infer<typeof ActionSchema>;
export const PlanSchema = z.object({
  dataset_id: z.string(),
  learner_id: z.string(),
  configuration: z.record(z.unknown()),
  plan_hash: z.string(),
  actions: z.array(ActionSchema),
  budget_seconds: z.number(),
  planned_seconds: z.number(),
  remaining_seconds: z.number(),
  unknown_time_actions: z.array(ActionSchema),
  blocked_actions: z.array(ActionSchema),
  candidates: z.number(),
  recent_order_available: z.boolean(),
  method: z.string(),
  limits: z.array(z.string()),
});
export type Plan = z.infer<typeof PlanSchema>;
export const SimulationSummarySchema = z.object({
  mean: z.number(),
  standard_error: z.number(),
  lower: z.number(),
  upper: z.number(),
  n: z.number(),
});
export const SimulationSchema = z.object({
  simulation_version: z.string(),
  configuration: z.record(z.unknown()),
  simulation_hash: z.string(),
  synthetic: z.literal(true),
  summaries: z.record(z.record(SimulationSummarySchema)),
  paired_comparisons: z.record(z.record(z.unknown())),
  trajectories: z.array(z.record(z.unknown())),
  assumptions: z.record(z.string()),
  interpretation: z.string(),
});
export type Simulation = z.infer<typeof SimulationSchema>;
export const PreviewSchema = z.object({
  source_hash: z.string(),
  sampled: z.boolean(),
  report: QualitySchema,
  events: z.array(z.record(z.unknown())),
});
export type Preview = z.infer<typeof PreviewSchema>;
export const UploadSchema = z.object({
  upload_id: z.string(),
  bytes: z.number(),
  filename: z.string(),
  sha256: z.string(),
});
export type Upload = z.infer<typeof UploadSchema>;
export type ImportOptions = {
  format: "legacy" | "csv" | "ndjson" | "json" | "parquet";
  namespace: string;
  learner: string;
};
export type ExperimentOptions = {
  seed: number;
  split: "forward" | "learner" | "rolling";
  bootstrap_repetitions: number;
  bkt_starts: number;
  online_updates: boolean;
  ablations: boolean;
  calibration: boolean;
};
