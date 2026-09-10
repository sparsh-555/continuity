import { readFile } from 'node:fs/promises'

import { expect, test, type Page } from '@playwright/test'

const email = process.env.CONTINUITY_E2E_EMAIL
const password = process.env.CONTINUITY_E2E_PASSWORD

test.skip(!email || !password, 'Set CONTINUITY_E2E_EMAIL and CONTINUITY_E2E_PASSWORD to run against a disposable demo world.')

async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('ENTER_EMAIL').fill(email!)
  await page.getByPlaceholder('ENTER_PASSWORD').fill(password!)
  await page.getByRole('button', { name: 'SIGN_IN' }).click()
  await expect(page).toHaveURL(/\/lines$/)
}

async function deliverNotice(page: Page) {
  const document = await readFile('../docs/world-finals/notices/PCN-2026-114.pdf')
  const response = await page.request.post('http://localhost:8000/notices', {
    data: { document: document.toString('base64'), filename: 'PCN-2026-114.pdf' },
  })
  expect(response.ok()).toBeTruthy()
}

test('a delivered notice announces itself and refreshes rows and an open product line', async ({ page, context }) => {
  await signIn(page)
  await expect(page.getByText('Sensor node', { exact: true })).toBeVisible()

  const line = await context.newPage()
  await line.goto('/lines')
  await line.getByText('Sensor node', { exact: true }).click()
  await expect(line.getByRole('button', { name: /End of life \(0\)/ })).toBeVisible()

  await deliverNotice(page)

  await expect(page.getByText('AMS1117-3.3 affects 3 product lines.')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('1 notice', { exact: true }).first()).toBeVisible()
  await expect(line.getByText('AMS1117-3.3 affects 3 product lines.')).toBeVisible({ timeout: 15_000 })
  await expect(line.getByRole('button', { name: /End of life \(1\)/ })).toBeVisible()

  await page.getByRole('button', { name: 'Changes' }).click()
  await page.getByRole('button', { name: 'START THE REVIEW' }).click()
  await expect(page.getByRole('button', { name: 'RUN IT AGAIN' })).toBeVisible({ timeout: 15_000 })
  const sensorLane = page.getByRole('button', { name: /Sensor node/ })
  await expect(sensorLane).toBeVisible()
  await sensorLane.click()
  await expect(page.getByText(/^Trying .+\.$/).first()).toBeVisible()
  await expect(page.getByText(/SATISFIED · thermal dissipation/).first()).toBeVisible()
})
