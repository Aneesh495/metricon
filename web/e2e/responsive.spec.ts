import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const headers = { "X-Metricon-Client": "1" };
let workspace = "";
let dataset = "";
let run = "";
let globalRun = "";

async function complete(request: APIRequestContext, id: string) {
  await expect
    .poll(
      async () => {
        const job = await (await request.get(`/api/jobs/${id}`)).json();
        if (["failed", "canceled"].includes(job.status))
          throw Error(job.error || job.message);
        return job.status;
      },
      { timeout: 150000 },
    )
    .toBe("completed");
  return (await (await request.get(`/api/jobs/${id}`)).json())
    .result_id as string;
}

async function navigate(page: Page, name: string) {
  await page
    .getByRole("navigation", { name: "Workbench navigation" })
    .getByRole("button", { name, exact: true })
    .click();
  await expect(page.locator("main h1")).toBeVisible();
}

test.beforeAll(async ({ request }) => {
  const demo = await (
    await request.post("/api/demo", {
      headers,
      data: { seed: 41, learners: 8, attempts: 60 },
    })
  ).json();
  workspace = demo.workspace.id;
  dataset = demo.workspace.dataset_id;
  const upload = await (
    await request.post("/api/uploads", {
      headers,
      multipart: {
        file: {
          name: "extension.json",
          mimeType: "application/json",
          buffer: Buffer.from(
            JSON.stringify({
              extra: { attempts: [{ id: "extension", correct: false }] },
            }),
          ),
        },
      },
    })
  ).json();
  const imported = await (
    await request.post(`/api/workspaces/${workspace}/import`, {
      headers,
      data: {
        upload_id: upload.upload_id,
        options: {
          format: "legacy",
          namespace: "test-extension",
          learner: "extra-learner",
        },
      },
    })
  ).json();
  await complete(request, imported.id);
  expect(
    (await (await request.get(`/api/workspaces/${workspace}`)).json())
      .dataset_id,
  ).not.toBe(dataset);
  const training = await request.post(
    `/api/workspaces/${workspace}/experiments?dataset_id=${dataset}`,
    {
      headers,
      data: {
        split: "rolling",
        rolling_folds: 3,
        families: ["global", "bkt"],
        bootstrap_repetitions: 20,
        bkt_starts: 1,
        bkt_max_iterations: 35,
        ablations: false,
      },
    },
  );
  expect(training.status()).toBe(202);
  const job = await training.json();
  expect(job.dataset_id).toBe(dataset);
  run = await complete(request, job.id);
  const baseline = await request.post(
    `/api/workspaces/${workspace}/experiments?dataset_id=${dataset}`,
    {
      headers,
      data: {
        families: ["global"],
        bootstrap_repetitions: 20,
        ablations: false,
      },
    },
  );
  expect(baseline.status()).toBe(202);
  globalRun = await complete(request, (await baseline.json()).id);
});

for (const width of [320, 360, 390, 768, 1280, 1440]) {
  test(`all analytical sections fit a ${width}px viewport`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (response.status() >= 500)
        errors.push(`${response.status()} ${response.url()}`);
    });
    await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 });
    await page.goto(
      `/?workspace=${workspace}&version=${dataset}&tab=observations`,
    );
    for (const name of [
      "Observations",
      "Import laboratory",
      "Experiment bench",
      "Model microscope",
      "Policy laboratory",
      "Provenance",
      "Jobs",
    ]) {
      await navigate(page, name);
      try {
        await expect
          .poll(() =>
            page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth + 2,
            ),
          )
          .toBe(true);
      } catch (error) {
        const layout = await page.evaluate(() => ({
          width: innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          overflow: Array.from(document.querySelectorAll("body, body *"))
            .filter((element) => {
              if (element.closest("nav")) return false;
              return (
                element.getBoundingClientRect().right > innerWidth + 2 ||
                element.scrollWidth > element.clientWidth + 2
              );
            })
            .slice(0, 80)
            .map((element) => ({
              tag: element.tagName,
              class: element.className,
              text: element.textContent?.slice(0, 80),
              right: element.getBoundingClientRect().right,
              width: element.clientWidth,
              scroll: element.scrollWidth,
              overflow: getComputedStyle(element).overflowX,
            })),
        }));
        await testInfo.attach(`${name}-overflow`, {
          body: JSON.stringify(layout, null, 2),
          contentType: "application/json",
        });
        throw error;
      }
      if (width === 390 || width === 1440)
        await page.screenshot({
          path: `.metricon/verification/browser/${testInfo.project.name}-${width}-${name.replaceAll(" ", "-")}.png`,
          fullPage: true,
        });
    }
    expect(errors).toEqual([]);
  });
}

