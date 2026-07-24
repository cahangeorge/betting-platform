export type PrepareIntervalUnit = 'Hours' | 'Days' | 'Weeks';

export const PREPARE_INTERVAL_UNIT_OPTIONS: { value: PrepareIntervalUnit; label: string }[] = [
	{ value: 'Hours', label: 'Ore' },
	{ value: 'Days', label: 'Zile' },
	{ value: 'Weeks', label: 'Săptămâni' }
];

export function autoScrapeIntervalHours(value: string, unit: PrepareIntervalUnit): number {
	const interval = Math.max(1, Number.parseInt(value, 10) || 1);
	return interval * ({ Hours: 1, Days: 24, Weeks: 168 } as const)[unit];
}
