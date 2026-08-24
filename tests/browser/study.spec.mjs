import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/vote', async (route) => {
    await route.fulfill({ status: 201, contentType: 'application/json', body: '{"ok":true}' });
  });
  await page.route('**/api/leaderboard**', async (route) => {
    const url = new URL(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total_votes: 1,
        dataset: url.searchParams.get('dataset'),
        cohort: url.searchParams.get('cohort'),
        models: [{
          model_id: 'fixture', model_name: 'Fixture model', wins: 1, losses: 0,
          ties: 0, both_bad: 0, battles: 1, decisive_votes: 1, win_rate: 1,
        }],
      }),
    });
  });
});

test('arena keeps four choices, cohort isolation, whitespace, and model reveal', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'A is better' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Both are good' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Both are bad' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'B is better' })).toBeVisible();
  await expect(page.getByRole('button', { name: /skip/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Primary' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Efficiency' })).toBeVisible();

  const raw = page.locator('.sample-raw').first();
  await expect(raw).not.toHaveText('');
  const style = await raw.evaluate((node) => {
    const computed = getComputedStyle(node);
    return {
      whiteSpace: computed.whiteSpace,
      overflowWrap: computed.overflowWrap,
      tabSize: computed.tabSize,
    };
  });
  expect(style.whiteSpace).toBe('pre-wrap');
  expect(style.overflowWrap).toBe('anywhere');
  expect(style.tabSize).toBe('4');

  await page.getByRole('button', { name: 'A is better' }).click();
  const overlay = page.locator('[aria-live="polite"]');
  await expect(overlay).toBeVisible();
  await expect(overlay.locator('span').first()).not.toHaveText('');
  await expect(overlay.locator('span').nth(1)).toContainText('is better than');

  await page.waitForTimeout(2200);
  await page.getByRole('button', { name: 'Efficiency' }).click();
  await expect(page.getByRole('button', { name: 'Efficiency' })).toHaveClass(/bg-foreground/);
});

test('sample and leaderboard routes expose dataset and cohort selectors', async ({ page }) => {
  await page.goto('/samples');
  await expect(page.getByText('Sample browser — 17 models')).toBeVisible();
  await page.getByRole('button', { name: 'Efficiency' }).click();
  await expect(page.getByText('Sample browser — 32 models')).toBeVisible();
  await page.locator('a[href^="/samples/"]').first().click();
  await expect(page.locator('.sample-raw').first()).toBeVisible();

  await page.goto('/leaderboard');
  await expect(page.getByText('Fixture model')).toBeVisible();
  await page.getByRole('button', { name: 'Efficiency' }).click();
  await expect.poll(() => page.evaluate(() => localStorage.getItem(
    'samplebench:dlmbench-canonical-20260824-r5:cohort',
  ))).toBe('efficiency');
});

test('mobile keeps both full cards swipeable and all four choices visible', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'mobile-only layout check');
  await page.goto('/');
  const cards = page.getByRole('article');
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText('Sample A');
  await expect(cards.nth(1)).toContainText('Sample B');
  await expect(page.getByRole('button', { name: 'A is better' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Both are good' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Both are bad' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'B is better' })).toBeVisible();
});