test("rolling diagnostics and model replay stay on the selected fold", async ({
  page,
}) => {
  await page.goto(
    `/?workspace=${workspace}&version=${dataset}&tab=experiments`,
  );
  await page.getByLabel("Choose experiment").selectOption(run);
  const prediction = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      url.pathname.endsWith("/predictions") &&
      url.searchParams.get("fold") === "1"
    );
  });
  await page.getByLabel("Select temporal fold").selectOption("1");
  const rows = await (await prediction).json();
  const report = await (
    await page.request.get(`/api/artifacts/${run}/report`)
  ).json();
  expect(rows.total).toBe(report.folds[1].models.global.test.n);
  await expect(
    page.getByText(
      "Every row is a saved test prediction from temporal fold 2.",
    ),
  ).toBeVisible();
  await page.getByLabel("Comparison run").selectOption(run);
  const comparison = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/compare",
  );
  await page.getByRole("button", { name: "Compare saved predictions" }).click();
  expect(new URL((await comparison).url()).searchParams.get("fold")).toBe("1");
  await navigate(page, "Model microscope");
  await page
    .getByRole("combobox", { name: "Experiment", exact: true })
    .selectOption(run);
  await page.getByLabel("Fitted model").selectOption("bkt");
  const replay = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      url.pathname.endsWith("/replay") && url.searchParams.get("fold") === "1"
    );
  });
  await page.getByLabel("Model temporal fold").selectOption("1");
  await expect(
    page.getByRole("combobox", { name: "Model temporal fold", exact: true }),
  ).toHaveValue("1");
  expect((await replay).status()).toBe(200);
});

test("the model microscope supports runs without BKT", async ({ page }) => {
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/models/") && response.status() >= 400)
      failures.push(response.url());
  });
  await page.goto(
    `/?workspace=${workspace}&version=${dataset}&artifact=${globalRun}&tab=models`,
  );
  await expect(
    page.getByRole("combobox", { name: "Fitted model", exact: true }),
  ).toHaveValue("global");
  await expect(
    page.getByRole("button", {
      name: "Exact serialized parameters",
      exact: true,
    }),
  ).toBeVisible();
  expect(failures).toEqual([]);
  await navigate(page, "Experiment bench");
  await page.getByLabel("Choose experiment").selectOption(globalRun);
  await page.getByLabel("Comparison run").selectOption(globalRun);
  await expect(
    page.getByRole("combobox", { name: "Current run model", exact: true }),
  ).toHaveValue("global");
  await page
    .getByRole("button", { name: "Compare saved predictions", exact: true })
    .click();
  const result = page.getByRole("button", {
    name: "Observed comparison, metrics, calibration and paired uncertainty",
    exact: true,
  });
  await expect(result).toBeVisible();
  await page.getByLabel("Comparison run").selectOption(run);
  await expect(result).toHaveCount(0);
  await page
    .getByText("Show calibration data table", { exact: true })
    .first()
    .click();
  await expect(
    page.getByLabel("Calibration data table").first().locator("tbody tr"),
  ).toHaveCount(10);
});

test("missing workspaces and foreign dataset links cannot mislabel observations", async ({
  page,
}) => {
  await page.goto(`/?workspace=does-not-exist&version=${dataset}`);
  await expect(
    page.getByRole("heading", { name: "This workspace is unavailable" }),
  ).toBeVisible();
  await expect(page.getByLabel("Dataset version")).toHaveValue("");
  const other = await page.request.post("/api/workspaces", {
    headers,
    data: { name: "Independent empty workspace" },
  });
  const identifier = (await other.json()).id;
  const scans: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes(`/api/datasets/${dataset}/`))
      scans.push(request.url());
  });
  await page.goto(`/?workspace=${identifier}&version=${dataset}`);
  await expect(
    page.getByRole("heading", {
      name: "This dataset version is unavailable in the selected workspace",
    }),
  ).toBeVisible();
  expect(scans).toEqual([]);
  await page
    .getByRole("button", { name: "Open the latest committed version" })
    .click();
  await expect(
    page.getByRole("heading", { name: "No imported observations." }),
  ).toBeVisible();
});

