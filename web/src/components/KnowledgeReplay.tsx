import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../api/client";
import {
  Empty,
  ErrorState,
  Field,
  Inspector,
  Loading,
  Notice,
  Pagination,
  Panel,
  Tag,
} from "./Common";
import { percentage } from "../lib/format";

const ReplaySchema = z.object({
  artifact_id: z.string(),
  dataset_id: z.string(),
  model: z.string(),
  learner_id: z.string(),
  rows: z.array(
    z.object({
      event_id: z.string(),
      identity: z.string(),
      question_id: z.string(),
      source_sequence: z.number(),
      timestamp: z.string().nullable(),
      time_semantics: z.string(),
      order_scope: z.string(),
      unit: z.number(),
      unit_size: z.number(),
      correct: z.boolean(),
      prediction_before_unit: z.number(),
      skills_before_unit: z.array(z.record(z.unknown())),
      skill_updates: z.array(
        z.object({
          skill: z.string(),
          conditioning_prior: z.number(),
          conditional_prediction: z.number(),
          answer_posterior: z.number(),
          after_learning_transition: z.number(),
          note: z.string(),
        }),
      ),
    }),
  ),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  final_states: z.record(z.unknown()),
  known_order_domains: z.number(),
  policy: z.string(),
  parameter_fit_partition: z.string(),
  interpretation: z.string(),
  bundle_policy: z.string(),
});

export function KnowledgeReplay({
  artifact,
  model,
  dataset,
}: {
  artifact: string;
  model: string;
  dataset: string;
}) {
  const learners = useQuery({
    queryKey: ["learners", dataset],
    queryFn: () => api.groups(dataset, "learner"),
  });
  const [selected, setSelected] = useState("");
  const [offset, setOffset] = useState(0);
  const learner = selected || learners.data?.rows[0]?.id || "";
  const query = useQuery({
    queryKey: ["replay", artifact, model, learner, offset],
    queryFn: () => api.replay(artifact, model, learner, offset),
    enabled: Boolean(learner),
  });
  const parsed = ReplaySchema.safeParse(query.data);
  return (
    <Panel
      title="Replay an observed learner history"
      description="Retrospective state reconstruction from initial knowledge using exact fitted parameters."
      action={
        <Field label="Learner">
          <select
            value={learner}
            onChange={(event) => {
              setSelected(event.target.value);
              setOffset(0);
            }}
          >
            {learners.data?.rows.map((row) => (
              <option key={row.id}>{row.id}</option>
            ))}
          </select>
        </Field>
      }
    >
      <Notice tone="warning">
        This replay includes observed answers from the full history. The
        held-out experiment's predictions remain in its separate raw prediction
        artifact. Replay is a model explanation, not an additional test result.
      </Notice>
      {!learner ? (
        <Empty title="No learner history">
          Import accepted attempts before replaying a knowledge model.
        </Empty>
      ) : query.isPending ? (
        <Loading label="Reconstructing model state without changing the saved model" />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : parsed.success ? (
        <>
          <div className="report-meta">
            <Tag>{parsed.data.policy} multi-skill policy</Tag>
            <span className="muted">
              {parsed.data.known_order_domains} known order domains
            </span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Source sequence / unit</th>
                  <th>Question</th>
                  <th>Pre-unit prediction</th>
                  <th>Answer</th>
                  <th>Posterior and transition</th>
                </tr>
              </thead>
              <tbody>
                {parsed.data.rows.map((row) => (
                  <tr key={row.identity}>
                    <td>
                      <code>
                        {row.source_sequence} / {row.unit}
                      </code>
                      <small className="muted">
                        {" "}
                        {row.unit_size} coupled answers
                      </small>
                    </td>
                    <td>{row.question_id}</td>
                    <td>{percentage(row.prediction_before_unit)}</td>
                    <td>
                      <Tag tone={row.correct ? "green" : "rose"}>
                        {row.correct ? "Correct" : "Incorrect"}
                      </Tag>
                    </td>
                    <td>
                      {row.skill_updates.map((update) => (
                        <div className="replay-update" key={update.skill}>
                          <strong>{update.skill}</strong>
                          <span>
                            Answer posterior{" "}
                            {percentage(update.answer_posterior)}
                          </span>
                          <span>
                            After transition{" "}
                            {percentage(update.after_learning_transition)}
                          </span>
                        </div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            offset={offset}
            limit={parsed.data.limit}
            total={parsed.data.total}
            onChange={setOffset}
          />
          <p className="footnote">{parsed.data.bundle_policy}</p>
          <Inspector
            value={parsed.data.final_states}
            title="Final model states"
          />
          <Inspector
            value={parsed.data.rows}
            title="Full trace including source identity and conditioning priors"
          />
        </>
      ) : query.data ? (
        <ErrorState
          error={new Error("Replay response failed schema validation")}
        />
      ) : null}
    </Panel>
  );
}
