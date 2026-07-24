import type { ApiError } from '../types.ts';

export function formatApiErrorDetail(detail: ApiError['detail'] | unknown): string {
	if (typeof detail === 'string' && detail.trim()) {
		return detail;
	}

	if (detail && typeof detail === 'object') {
		const payload = detail as Record<string, unknown>;
		const message = typeof payload.message === 'string' ? payload.message.trim() : '';
		if (message) {
			const resolved = payload.resolved_records_count;
			const unresolved = payload.unresolved_records_count;
			if (typeof resolved === 'number' && typeof unresolved === 'number') {
				return `${message} (${resolved} rezolvate, ${unresolved} nerezolvate)`;
			}
			return message;
		}
	}

	return 'Cererea a eșuat din cauza unui răspuns API invalid.';
}
