import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 180000,
  fullyParallel: false,
  outputDir: "../.metricon/verification/browser/test-results",
  reporter: [
    ["list"],
    ["json", { outputFile: ".metricon/verification/browser/playwright.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8020",
    headless: true,
    launchOptions: existsSync(chrome) ? { executablePath: chrome } : undefined,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: ".venv/bin/metricon --root .metricon/e2e-store serve --port 8020",
    url: "http://127.0.0.1:8020/api/health",
    reuseExistingServer: false,
    timeout: 30000,
    cwd: fileURLToPath(new URL("..", import.meta.url)),
  },
});
