import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export function useJobs(workspace: string | undefined) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["jobs", workspace],
    queryFn: () => api.jobs(workspace!),
    enabled: Boolean(workspace),
    refetchInterval: (state) =>
      state.state.data?.some(
        (job) => job.status === "running" || job.status === "queued",
      )
        ? 1500
        : 10000,
  });
  const latestComplete = query.data?.find(
    (job) => job.status === "completed",
  )?.id;
  useEffect(() => {
    if (latestComplete) {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      void queryClient.invalidateQueries({ queryKey: ["versions", workspace] });
      void queryClient.invalidateQueries({ queryKey: ["artifacts"] });
    }
  }, [latestComplete, workspace, queryClient]);
  return query;
}

export function useSelection() {
  const initial = new URLSearchParams(window.location.search);
  const [workspace, setWorkspace] = useState(initial.get("workspace") ?? "");
  const [tab, setTab] = useState(initial.get("tab") ?? "observations");
  useEffect(() => {
    const query = new URLSearchParams();
    if (workspace) query.set("workspace", workspace);
    query.set("tab", tab);
    window.history.replaceState(null, "", `?${query.toString()}`);
  }, [workspace, tab]);
  return { workspace, setWorkspace, tab, setTab };
}
