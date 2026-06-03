/** Svelte stores for shared state. */
import { writable } from 'svelte/store';

export const user = writable<{ id: string; email: string } | null>(null);
export const token = writable<string | null>(null);
export const bankrolls = writable<Array<Record<string, unknown>>>([]);
export const activeBankrollId = writable<string | null>(null);
export const matches = writable<Array<Record<string, unknown>>>([]);
export const botStatus = writable<Record<string, unknown>>({ running: false, cycles: 0 });
export const trades = writable<Array<Record<string, unknown>>>([]);
export const loading = writable(false);
