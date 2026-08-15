import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './tests/manual',
  workers: 1,
  timeout: 120000,
  retries: 0,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