test("network and clipboard failures show recoverable controls", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/workspaces", (route) => route.abort());
  await page.goto(`/?workspace=${workspace}&version=${dataset}`);
  await expect(page.getByRole("alert")).toContainText(
    "Cannot reach the local laboratory. Start metricon serve and retry.",
  );
  await page.unroute("**/api/workspaces");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Evidence before inference." }),
  ).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: () => Promise.reject(Error("denied")) },
    });
  });
  await page
    .getByRole("button", { name: "Copy JSON", exact: true })
    .first()
    .click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Clipboard access is unavailable." }),
  ).toHaveText(
    "Clipboard access is unavailable. Use Download JSON to save this artifact.",
  );
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download JSON", exact: true })
    .first()
    .click();
  expect((await download).suggestedFilename()).toBe("metricon-artifact.json");
  expect(errors).toEqual([]);
});

test("an unavailable interface module recovers through reload", async ({
  page,
}) => {
  await page.route("**/assets/Jobs-*.js", (route) => route.abort());
  await page.goto(`/?workspace=${workspace}&version=${dataset}`);
  await navigate(page, "Jobs");
  await expect(
    page.getByRole("heading", { name: "The workbench could not open." }),
  ).toBeVisible();
  await page.unroute("**/assets/Jobs-*.js");
  await page
    .getByRole("button", { name: "Reload workbench", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Observe the work in flight." }),
  ).toBeVisible();
  await expect(page.getByLabel("Dataset version")).toHaveValue(dataset);
});

test("deep links reload and browser history preserve the dataset and learner", async ({
  page,
}) => {
  await page.goto(
    `/?workspace=${workspace}&version=${dataset}&artifact=${run}&tab=provenance`,
  );
  await expect(page.getByLabel("Artifact selection")).toHaveValue(run);
  await navigate(page, "Observations");
  await page
    .getByRole("combobox", { name: "Learner", exact: true })
    .selectOption("demo-000");
  await page.getByLabel("Find learner ID").fill("demo-001");
  await expect(
    page.getByRole("combobox", { name: "Learner", exact: true }),
  ).toHaveValue("demo-000");
  await page.reload();
  await expect(page.getByLabel("Dataset version")).toHaveValue(dataset);
  await expect(
    page.getByRole("combobox", { name: "Learner", exact: true }),
  ).toHaveValue("demo-000");
  await page.getByLabel("Inspect timeline bin").selectOption("0");
  await expect(page.locator(".chart-caption").first()).toContainText("Bin 1:");
  await navigate(page, "Jobs");
  await page.goBack();
  await expect(
    page.getByRole("heading", { name: "Evidence before inference." }),
  ).toBeVisible();
  await expect(page.getByLabel("Dataset version")).toHaveValue(dataset);
});

test("a prepared export is cleared when the dataset version changes", async ({
  page,
}) => {
  await page.goto(
    `/?workspace=${workspace}&version=${dataset}&tab=observations`,
  );
  await page
    .getByRole("button", { name: "Prepare export", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Download events.json" }),
  ).toBeVisible();
  const versions = await (
    await page.request.get(`/api/workspaces/${workspace}/datasets`)
  ).json();
  const newer = versions.find(
    (version: { id: string }) => version.id !== dataset,
  ).id;
  await page.getByLabel("Dataset version").selectOption(newer);
  await expect(
    page.getByRole("link", { name: "Download events.json" }),
  ).toHaveCount(0);
});

test("workspace modal traps keyboard focus and rejects a blank name", async ({
  page,
}) => {
  await page.goto(`/?workspace=${workspace}&version=${dataset}`);
  await page
    .getByRole("button", { name: "New workspace", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(page.getByLabel("Workspace name")).toBeFocused();
  await page.getByLabel("Workspace name").fill("   ");
  await expect(
    dialog.getByRole("button", { name: "Create workspace", exact: true }),
  ).toBeDisabled();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Workspace name")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});
