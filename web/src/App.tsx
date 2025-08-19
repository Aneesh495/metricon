import { lazy, Suspense, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  Boxes,
  FlaskConical,
  GitBranch,
  Import,
  ListTodo,
  Microscope,
  Plus,
  Route,
  Sparkles,
} from "lucide-react";
import { api } from "./api/client";
import {
  Empty,
  ErrorState,
  Field,
  Loading,
  Notice,
  Tag,
} from "./components/Common";
import { useJobs, useSelection } from "./hooks/useLab";
import { hash, number } from "./lib/format";
import { loadPage } from "./lib/load-page";

const Observations = lazy(() =>
  loadPage("Observations", () => import("./pages/Observations")).then(
    (module) => ({
      default: module.Observations,
    }),
  ),
);
const ImportLab = lazy(() =>
  loadPage("ImportLab", () => import("./pages/ImportLab")).then((module) => ({
    default: module.ImportLab,
  })),
);
const Experiments = lazy(() =>
  loadPage("Experiments", () => import("./pages/Experiments")).then(
    (module) => ({
      default: module.Experiments,
    }),
  ),
);
const ModelMicroscope = lazy(() =>
  loadPage("ModelMicroscope", () => import("./pages/ModelMicroscope")).then(
    (module) => ({
      default: module.ModelMicroscope,
    }),
  ),
);
const PolicyLab = lazy(() =>
  loadPage("PolicyLab", () => import("./pages/PolicyLab")).then((module) => ({
    default: module.PolicyLab,
  })),
);
const Provenance = lazy(() =>
  loadPage("Provenance", () => import("./pages/Provenance")).then((module) => ({
    default: module.Provenance,
  })),
);
const Jobs = lazy(() =>
  loadPage("Jobs", () => import("./pages/Jobs")).then((module) => ({
    default: module.Jobs,
  })),
);

const navigation = [
  { id: "observations", title: "Observations", icon: Activity },
  { id: "import", title: "Import laboratory", icon: Import },
  { id: "experiments", title: "Experiment bench", icon: FlaskConical },
  { id: "models", title: "Model microscope", icon: Microscope },
  { id: "policies", title: "Policy laboratory", icon: Route },
  { id: "provenance", title: "Provenance", icon: GitBranch },
  { id: "jobs", title: "Jobs", icon: ListTodo },
];

