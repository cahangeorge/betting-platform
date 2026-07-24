import { goto } from '$app/navigation';
import { liveSocket } from '$lib/stores/liveSocket';
import { betslip } from '$lib/stores/betslip';
import { sessionEpoch } from './session-epoch';
export { SESSION_EXPIRED_EVENT } from './session-event';

/** One recovery path for explicit logout and expired sessions. */
export async function endSession(): Promise<void> {
	sessionEpoch.terminate();
	liveSocket.disconnect();
	betslip.setOwner(null);
	await goto('/login?reason=session-expired', { replaceState: true });
}
