import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

const viewportWidths = [1920, 1440, 1024, 768, 390, 320] as const;

const routes = [
	{ name: 'Home', path: '/', heading: 'Deciziile de azi' },
	{ name: 'Prepare', path: '/prepare', heading: 'Pregătește datele meciurilor' },
	{ name: 'Analyze', path: '/analyze', heading: 'Analiză' },
	{ name: 'Opportunities', path: '/opportunities?view=value', heading: 'VALUE BET FEED' },
	{ name: 'Tickets', path: '/tickets', heading: 'Bilete' },
	{ name: 'Monitoring', path: '/monitoring', heading: 'Monitoring and automation' },
	{ name: 'Data explorer', path: '/prepare/data', heading: 'Data Hub' },
	{ name: 'Strategies', path: '/settings/strategies', heading: 'CONFIGURATII' },
	{ name: 'Countries and leagues', path: '/settings/countries-leagues', heading: 'Listare țări/ligi' },
	{ name: 'Account', path: '/settings/account', heading: 'ACCOUNT' }
] as const;

test.describe('page-level horizontal overflow', () => {
	for (const route of routes) {
		test(`${route.name} does not create document-level horizontal scroll at supported widths`, async ({
			page,
			context
		}) => {
			const session = await createAuthenticatedSession(context);

			try {
				for (const width of viewportWidths) {
					await test.step(`${route.name} at ${width}px`, async () => {
						await page.setViewportSize({ width, height: 900 });
						await page.goto(route.path);
						await expect(
							page.getByRole('heading', { name: route.heading, exact: true }).first()
						).toBeVisible();
						await page.waitForLoadState('networkidle');

						const overflow = await page.evaluate(() => ({
							clientWidth: document.documentElement.clientWidth,
							scrollWidth: document.documentElement.scrollWidth
						}));

						expect(overflow.scrollWidth, `${route.name} at ${width}px`).toBeLessThanOrEqual(
							overflow.clientWidth
						);
					});
				}
			} finally {
				await cleanupSessionArtifacts(session);
			}
		});
	}
});
