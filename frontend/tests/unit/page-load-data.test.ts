import test from 'node:test';
import assert from 'node:assert/strict';
import { readdir } from 'node:fs/promises';
import path from 'node:path';

const routesDir = path.resolve('src/routes');

async function findServerRoutesWithUniversalLoad(dir: string): Promise<string[]> {
	const entries = await readdir(dir, { withFileTypes: true });
	const fileNames = new Set(entries.filter((entry) => entry.isFile()).map((entry) => entry.name));
	const routes = fileNames.has('+page.server.ts') && fileNames.has('+page.ts') ? [dir] : [];

	for (const entry of entries) {
		if (entry.isDirectory()) {
			routes.push(...(await findServerRoutesWithUniversalLoad(path.join(dir, entry.name))));
		}
	}

	return routes;
}

test('server-loaded page routes avoid redundant universal load shims', async () => {
	const routes = await findServerRoutesWithUniversalLoad(routesDir);

	assert.deepEqual(
		routes.map((route) => path.relative(routesDir, route)).sort(),
		[],
		'routes with +page.server.ts should not add a no-op +page.ts that can shadow server data'
	);
});
