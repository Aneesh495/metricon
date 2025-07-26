import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { KnowledgeReplay } from "../components/KnowledgeReplay";
import { api } from "../api/client";
import { CoefficientChart } from "../components/Charts";
import {
  Empty,
  ErrorState,
  Field,
  Inspector,
  Loading,
  Notice,
  Panel,
  Tag,
} from "../components/Common";
import { hash, number, percentage } from "../lib/format";

const BKTParameterSchema = z.object({
  initial: z.number(),
  learning: z.number(),
  slip: z.number(),
  guess: z.number(),
  forgetting: z.number(),
});
const AssociationSchema = z.array(
  z.object({ feature: z.string(), coefficient: z.number() }),
);
const ItemSchema = z.record(
  z.object({
    difficulty: z.number(),
    discrimination: z.number(),
    n: z.number(),
    information: z.number(),
    conditional_standard_error: z.number(),
    unstable: z.boolean(),
  }),
);
export type BKTParameters = z.infer<typeof BKTParameterSchema>;

export function scalarBKT(
  prior: number,
  correct: boolean,
  parameters: BKTParameters,
) {
  const prediction =
    prior * (1 - parameters.slip) + (1 - prior) * parameters.guess;
  const evidence = correct ? prediction : 1 - prediction;
  const posterior =
    (prior * (correct ? 1 - parameters.slip : parameters.slip)) /
    Math.max(evidence, 1e-9);
  const next =
    posterior * (1 - parameters.forgetting) +
    (1 - posterior) * parameters.learning;
  return { prediction, posterior, next };
}

export function BKTExplorer({ parameters }: { parameters: BKTParameters }) {
  const [sequence, setSequence] = useState("1,0,1,1,0,1");
  const [initial, setInitial] = useState(parameters.initial);
  const tokens = sequence.split(/[\s,]+/).filter(Boolean);
  const valid =
    tokens.every((token) => token === "0" || token === "1") &&
    tokens.length <= 100;
  let knowledge = initial;
  const rows = valid
    ? tokens.map((token, index) => {
        const prior = knowledge;
        const result = scalarBKT(prior, token === "1", parameters);
        knowledge = result.next;
        return { index, correct: token === "1", prior, ...result };
      })
    : [];
  return (
    <Panel
      title="Inspect the state transition"
      description="Illustrative sequence using exact fitted parameters. This does not alter or evaluate the original research run."
    >
      <div className="form-grid">
        <Field
          label="Illustrative answer sequence"
          hint="0 = incorrect, 1 = correct; at most 100 answers."
        >
          <input
            value={sequence}
            onChange={(event) => setSequence(event.target.value)}
          />
        </Field>
        <Field label={`Initial model knowledge: ${percentage(initial)}`}>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={initial}
            onChange={(event) => setInitial(Number(event.target.value))}
          />
        </Field>
      </div>
      {!valid ? (
        <Notice tone="danger">
          Use only 0 and 1 separated by commas or spaces.
        </Notice>
      ) : null}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Opportunity</th>
              <th>Prior knowledge</th>
              <th>Next-answer prediction</th>
              <th>Observed answer</th>
              <th>Answer posterior</th>
              <th>After transition</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.index}>
                <td>{row.index + 1}</td>
                <td>{percentage(row.prior)}</td>
                <td>{percentage(row.prediction)}</td>
                <td>
                  <Tag tone={row.correct ? "green" : "rose"}>
                    {row.correct ? "Correct" : "Incorrect"}
                  </Tag>
                </td>
                <td>{percentage(row.posterior)}</td>
                <td>{percentage(row.next)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="footnote">
        Prediction precedes the answer. Conditioning follows the answer.
        Learning and optional forgetting follow conditioning. A high posterior
        is a model estimate.
      </p>
    </Panel>
  );
}

