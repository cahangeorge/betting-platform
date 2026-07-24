import { expect, type Locator, type Page, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { backendRequest, withBearerToken } from '../helpers/backend';
import { runDirectSql, shouldSkipDirectDatabaseCleanup } from '../helpers/database';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import type { AuthSession } from '../helpers/types';

interface ScheduledJob {
	id: number;
	name: string;
	task_type: string;
	enabled: boolean;
	config?: Record<string, unknown> | null;
}

function escapeRegExp(value: string): string {
	return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function getScheduledJob(session: AuthSession, jobId: number): Promise<ScheduledJob> {
	return await backendRequest<ScheduledJob>(`/api/v1/jobs/${jobId}`, {
		headers: withBearerToken(session.token.access_token)
	});
}

async function createScheduledJobFromButton(
	page: Page,
	root: Locator,
	buttonName: string
): Promise<ScheduledJob> {
	const createResponse = page.waitForResponse(
		(response) =>
			response.url().includes('/api/v1/jobs') &&
			response.request().method() === 'POST'
	);

	await root.getByRole('button', { name: buttonName }).click();

	const response = await createResponse;
	expect(response.status()).toBe(201);
	return (await response.json()) as ScheduledJob;
}

async function deleteScheduledJobs(jobIds: number[]): Promise<void> {
	if (jobIds.length === 0 || shouldSkipDirectDatabaseCleanup()) return;

	try {
		await runDirectSql(`DELETE FROM scheduled_jobs WHERE id IN (${jobIds.join(', ')});`);
	} catch (error) {
		console.warn(
			`best-effort scheduled job cleanup skipped: ${
				error instanceof Error ? error.message : 'unknown error'
			}`
		);
	}
}


test('scheduled jobs can be saved from UI controls and toggled in hybrid mode', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);
	const createdJobIds: number[] = [];

	try {
		await page.goto('/prepare');
		const scrapeMain = page.locator('#main-content');
		await expect(scrapeMain.getByRole('heading', { name: 'Pregătește datele meciurilor', exact: true })).toBeVisible();
		await expect(page.getByTestId('prepare-panel')).toHaveAttribute('data-interactive', 'true');
		await scrapeMain.getByText('Setări avansate de rulare', { exact: true }).click();
		const autoScrapeToggle = scrapeMain.getByLabel('Activează programarea automată a colectării');
		await autoScrapeToggle.evaluate((element: HTMLInputElement) => element.click());
		await expect(autoScrapeToggle).toBeChecked();

		const autoscrapeJob = await createScheduledJobFromButton(page, scrapeMain, 'Salvează programarea automată');
		expect(autoscrapeJob.task_type).toBe('scrape_odds');
		expect(autoscrapeJob.config?.source_page).toBe('scrape');
		expect(autoscrapeJob.config?.area).toBe('scrape');
		createdJobIds.push(autoscrapeJob.id);

		await scrapeMain.getByText('Automatizare și fluxuri specializate', { exact: true }).click();
		const autoscrapeButton = scrapeMain
			.getByRole('button', { name: new RegExp(escapeRegExp(autoscrapeJob.name), 'i') })
			.first();
		await expect(autoscrapeButton).toBeVisible();
		await expect(autoscrapeButton).toContainText('activ');
		await autoscrapeButton.click();
		await expect.poll(async () => (await getScheduledJob(session, autoscrapeJob.id)).enabled).toBe(false);
		await expect(autoscrapeButton).toContainText('pauzat');

		await page.goto('/tickets');
		const ticketsMain = page.locator('#main-content');
		await expect(ticketsMain.getByRole('heading', { name: 'Bilete', exact: true })).toBeVisible();
		await expect(page.getByTestId('tickets-panel')).toHaveAttribute('data-interactive', 'true');
		await ticketsMain.getByRole('tab', { name: 'Active' }).click();
		await ticketsMain.getByText('Automatizare verificare', { exact: true }).click();
		await ticketsMain.getByLabel('Activează verificarea programată').check();
		await ticketsMain.getByLabel('Număr interval').fill('2');

		const verificationJob = await createScheduledJobFromButton(page, ticketsMain, 'Salvează verificarea automată');
		expect(verificationJob.task_type).toBe('verify_results');
		expect(verificationJob.config?.source_page).toBe('tickets');
		expect(verificationJob.config?.area).toBe('verification');
		createdJobIds.push(verificationJob.id);

		const verificationButton = page
			.locator('#main-content')
			.getByRole('button', { name: new RegExp(escapeRegExp(verificationJob.name), 'i') })
			.first();
		await expect(verificationButton).toBeVisible();
		await expect(verificationButton).toContainText('activ');
		await verificationButton.click();
		await expect.poll(async () => (await getScheduledJob(session, verificationJob.id)).enabled).toBe(false);
		await expect(verificationButton).toContainText('pauzat');
	} finally {
		await deleteScheduledJobs(createdJobIds);
		await cleanupSessionArtifacts(session);
	}
});
