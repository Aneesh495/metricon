const tabs = [
  "observations",
  "import",
  "experiments",
  "models",
  "policies",
  "provenance",
  "jobs",
];

export function readSelection(search: string) {
  const query = new URLSearchParams(search);
  const requestedTab = query.get("tab") ?? "observations";
  return {
    workspace: query.get("workspace") ?? "",
    version: query.get("version") ?? "",
    learner: query.get("learner") ?? "",
    artifact: query.get("artifact") ?? "",
    tab: tabs.includes(requestedTab) ? requestedTab : "observations",
  };
}

export function selectionQuery(selection: ReturnType<typeof readSelection>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(selection)) {
    if (value) query.set(key, value);
  }
  return `?${query.toString()}`;
}
