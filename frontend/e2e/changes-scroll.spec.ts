import { expect, test } from '@playwright/test'

test('the change document can scroll its final line fully into the viewport', async ({ page }) => {
  await page.route('**/auth/me', (route) => route.fulfill({ json: {
    id: 'layout-test', email: 'layout@example.test', roles: ['design'], org_id: 'test', onboarded: true,
  } }))
  await page.route('**/notices', (route) => route.fulfill({ json: [] }))
  await page.route('**/decisions/waiting', (route) => route.fulfill({ json: [] }))
  await page.goto('/changes')
  const pane = page.getByText('The change request', { exact: true }).locator('..').locator('..')
  await expect(pane).toBeVisible()

  // Exercise the real pane and shell with a long document, independently of review data.
  await pane.evaluate((pane) => {
    pane.setAttribute('data-testid', 'document-pane')
    const content = document.createElement('div')
    content.style.height = '3000px'
    const end = document.createElement('p')
    end.textContent = 'End of change document'
    end.dataset.testid = 'document-end'
    pane.replaceChildren(content, end)
  })
  for (const height of [900, 600]) {
    await page.setViewportSize({ width: 1440, height })
    await page.getByTestId('document-pane').evaluate((pane) => { pane.scrollTop = pane.scrollHeight })
    await expect(page.getByTestId('document-end')).toBeInViewport({ ratio: 1 })
    const bounds = await page.getByTestId('document-pane').boundingBox()
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(height)
  }
})
