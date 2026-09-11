import { readFile } from 'node:fs/promises'

import { expect, test, type Page } from '@playwright/test'

const email = process.env.CONTINUITY_E2E_EMAIL
const password = process.env.CONTINUITY_E2E_PASSWORD

test.skip(!email || !password, 'Set CONTINUITY_E2E_EMAIL and CONTINUITY_E2E_PASSWORD to run against a disposable demo world.')
test.setTimeout(75_000)

// **This test needs a world nobody has touched.** It asserts `End of life (0)` before
// delivering the notice, so a second run against the same world fails on its own
// precondition rather than on anything it is testing. `./demo.sh` without `--keep` rebuilds
// the world, which is what makes the run repeatable.

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

  // **Leaving and coming back shows the review that ran.** Lane state used to be component
  // state, so navigating away abandoned the run and returning showed the stored change
  // requests where the trace had been. Nothing is pressed here and nothing is re-run: the
  // lanes are rebuilt from what the run wrote down, with the questions still answerable.
  await page.reload()
  await expect(page.getByRole('button', { name: 'RUN IT AGAIN' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('AMS1117-3.3 is going end of life.')).toBeVisible()
  await expect(page.getByRole('button', { name: /Sensor node/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'SIGN FOR MY DESK' }).first()).toBeVisible()

  await line.reload()
  // **Wait for the review to settle before asking for the board.** A replayed review walks
  // `trying` through every candidate as its frames arrive, and the pane places the board for
  // whichever one is showing — so clicking BOARD mid-replay starts a placement for an
  // intermediate candidate and the picture is replaced underneath the next assertion. The
  // change-request button only renders once the review is no longer running.
  await expect(line.getByRole('button', { name: /Change request · / })).toBeVisible({
    timeout: 30_000,
  })
  await expect(line.getByRole('button', { name: 'BOARD' })).toBeVisible()
  await line.getByRole('button', { name: 'BOARD' }).click()
  await expect(line.getByRole('button', { name: 'PLACE IT AGAIN' })).toBeVisible({ timeout: 45_000 })
  // **A first visit places, and placing is a KiCad run.** The pane chases `trying` while the
  // stored review replays, so a page opened on a reviewed product starts more than one of
  // them and they contend — the run for the settled candidate can be queued behind the ones
  // for candidates the review merely tried. That churn is a defect and is written down in
  // DEFERRED; this wait is sized for a real run rather than for the interval that used to be
  // enough when only one placement happened.
  await expect(
    line.getByText(/^FOOTPRINT: .+ → .+ \(DROP-IN\) · FITTED PART: AMS1117-3\.3 → .+$/),
  ).toBeVisible({ timeout: 45_000 })
  const after = line.locator('figure').filter({ hasText: /^AFTER · / })
  const afterOverlay = after.locator('rect[fill="#a78bfa"]')
  await expect(afterOverlay).toBeVisible()
  await expect(afterOverlay).toHaveAttribute('x', /^(?!0(?:\.0+)?$).+/)

  // Away from the board and back. The pane unmounts on the toggle, and both pictures used
  // to come back **blank**: the blob URL was created in a memo and revoked in an effect
  // cleanup, so a remount left the `<image>` pointing at a blob the browser no longer had.
  // Nothing on screen said anything was wrong. The overlay above is drawn by us and was
  // still there, which is why this fetches the picture itself.
  await line.getByRole('button', { name: 'COMPONENTS' }).click()
  await line.getByRole('button', { name: 'BOARD' }).click()
  await expect(line.getByRole('button', { name: 'PLACE IT AGAIN' })).toBeVisible()
  const drawn = line.locator('figure image').first()
  await expect(drawn).toHaveAttribute('href', /^blob:/)
  const readable = await drawn.evaluate(async (node) =>
    fetch(node.getAttribute('href') ?? '').then((response) => response.ok).catch(() => false),
  )
  expect(readable, 'the board picture is still there after a toggle').toBe(true)
})
