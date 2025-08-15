import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const chromium = {
  browserName: "chromium" as const,
  launchOptions: existsSync(chrome) ? { executablePath: chrome } : undefined,
};
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 180000,
  fullyParallel: false,
  outputDir: "../.metricon/verification/browser/test-results",
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: fileURLToPath(
          new URL(
            "../.metricon/verification/browser/playwright.json",
            import.meta.url,
          ),
        ),
      },
    ],
  ],
  use: {
    baseURL: "http://127.0.0.1:8020",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "laptop-chromium",
      use: { ...chromium, viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "mobile-chromium",
      use: {
        ...chromium,
        viewport: { width: 360, height: 800 },
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: "mobile-webkit",
      use: { ...devices["iPhone 13"], browserName: "webkit" },
    },
  ],
  webServer: {
    command: ".venv/bin/metricon --root .metricon/e2e-store serve --port 8020",
    url: "http://127.0.0.1:8020/api/health",
    reuseExistingServer: false,
    timeout: 30000,
    cwd: fileURLToPath(new URL("..", import.meta.url)),
  },
});
