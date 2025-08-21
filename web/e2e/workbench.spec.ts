import { test, expect, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";

let page: Page;
let workspace = "";
let dataset = "";
let run = "";
let profile = "";
const errors: string[] = [];
const headers = { "X-Metricon-Client": "1" };
const evidence = ".metricon/verification/browser";

async function navigate(name: string) {
  await page
    .getByRole("navigation", { name: "Workbench navigation" })
    .getByRole("button", { name, exact: true })
    .click();
}
async function waitTask(id: string) {
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`/api/jobs/${id}`);
        const job = await response.json();
        if (job.status === "failed") throw Error(job.error || job.message);
        return job.status;
      },
      { timeout: 150000 },
    )
    .toBe("completed");
}

test.describe.serial("Scientific workbench", () => {
  test.beforeAll(async ({ browser }, testInfo) => {
    mkdirSync(evidence, { recursive: true });
    profile = testInfo.project.name;
    page = await browser.newPage({
      viewport: testInfo.project.use.viewport,
      isMobile: testInfo.project.use.isMobile,
      hasTouch: testInfo.project.use.hasTouch,
      userAgent: testInfo.project.use.userAgent,
    });
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (response.status() >= 500)
        errors.push(`${response.status()} ${response.url()}`);
    });
  });
  test.afterAll(async () => {
    await page.close();
  });

  test("blank workspace stays empty and migration is explicit", async () => {
    await page.goto("/");
    await page
      .getByRole("button", { name: "New workspace", exact: true })
      .click();
    await page
      .getByLabel("Workspace name")
      .fill("Browser acceptance workspace");
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Create workspace", exact: true })
      .click();
    await expect(
      page.getByText("No imported observations.", { exact: true }),
    ).toBeVisible();
    workspace = await page
      .getByLabel("WORKSPACE", { exact: true })
      .inputValue();
    const response = await page.request.get(`/api/workspaces/${workspace}`);
    expect((await response.json()).dataset_id).toBeNull();
    await navigate("Import laboratory");
    await expect(
      page.getByText("Explicit browser migration", { exact: true }),
    ).toBeVisible();
  });

  test("preview imports legacy events and exposes rejection records", async () => {
    const attempts = Array.from({ length: 30 }, (_, index) => ({
      id: `attempt-${index}`,
      correct: index % 5 === 0 ? "false" : index % 3 !== 0,
      type: "MULTIPLE_CHOICE",
    }));
    await page
      .getByLabel("Or paste an export")
      .fill(JSON.stringify({ q1: { attempts } }));
    await page
      .getByRole("button", { name: "Preview pasted source", exact: true })
      .click();
    await expect(
      page.getByText("Schema preview", { exact: true }),
    ).toBeVisible();
    const pending = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/workspaces/${workspace}/import`) &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Publish import job" }).click();
    const job = await (await pending).json();
    await waitTask(job.id);
    await expect(page.getByText("completed", { exact: true })).toBeVisible();
    await page
      .getByRole("button", { name: "Details", exact: true })
      .first()
      .click();
    const inspector = page.getByRole("button", {
      name: "Job record",
      exact: true,
    });
    if ((await inspector.getAttribute("aria-expanded")) === "false")
      await inspector.click();
    await expect(
      page.getByText(/correct must be a JSON boolean/),
    ).toBeVisible();
    await navigate("Observations");
    await expect(page.getByText("24 attempts", { exact: false })).toBeVisible();
    await page.screenshot({
      path: `${evidence}/${profile}-import-quality.png`,
      fullPage: true,
    });
  });

  test("explicit synthetic workspace trains real fitted models", async () => {
    const pending = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/demo") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Create synthetic sandbox", exact: true })
      .first()
      .click();
    const demo = await (await pending).json();
    workspace = demo.workspace.id;
    dataset = demo.workspace.dataset_id;
    await expect(
      page.getByText("Synthetic demo", { exact: true }),
    ).toBeVisible();
    await navigate("Experiment bench");
    const training = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith(
          `/api/workspaces/${workspace}/experiments`,
        ) && response.request().method() === "POST",
    );
    await page.getByLabel("Learner bootstrap draws").fill("20");
    await page
      .getByRole("button", { name: "Run experiment", exact: true })
      .click();
    const job = await (await training).json();
    await waitTask(job.id);
    run = (await (await page.request.get(`/api/jobs/${job.id}`)).json())
      .result_id;
    await navigate("Experiment bench");
    await expect(
      page.getByRole("cell", { name: "bkt", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: `${evidence}/${profile}-experiment.png`,
      fullPage: true,
    });
  });

  test("run comparison and calibration use saved predictions", async () => {
    await page.getByLabel("Comparison run").selectOption(run);
    await page
      .getByRole("button", { name: "Compare saved predictions" })
      .click();
    await expect(
      page.getByText("Paired learner resampling on identical test targets", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByText(/Calibration/).first()).toBeVisible();
    const response = await page.request.get(
      `/api/compare?left=${run}&right=${run}&left_model=bkt&right_model=global`,
    );
    expect(response.status()).toBe(200);
    expect((await response.json()).paired.available).toBe(true);
  });

  test("model microscope exposes parameters and observed replay", async () => {
    await navigate("Model microscope");
    await page.getByLabel("Fitted model").selectOption("bkt");
    await expect(
      page.getByText("Per-skill BKT parameters", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: `${evidence}/${profile}-model.png`,
      fullPage: true,
    });
    const response = await page.request.get(
      `/api/artifacts/${run}/models/bkt/replay?learner_id=demo-000&offset=0`,
    );
    expect(response.status()).toBe(200);
    expect((await response.json()).rows.length).toBeGreaterThan(0);
  });

  test("planner and misspecified simulation disclose assumptions", async () => {
    await navigate("Observations");
    await page
      .getByRole("combobox", { name: "Learner", exact: true })
      .selectOption("demo-000");
    await navigate("Policy laboratory");
    await page
      .getByRole("button", { name: /Build|Plan|Rank/ })
      .first()
      .click();
    await expect(
      page.getByText("Plan assumptions and factors", { exact: true }),
    ).toBeVisible();
    await page.getByLabel("Simulator regime").selectOption("misspecified");
    await page.getByLabel("Monte Carlo repetitions").fill("30");
    const pending = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith(
          `/api/workspaces/${workspace}/simulations`,
        ) && response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Compare policies", exact: true })
      .click();
    const job = await (await pending).json();
    await waitTask(job.id);
    await navigate("Policy laboratory");
    await expect(
      page.getByText("Synthetic policy experiment", { exact: true }),
    ).toBeVisible();
  });

  test("persistent cancellation stops a real running worker", async () => {
    const response = await page.request.post(
      `/api/workspaces/${workspace}/simulations`,
      {
        headers,
        data: {
          repetitions: 5000,
          budget_seconds: 86400,
          skills: Array.from({ length: 100 }, (_, i) => `s-${i}`),
        },
      },
    );
    expect(response.status()).toBe(202);
    const job = await response.json();
    await expect
      .poll(
        async () => {
          const response = await page.request.get(`/api/jobs/${job.id}`);
          return (await response.json()).status;
        },
        { timeout: 15000 },
      )
      .toBe("running");
    await expect(
      page
        .getByRole("navigation", { name: "Workbench navigation" })
        .getByRole("button", { name: "Jobs", exact: true }),
    ).toHaveAccessibleDescription(/^[1-9][0-9]* active jobs?$/, {
      timeout: 15000,
    });
    await navigate("Jobs");
    await page
      .getByRole("article")
      .filter({ has: page.getByText(job.id.slice(0, 12), { exact: true }) })
      .getByRole("button", { name: "Cancel job", exact: true })
      .click();
    await expect
      .poll(
        async () => {
          const result = await (
            await page.request.get(`/api/jobs/${job.id}`)
          ).json();
          return result.status;
        },
        { timeout: 15000 },
      )
      .toBe("canceled");
    expect(
      (await (await page.request.get(`/api/jobs/${job.id}`)).json()).result_id,
    ).toBeNull();
  });

  test("exports lineage keyboard tables and responsive rendering work", async () => {
    await navigate("Observations");
    await page.getByLabel("Canonical export format").selectOption("csv");
    await page
      .getByRole("button", { name: "Prepare export", exact: true })
      .click();
    await expect(
      page.getByRole("link", { name: "Download events.csv" }),
    ).toBeVisible();
    const url = await page
      .getByRole("link", { name: "Download events.csv" })
      .getAttribute("href");
    const download = await page.request.get(url!);
    expect(download.status()).toBe(200);
    expect(await download.text()).toContain("csv_encoding");
    await page.getByLabel("Question and skill aggregate table").focus();
    await page.keyboard.press("PageDown");
    const lineage = await page.request.get(`/api/lineage/${run}/verify`);
    expect((await lineage.json()).valid).toBe(true);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: `${evidence}/${profile}-mobile.png`,
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 2,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
  });
});
