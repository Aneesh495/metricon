import { afterEach, expect, test, vi } from "vitest";
import { api, ApiError } from "./client";

afterEach(() => vi.unstubAllGlobals());

const job = {
  id: "job",
  workspace_id: "workspace",
  dataset_id: "historical-version",
  kind: "experiment",
  parameters: {},
  status: "queued",
  progress: 0,
  message: "",
  result_id: null,
  error: null,
  cancel_requested: false,
  created_at: 0,
  updated_at: 0,
};

test("experiment and simulation requests explicitly pin the selected version", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(job)));
  vi.stubGlobal("fetch", fetcher);
  await api.experiment(
    "workspace",
    {
      seed: 17,
      split: "forward",
      bootstrap_repetitions: 20,
      bkt_starts: 1,
      online_updates: true,
      ablations: false,
      calibration: true,
    },
    "historical-version",
  );
  fetcher.mockResolvedValueOnce(new Response(JSON.stringify(job)));
  await api.simulate("workspace", { repetitions: 30 }, "historical-version");
  for (const [url] of fetcher.mock.calls) {
    expect(
      new URL(String(url), "http://localhost").searchParams.get("dataset_id"),
    ).toBe("historical-version");
  }
});

test("prediction inspection and paired comparison request the chosen rolling fold", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(new Response("{}")));
  vi.stubGlobal("fetch", fetcher);
  await api.predictions("run", "bkt", 0, "identity", undefined, 2);
  await api.compare("run", "other-run", "bkt", "global", 2);
  for (const [url] of fetcher.mock.calls) {
    expect(
      new URL(String(url), "http://localhost").searchParams.get("fold"),
    ).toBe("2");
  }
});

test("an invalid successful payload fails runtime validation", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response('{"fake":true}')),
  );
  await expect(api.workspaces()).rejects.toMatchObject({
    name: "ApiError",
    status: 502,
  });
});

test("offline and HTML responses produce actionable API errors", async () => {
  const fetcher = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("Failed to fetch"))
    .mockResolvedValueOnce(
      new Response("<html>Unavailable</html>", { status: 503 }),
    );
  vi.stubGlobal("fetch", fetcher);
  await expect(api.workspaces()).rejects.toMatchObject({
    status: 0,
    message: expect.stringContaining("Start metricon serve"),
  });
  await expect(api.workspaces()).rejects.toMatchObject({
    status: 503,
    message: expect.stringContaining("non-JSON"),
  });
});

test("API errors retain their status and actionable server detail", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response('{"detail":"Dataset does not belong to workspace"}', {
        status: 422,
      }),
    ),
  );
  const promise = api.workspaces();
  await expect(promise).rejects.toBeInstanceOf(ApiError);
  await expect(promise).rejects.toMatchObject({
    status: 422,
    message: "Dataset does not belong to workspace",
  });
});
