import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: process.env.CONTINUITY_E2E_URL ?? 'http://localhost:5173',
    screenshot: 'only-on-failure',
  },
})
