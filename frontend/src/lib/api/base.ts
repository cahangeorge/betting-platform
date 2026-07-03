export function apiBaseUrl(locationLike?: Location | URL): string {
	const configured = (import.meta as unknown as { env?: { PUBLIC_API_URL?: string } }).env?.PUBLIC_API_URL;
	if (configured) return configured.replace(/\/$/, '');

	const current =
		locationLike ??
		(typeof window !== 'undefined' ? window.location : undefined);

	if (!current) return '';

	return '';
}
