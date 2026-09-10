import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  // Playwright's default is five seconds, which is a page that has already fetched. Every
  // assertion here is about something that arrives over the network — a product line's
  // check, a review's frames, a KiCad placement — and at five seconds this suite failed
  // roughly one run in three, in a different place each time. Fifteen is still short enough
  // that a real regression fails rather than hangs.
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.CONTINUITY_E2E_URL ?? 'http://localhost:5173',
    screenshot: 'only-on-failure',
  },
})
