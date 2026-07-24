export const SESSION_EXPIRED_EVENT = 'bet:session-expired';

/** API modules only announce the terminal auth failure; the app shell owns recovery. */
export function notifySessionExpired(): void {
	if (typeof window !== 'undefined') window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}
