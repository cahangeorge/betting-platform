import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('Prepare offers a compact preset-first data collection flow', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		await page.goto('/prepare');
		await expect(page.getByRole('heading', { name: 'Pregătește datele meciurilor' })).toBeVisible();
		await expect(page.getByRole('button', { name: 'Top 5 Europa' })).toBeVisible();
		await expect(page.getByRole('button', { name: /Arată toate țările/ })).toBeVisible();

		await page.getByRole('button', { name: 'Top 5 Europa' }).click();

		await expect(page.getByText(/5 ligi · 10 ani de istoric \+ mâine/)).toBeVisible();
		await expect(page.locator('#selection').getByText('Premier League', { exact: true }).first()).toBeVisible();
		await expect(page.locator('#selection details').first()).not.toHaveAttribute('open', '');
		await expect(page.getByRole('button', { name: 'Pornește colectarea' })).toBeEnabled();

		await page.setViewportSize({ width: 390, height: 844 });
		expect(
			await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
		).toBe(true);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});

test('Prepare paginates recent scrape jobs by the selected page and page size', async ({ browser }) => {
	const context = await browser.newContext({ serviceWorkers: 'block' });
	const page = await context.newPage();
	const session = await createAuthenticatedSession(context);
	const requestedPages: string[] = [];
	const jobs = Array.from({ length: 25 }, (_, index) => {
		const id = 25 - index;
		return {
			id,
			job_type: 'scrape_odds',
			status: 'completed',
			league: null,
			params: { command: 'historic' },
			started_at: null,
			completed_at: '2026-07-30T00:00:00Z',
			output: null,
			error: null,
			created_at: `2026-07-${String(30 - index).padStart(2, '0')}T00:00:00Z`
		};
	});

	await page.route('**/api/v1/data/scrape*', async (route) => {
		const url = new URL(route.request().url());
		const selectedPage = Number(url.searchParams.get('page') ?? '1');
		const perPage = Number(url.searchParams.get('per_page') ?? '20');
		const offset = (selectedPage - 1) * perPage;
		requestedPages.push(url.search);
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			headers: {
				'x-total-count': String(jobs.length),
				'x-page': String(selectedPage),
				'x-per-page': String(perPage)
			},
			body: JSON.stringify(jobs.slice(offset, offset + perPage))
		});
	});

	try {
		await page.goto('/prepare');
		const jobsCard = page.locator('#jobs');

		await expect(jobsCard.getByText('Se afișează 1–20 din 25 joburi.')).toBeVisible();
		await jobsCard.getByLabel('Pagină').selectOption('2');
		await expect(jobsCard.getByText('Se afișează 21–25 din 25 joburi.')).toBeVisible();

		await jobsCard.getByLabel('Rânduri').selectOption('10');
		await expect(jobsCard.getByText('Se afișează 1–10 din 25 joburi.')).toBeVisible();
		await jobsCard.getByLabel('Pagină').selectOption('3');
		await expect(jobsCard.getByText('Se afișează 21–25 din 25 joburi.')).toBeVisible();

		expect(requestedPages).toContain('?page=2&per_page=20');
		expect(requestedPages).toContain('?page=1&per_page=10');
		expect(requestedPages).toContain('?page=3&per_page=10');
	} finally {
		await cleanupSessionArtifacts(session);
		await context.close();
	}
});
