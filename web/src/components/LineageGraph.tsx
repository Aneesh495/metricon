import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { z } from "zod";
import { ErrorState, Inspector, Loading, Notice, Tag } from "./Common";
import { hash } from "../lib/format";

export const GraphSchema = z.object({
  root: z.string(),
  nodes: z.array(
    z.object({
      id: z.string(),
      kind: z.string(),
      metadata: z.record(z.unknown()),
      locator: z.string().nullable(),
      checksum: z.string().nullable(),
    }),
  ),
  edges: z.array(
    z.object({ child: z.string(), parent: z.string(), role: z.string() }),
  ),
  levels: z.array(z.array(z.string())),
  acyclic: z.boolean(),
  meaning: z.string(),
});

export function LineageGraph({ artifact }: { artifact: string }) {
  const graphQuery = useQuery({
    queryKey: ["lineage", artifact],
    queryFn: () => api.lineage(artifact),
  });
  const parsed = GraphSchema.safeParse(graphQuery.data);
  const [selected, setSelected] = useState("");
  const verify = useMutation({ mutationFn: () => api.verifyLineage(artifact) });
  const descendants = useQuery({
    queryKey: ["descendants", selected],
    queryFn: () => api.descendants(selected),
    enabled: Boolean(selected),
  });
  if (graphQuery.isPending)
    return <Loading label="Resolving content lineage" />;
  if (graphQuery.error) return <ErrorState error={graphQuery.error} />;
  if (!parsed.success)
    return (
      <ErrorState error={new Error("Lineage graph contract does not match")} />
    );
  const graph = parsed.data;
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const node = nodesById.get(selected);
  return (
    <div className="lineage-graph">
      <div className="report-meta">
        <Tag tone="green">Acyclic dependency graph</Tag>
        <span className="muted">
          {graph.nodes.length} nodes / {graph.edges.length} edges
        </span>
        <button
          className="secondary"
          disabled={verify.isPending}
          onClick={() => verify.mutate()}
        >
          Verify lineage files
        </button>
      </div>
      {verify.data ? (
        <Notice tone={verify.data.valid ? "success" : "danger"}>
          {verify.data.valid
            ? "All available immutable lineage files match their hashes."
            : "Lineage verification found altered files."}{" "}
          {String(
            (verify.data.metadata_only_nodes as unknown[] | undefined)
              ?.length ?? 0,
          )}{" "}
          metadata-only references remain explicit.
        </Notice>
      ) : null}
      {verify.error ? <ErrorState error={verify.error} /> : null}
      <div
        className="lineage-columns"
        role="list"
        aria-label="Dependency graph ordered from sources to results"
      >
        {graph.levels.map((level, index) => (
          <section className="lineage-level" key={index}>
            <header>Dependency level {index}</header>
            {level.map((id) => {
              const current = nodesById.get(id)!;
              const parentCount = graph.edges.filter(
                (edge) => edge.child === id,
              ).length;
              return (
                <button
                  key={id}
                  className={`lineage-node ${id === selected ? "selected" : ""}`}
                  onClick={() => setSelected(id)}
                  aria-pressed={id === selected}
                >
                  <strong>{current.kind}</strong>
                  <code>{hash(id, 16)}</code>
                  <small>
                    {parentCount} dependencies
                    {current.checksum
                      ? " / file backed"
                      : " / metadata reference"}
                  </small>
                </button>
              );
            })}
          </section>
        ))}
      </div>
      <p className="footnote">{graph.meaning}</p>
      {node ? (
        <div className="lineage-detail">
          <h3>{node.kind}</h3>
          <div className="hash-block">
            <span>Content identity</span>
            <code>{node.id}</code>
            {node.checksum ? (
              <>
                <span>File SHA-256</span>
                <code>{node.checksum}</code>
              </>
            ) : null}
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Dependency role</th>
                  <th>Parent identity</th>
                </tr>
              </thead>
              <tbody>
                {graph.edges
                  .filter((edge) => edge.child === node.id)
                  .map((edge) => (
                    <tr key={`${edge.parent}:${edge.role}`}>
                      <td>{edge.role}</td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => setSelected(edge.parent)}
                        >
                          <code>{hash(edge.parent, 24)}</code>
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <Inspector
            value={node.metadata}
            title="Node metadata"
            initiallyOpen
          />
          <Inspector
            value={descendants.data}
            title="Results depending on this node"
          />
        </div>
      ) : null}
    </div>
  );
}
