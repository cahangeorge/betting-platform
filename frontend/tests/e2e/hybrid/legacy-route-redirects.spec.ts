import { expect, test } from '@playwright/test';

for (const [legacy, canonical] of [
	['/scrape?league=romania', '/prepare?league=romania'],
	['/predict?run=42', '/analyze?run=42'],
	['/value-bets?league=serie-a', '/opportunities?league=serie-a&view=value'],
	['/live?status=running', '/opportunities?status=running&view=live']
] as const) {
	test(`${legacy} redirects permanently to ${canonical}`, async ({ request }) => {
		const response = await request.get(legacy, { maxRedirects: 0 });
		expect(response.status()).toBe(308);
		expect(response.headers().location).toBe(canonical);
	});
}