export function ModelMicroscope({
  dataset,
  artifact: requestedArtifact,
}: {
  dataset: string;
  artifact: string;
}) {
  const artifacts = useQuery({
    queryKey: ["artifacts", dataset, "experiment"],
    queryFn: () => api.artifacts(dataset, "experiment"),
  });
  const [selected, setSelected] = useState("");
  const artifact =
    selected || requestedArtifact || artifacts.data?.[0]?.id || "";
  const [name, setName] = useState("bkt");
  const [skill, setSkill] = useState("");
  const report = useQuery({
    queryKey: ["report", artifact],
    queryFn: () => api.report(artifact),
    enabled: Boolean(artifact),
  });
  const model = useQuery({
    queryKey: ["model", artifact, name],
    queryFn: () => api.model(artifact, name),
    enabled: Boolean(artifact),
  });
  const skillParameters = z
    .record(BKTParameterSchema)
    .safeParse(model.data?.skills);
  const selectedSkill =
    skill ||
    (skillParameters.success ? Object.keys(skillParameters.data)[0] : "");
  const parameter = skillParameters.success
    ? skillParameters.data[selectedSkill]
    : null;
  const associations = AssociationSchema.safeParse(model.data?.associations);
  const items = ItemSchema.safeParse(model.data?.items);
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <p className="eyebrow">04 / Model microscope</p>
          <h1>Open the fitted model.</h1>
          <p>
            Exact parameters, convergence evidence, and prediction mechanics
            belong in the workbench.
          </p>
        </div>
      </div>
      <Panel
        title="Model selection"
        description="All parameters come from committed experiment artifacts."
      >
        <div className="form-grid">
          <Field label="Experiment">
            <select
              value={artifact}
              onChange={(event) => {
                setSelected(event.target.value);
                setSkill("");
              }}
            >
              <option value="">Choose a run</option>
              {artifacts.data?.map((row) => (
                <option key={row.id} value={row.id}>
                  {hash(row.id, 20)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Fitted model">
            <select
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setSkill("");
              }}
            >
              {Object.entries(report.data?.folds[0]?.models ?? {})
                .filter(([, result]) => result.eligible)
                .map(([key]) => (
                  <option key={key}>{key}</option>
                ))}
            </select>
          </Field>
        </div>
      </Panel>
      {!artifact ? (
        <Empty title="A fitted model needs a completed experiment">
          Run the packaged experiment pipeline, then inspect its parameters
          here.
        </Empty>
      ) : model.isPending ? (
        <Loading />
      ) : model.error ? (
        <ErrorState error={model.error} />
      ) : model.data ? (
        <>
          {model.data.family === "bkt" && skillParameters.success ? (
            <>
              <Panel
                title="Per-skill BKT parameters"
                description="Primary policy uses the first sorted tag. Mean policy fits replicated outcomes independently and is evaluated as an ablation."
              >
                <Field label="Skill">
                  <select
                    value={selectedSkill}
                    onChange={(event) => setSkill(event.target.value)}
                  >
                    {Object.keys(skillParameters.data).map((key) => (
                      <option key={key}>{key}</option>
                    ))}
                  </select>
                </Field>
                {parameter ? (
                  <div className="parameter-grid">
                    {Object.entries(parameter).map(([key, value]) => (
                      <div key={key}>
                        <span>{key}</span>
                        <strong>{number(value, 4)}</strong>
                      </div>
                    ))}
                  </div>
                ) : null}
                <Inspector
                  value={
                    model.data.diagnostics &&
                    typeof model.data.diagnostics === "object"
                      ? (model.data.diagnostics as Record<string, unknown>)[
                          selectedSkill
                        ]
                      : {}
                  }
                  title="Skill fitting diagnostics"
                  initiallyOpen
                />
              </Panel>
              {parameter ? (
                <BKTExplorer
                  key={`${artifact}:${name}:${selectedSkill}`}
                  parameters={parameter}
                />
              ) : null}
            </>
          ) : null}
          {model.data.family === "logistic" && associations.success ? (
            <Panel
              title="Predictive associations"
              description="Coefficients use training-fitted feature vocabularies. They describe associations, not causal effects."
            >
              <CoefficientChart associations={associations.data} />
              <Inspector
                value={model.data.encoder}
                title="Feature version and training vocabulary"
              />
            </Panel>
          ) : null}
          {model.data.family === "irt" && items.success ? (
            <Panel
              title="Population item estimates"
              description="Item estimates apply only to the eligible cohort and fitted scale. Conditional curvature is not a full posterior interval."
            >
              <Notice tone="warning">
                Unsupported and sparse items are excluded during fitting. These
                are population estimates, not difficulty labels inferred from
                one person's answer history.
              </Notice>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th>Difficulty</th>
                      <th>Discrimination</th>
                      <th>n</th>
                      <th>Conditional SE</th>
                      <th>Support</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(items.data)
                      .sort((a, b) => b[1].n - a[1].n)
                      .slice(0, 100)
                      .map(([key, value]) => (
                        <tr key={key}>
                          <td>{key}</td>
                          <td>{number(value.difficulty, 3)}</td>
                          <td>{number(value.discrimination, 3)}</td>
                          <td>{number(value.n)}</td>
                          <td>{number(value.conditional_standard_error, 3)}</td>
                          <td>
                            <Tag tone={value.unstable ? "amber" : "green"}>
                              {value.unstable ? "Unstable" : "Supported"}
                            </Tag>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              <p className="footnote">
                Top 100 items by response count. Complete parameters are in the
                downloadable artifact.
              </p>
            </Panel>
          ) : null}
          {model.data.family === "bkt" ? (
            <KnowledgeReplay
              artifact={artifact}
              model={name}
              dataset={dataset}
            />
          ) : null}
          <Inspector value={model.data.diagnostics} title="Model diagnostics" />
          <Inspector value={model.data} title="Exact serialized parameters" />
        </>
      ) : null}
    </div>
  );
}
