import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('countries and leagues workflow is linked under configurations', async () => {
	const navigation = await readFile('src/lib/navigation.ts', 'utf8');
	const sidebar = await readFile('src/lib/components/Sidebar.svelte', 'utf8');
	const palette = await readFile('src/lib/components/CommandPalette.svelte', 'utf8');

	assert.match(navigation, /configurationNavigation/);
	assert.match(navigation, /\/settings\/countries-leagues/);
	assert.match(navigation, /Listare țări\/ligi/);
	assert.match(sidebar, /Configurații/);
	assert.match(sidebar, /configurationNavigation/);
	assert.match(palette, /countries-leagues/);
});

test('countries and leagues page exposes multi-select and bounded retry controls', async () => {
	const page = await readFile('src/routes/settings/countries-leagues/+page.svelte', 'utf8');
	const api = await readFile('src/lib/api/catalog.ts', 'utf8');

	assert.match(page, /Selectare multiplă țări/);
	assert.match(page, /Număr maxim de încercări/);
	assert.match(page, /Caută și validează ligile/);
	assert.match(page, /Starea ligilor/);
	assert.match(page, /md:hidden/);
	assert.match(page, /hidden overflow-x-auto md:block/);
	assert.match(api, /football\/discover-validate/);
	assert.match(api, /max_attempts/);
	assert.match(api, /batch_size/);
});