export default function App() {
  const queryClient = useQueryClient();
  const {
    workspace: selectedWorkspace,
    setWorkspace,
    tab,
    setTab,
    version,
    setVersion,
    learner,
    setLearner,
    artifact,
    setArtifact,
  } = useSelection();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("My learning workspace");
  const workspaces = useQuery({
    queryKey: ["workspaces"],
    queryFn: api.workspaces,
  });
  const workspace = selectedWorkspace
    ? workspaces.data?.find((row) => row.id === selectedWorkspace)
    : workspaces.data?.[0];
  const versions = useQuery({
    queryKey: ["versions", workspace?.id],
    queryFn: () => api.versions(workspace!.id),
    enabled: Boolean(workspace),
  });
  const selectedVersion = versions.data?.find((row) => row.id === version);
  const dataset = version
    ? selectedVersion?.id || ""
    : workspace?.dataset_id || "";
  const jobs = useJobs(workspace?.id);
  const activeJobs =
    jobs.data?.filter((job) => ["queued", "running"].includes(job.status))
      .length ?? 0;
  const create = useMutation({
    mutationFn: () => api.createWorkspace(name),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      chooseWorkspace(result.id);
      setCreating(false);
    },
  });
  const demo = useMutation({
    mutationFn: api.demo,
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      chooseWorkspace(result.workspace.id);
    },
  });
  function chooseWorkspace(id: string) {
    setWorkspace(id);
    setVersion("");
    setLearner("");
    setArtifact("");
  }
  function inspectArtifact(id: string) {
    setArtifact(id);
    setTab("provenance");
  }
  function jobQueued(_id: string) {
    setTab("jobs");
  }
  function renderPage() {
    if (selectedWorkspace && !workspace)
      return (
        <Empty title="This workspace is unavailable">
          Select an existing workspace or create a new one. The requested link
          does not select another workspace's data.
        </Empty>
      );
    if (!workspace)
      return (
        <Empty
          title="Your laboratory starts empty."
          action={
            <div className="button-row">
              <button onClick={() => setCreating(true)}>
                <Plus size={16} />
                Create workspace
              </button>
              <button
                className="secondary"
                disabled={demo.isPending}
                onClick={() => demo.mutate()}
              >
                <Sparkles size={16} />
                Create synthetic sandbox
              </button>
            </div>
          }
        >
          Import actual practice events into your own workspace. A synthetic
          sandbox is a separate, explicitly labeled dataset.
        </Empty>
      );
    if (tab === "import")
      return <ImportLab workspace={workspace.id} onJob={jobQueued} />;
    if (tab === "jobs")
      return <Jobs workspace={workspace.id} onArtifact={inspectArtifact} />;
    if (versions.error)
      return (
        <ErrorState
          error={versions.error}
          retry={() => void versions.refetch()}
        />
      );
    if (version && versions.isPending)
      return <Loading label="Checking the requested dataset version" />;
    if (version && !selectedVersion)
      return (
        <Empty
          title="This dataset version is unavailable in the selected workspace"
          action={
            <button
              onClick={() => {
                setVersion("");
                setLearner("");
                setArtifact("");
              }}
            >
              Open the latest committed version
            </button>
          }
        >
          Select a version owned by this workspace. A deep link cannot combine
          one workspace's label with another workspace's observations.
        </Empty>
      );
    if (!dataset)
      return (
        <Empty
          title="No imported observations."
          action={
            <button onClick={() => setTab("import")}>
              <Import size={16} />
              Preview an import
            </button>
          }
        >
          A new account contains no attempts, percentages, percentiles or
          mastery claims.
        </Empty>
      );
    if (tab === "experiments")
      return (
        <Experiments
          workspace={workspace.id}
          dataset={dataset}
          onArtifact={inspectArtifact}
          onJob={jobQueued}
        />
      );
    if (tab === "models")
      return <ModelMicroscope dataset={dataset} artifact={artifact} />;
    if (tab === "policies")
      return (
        <PolicyLab
          workspace={workspace.id}
          dataset={dataset}
          learner={learner}
          onJob={jobQueued}
        />
      );
    if (tab === "provenance")
      return (
        <Provenance
          key={`${dataset}:${artifact}`}
          dataset={dataset}
          requestedArtifact={artifact}
        />
      );
    return (
      <Observations
        dataset={dataset}
        learner={learner}
        onLearner={setLearner}
      />
    );
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to workbench
      </a>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <i />
            <i />
            <i />
          </div>
          <div>
            <strong>
              metricon<span>.</span>
            </strong>
            <small>LEARNING LABORATORY</small>
          </div>
        </div>
        <div className="workspace-picker">
          <label htmlFor="workspace-selector">WORKSPACE</label>
          <select
            id="workspace-selector"
            value={workspace?.id ?? ""}
            onChange={(event) => chooseWorkspace(event.target.value)}
          >
            <option value="" disabled>
              Select a workspace
            </option>
            {workspaces.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
          <button className="text-button" onClick={() => setCreating(true)}>
            <Plus size={14} />
            New workspace
          </button>
        </div>
        <button
          className="text-button"
          disabled={demo.isPending}
          onClick={() => demo.mutate()}
        >
          Create synthetic sandbox
        </button>
        <nav aria-label="Workbench navigation">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={tab === item.id ? "nav-item active" : "nav-item"}
              aria-current={tab === item.id ? "page" : undefined}
              onClick={() => setTab(item.id)}
            >
              <item.icon size={18} />
              <span>{item.title}</span>
              {item.id === "jobs" && activeJobs ? <b>{activeJobs}</b> : null}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-status">
            <i />
            Local workspace
          </div>
          <p>
            Immutable data.
            <br />
            Inspectable decisions.
          </p>
          <a href="/api/docs" target="_blank" rel="noreferrer">
            API reference <ArrowUpRight size={14} />
          </a>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <Boxes size={16} />
            <span>{workspace?.name ?? "No workspace selected"}</span>
            {workspace?.kind === "synthetic" ? (
              <Tag tone="amber">Synthetic demo</Tag>
            ) : workspace?.kind === "research" ? (
              <Tag>Research cohort</Tag>
            ) : (
              <Tag>Personal data</Tag>
            )}
          </div>
          <div>
            <span className="muted">DATASET</span>
            <select
              aria-label="Dataset version"
              value={dataset}
              onChange={(event) => {
                setVersion(event.target.value);
                setLearner("");
                setArtifact("");
              }}
            >
              <option value="">No committed version</option>
              {versions.data?.map((row) => (
                <option key={row.id} value={row.id}>
                  {hash(row.id)} / {number(row.row_count)} events
                </option>
              ))}
            </select>
          </div>
        </header>
        <main id="main" className="main-content">
          {workspaces.error ? (
            <ErrorState
              error={workspaces.error}
              retry={() => void workspaces.refetch()}
            />
          ) : workspaces.isPending ? (
            <Loading label="Connecting to the local laboratory" />
          ) : (
            <Suspense
              key={`${workspace?.id}:${dataset}`}
              fallback={<Loading label="Opening analytical workbench" />}
            >
              {renderPage()}
            </Suspense>
          )}
          {demo.error ? <ErrorState error={demo.error} /> : null}
        </main>
        <footer className="app-footer">
          <span>METRICON / SCIENTIFIC WORKBENCH</span>
          <span>Source, sample, method, uncertainty.</span>
        </footer>
      </div>
      {creating ? (
        <div className="modal-backdrop">
          <section
            className="modal"
            onKeyDown={(event) => {
              if (event.key === "Escape") setCreating(false);
              if (event.key === "Tab") {
                const controls =
                  event.currentTarget.querySelectorAll<HTMLElement>(
                    "button:not([disabled]),input,select,textarea,a[href]",
                  );
                const first = controls[0],
                  last = controls[controls.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                  event.preventDefault();
                  last?.focus();
                }
                if (!event.shiftKey && document.activeElement === last) {
                  event.preventDefault();
                  first?.focus();
                }
              }
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="workspace-title"
          >
            <p className="eyebrow">Separate data ownership</p>
            <h2 id="workspace-title">Create a personal workspace</h2>
            <Field label="Workspace name">
              <input
                autoFocus
                value={name}
                maxLength={120}
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && name.trim() && !create.isPending)
                    create.mutate();
                  if (event.key === "Escape") setCreating(false);
                }}
              />
            </Field>
            <Notice>
              This workspace starts empty. Imports publish new versions after
              full validation.
            </Notice>
            {create.error ? <ErrorState error={create.error} /> : null}
            <div className="button-row">
              <button
                disabled={!name.trim() || create.isPending}
                onClick={() => create.mutate()}
              >
                Create workspace
              </button>
              <button className="secondary" onClick={() => setCreating(false)}>
                Cancel
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
