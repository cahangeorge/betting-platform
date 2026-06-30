const LOCAL_FRONTEND_PORTS = new Set(['5174', '5175']);

export function apiBaseUrl(locationLike?: Location | URL): string {
	const configured = (import.meta as unknown as { env?: { PUBLIC_API_URL?: string } }).env?.PUBLIC_API_URL;
	if (configured) return configured.replace(/\/$/, '');

	const current =
		locationLike ??
		(typeof window !== 'undefined' ? window.location : undefined);

	if (!current) return '';

	if (LOCAL_FRONTEND_PORTS.has(current.port)) {
		return `${current.protocol}//${current.hostname}:8001`;
	}

	return '';
}
