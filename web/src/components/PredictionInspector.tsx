import { useDeferredValue, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../api/client";
import { CalibrationChart } from "./Charts";
import {
  ErrorState,
  Field,
  Loading,
  Notice,
  Pagination,
  Panel,
  Tag,
} from "./Common";
import { number, percentage } from "../lib/format";

const PredictionPageSchema = z.object({
  artifact_id: z.string(),
  model: z.string(),
  partition: z.string(),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  sort: z.string(),
  interpretation: z.string(),
  rows: z.array(
    z.object({
      identity: z.string(),
      learner_id: z.string(),
      question_id: z.string(),
      skills: z.array(z.string()),
      correct: z.boolean(),
      probability: z.number(),
      calibrated_probability: z.number().nullable(),
      absolute_error: z.number(),
    }),
  ),
});

export function PredictionInspector({
  artifact,
  model,
}: {
  artifact: string;
  model: string;
}) {
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState("largest_error");
  const [learner, setLearner] = useState("");
  const deferredLearner = useDeferredValue(learner);
  const [skill, setSkill] = useState("");
  const deferredSkill = useDeferredValue(skill);
  const rows = useQuery({
    queryKey: ["predictions", artifact, model, offset, sort, deferredLearner],
    queryFn: () =>
      api.predictions(
        artifact,
        model,
        offset,
        sort,
        deferredLearner || undefined,
      ),
  });
  const slice = useQuery({
    queryKey: [
      "prediction-slice",
      artifact,
      model,
      deferredLearner,
      deferredSkill,
    ],
    queryFn: () =>
      api.predictionSlice(
        artifact,
        model,
        deferredLearner || undefined,
        deferredSkill || undefined,
      ),
  });
  const parsed = PredictionPageSchema.safeParse(rows.data);
  return (
    <Panel
      title="Inspect saved held-out predictions"
      description="Every row is an actual prediction emitted by the packaged evaluation run."
    >
      <div className="form-grid">
        <Field label="Diagnostic ordering">
          <select
            value={sort}
            onChange={(event) => {
              setSort(event.target.value);
              setOffset(0);
            }}
          >
            <option value="largest_error">Largest absolute errors</option>
            <option value="confidence">Most confident predictions</option>
            <option value="identity">Stable event identity</option>
          </select>
        </Field>
        <Field label="Learner slice">
          <input
            placeholder="Optional learner ID"
            value={learner}
            onChange={(event) => {
              setLearner(event.target.value);
              setOffset(0);
            }}
          />
        </Field>
        <Field label="Calibration skill slice">
          <input
            placeholder="Optional skill tag"
            value={skill}
            onChange={(event) => setSkill(event.target.value)}
          />
        </Field>
      </div>
      <Notice>
        Post-hoc inspection explains failures. These filters do not change the
        original test manifest, fitted models or published comparison.
      </Notice>
      {rows.isPending ? (
        <Loading />
      ) : rows.error ? (
        <ErrorState error={rows.error} />
      ) : parsed.success ? (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Learner / question</th>
                  <th>Prediction</th>
                  <th>Observed outcome</th>
                  <th>Calibrated</th>
                  <th>Absolute error</th>
                </tr>
              </thead>
              <tbody>
                {parsed.data.rows.map((row) => (
                  <tr key={row.identity}>
                    <td>
                      <strong>{row.learner_id}</strong>
                      <br />
                      <code>{row.question_id}</code>
                    </td>
                    <td>{percentage(row.probability)}</td>
                    <td>
                      <Tag tone={row.correct ? "green" : "rose"}>
                        {row.correct ? "Correct" : "Incorrect"}
                      </Tag>
                    </td>
                    <td>{percentage(row.calibrated_probability)}</td>
                    <td>{number(row.absolute_error, 4)}</td>
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
        </>
      ) : null}
      {slice.isPending ? (
        <Loading label="Computing the selected saved-prediction slice" />
      ) : slice.error ? (
        <ErrorState error={slice.error} />
      ) : slice.data ? (
        <>
          <p className="footnote">
            {slice.data.population}, n={number(slice.data.metrics.n)}.{" "}
            {slice.data.selection_limit}
          </p>
          <CalibrationChart metrics={slice.data.metrics} />
        </>
      ) : null}
    </Panel>
  );
}
