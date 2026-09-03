import { defineConfig } from "@playwright/test";

const runnerChromium = process.env.PW_CHROMIUM_EXECUTABLE_PATH;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    headless: true,
    screenshot: "off",
    trace: "off",
    video: "off",
    ...(runnerChromium
      ? { launchOptions: { executablePath: runnerChromium } }
      : {}),
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      WEB_LOCAL_SUPABASE_URL: "http://127.0.0.1:4173",
      WEB_LOCAL_SUPABASE_ANON_KEY: "public-test-anon-key",
      WEB_LOCAL_BACKEND_PROXY: "http://127.0.0.1:8000",
    },
  },
});
