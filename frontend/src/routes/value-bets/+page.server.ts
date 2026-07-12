import type { PageServerLoad } from './$types';
import { redirectLegacyRoute } from '$lib/navigation/legacy-redirect';

export const load: PageServerLoad = ({ url }) => redirectLegacyRoute(url, '/opportunities', { view: 'value' });
