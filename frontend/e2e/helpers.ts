import { expect, type Page } from '@playwright/test'

export async function openSample(page: Page, dataset: string) {
  await page.goto('/')
  await page.waitForSelector('[data-testid=lib-row]')
  await page.locator(`[data-testid=lib-row][data-dataset="${dataset}"]`).first().click()
  await page.waitForSelector('[data-testid=step-node]')
  await expect(page.getByTestId('phase-strip')).toBeVisible()
}

export async function openById(page: Page, sampleId: string) {
  await page.goto('/')
  await page.getByTestId('lib-search').fill(sampleId.split('/').pop() ?? sampleId)
  await page.locator(`[data-testid=lib-row][data-sample-id="${sampleId}"]`).click()
  await page.waitForSelector('[data-testid=step-node]')
  await page.waitForTimeout(500)
}
