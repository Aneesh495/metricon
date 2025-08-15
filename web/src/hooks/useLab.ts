import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { readSelection, selectionQuery } from "../lib/selection";

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
  const [selection, setSelection] = useState(() =>
    readSelection(window.location.search),
  );
  const firstSync = useRef(true);
  useEffect(() => {
    const restore = () => setSelection(readSelection(window.location.search));
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  useEffect(() => {
    const query = selectionQuery(selection);
    const initial = firstSync.current;
    firstSync.current = false;
    if (query === window.location.search) return;
    if (initial) window.history.replaceState(null, "", query);
    else window.history.pushState(null, "", query);
  }, [selection]);
  function change(key: keyof typeof selection, value: string) {
    setSelection((current) => ({ ...current, [key]: value }));
  }
  return {
    ...selection,
    setWorkspace: (value: string) => change("workspace", value),
    setTab: (value: string) => change("tab", value),
    setVersion: (value: string) => change("version", value),
    setLearner: (value: string) => change("learner", value),
    setArtifact: (value: string) => change("artifact", value),
  };
}
