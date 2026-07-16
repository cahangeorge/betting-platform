import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('global strategy mutations are rendered only for administrators', async () => {
	const source = await readFile('src/routes/configuratii/+page.svelte', 'utf8');

	assert.match(source, /const isAdmin = \$derived\(Boolean\(\$page\.data\.user\?\.is_admin\)\)/);
	assert.match(source, /if \(!isAdmin\) return/);
	assert.match(source, /Doar administratorii pot crea, edita sau duplica strategii globale/);
	assert.match(source, /\{#if isAdmin\}[\s\S]*Edit[\s\S]*Duplicate[\s\S]*\{\/if\}/);
});
