import type { Handle } from '@sveltejs/kit';
import { isIndexablePagePath } from '$lib/seo/site';
import { resolveRequestUser } from '$lib/server/auth-cookies';

export const handle: Handle = async ({ event, resolve }) => {
	const isAuthFormSubmission =
		event.request.method === 'POST' && ['/login', '/signup'].includes(event.url.pathname);
	if (event.route.id !== null && !isAuthFormSubmission) {
		event.locals.user = await resolveRequestUser(event.cookies, event.fetch);
	}

	const response = await resolve(event);

	if (response.headers.get('content-type')?.includes('text/html')) {
		const isAnonymousMarketingPage =
			isIndexablePagePath(event.url.pathname) &&
			!event.cookies.get('access_token') &&
			!event.cookies.get('refresh_token');

		if (isAnonymousMarketingPage) {
			response.headers.set(
				'Cache-Control',
				'public, max-age=0, s-maxage=300, stale-while-revalidate=86400'
			);
			appendVary(response.headers, 'Cookie');
			response.headers.delete('Pragma');
		} else {
			response.headers.set('Cache-Control', 'private, no-cache, no-store, must-revalidate');
			response.headers.set('Pragma', 'no-cache');
		}
	}

	return response;
};

function appendVary(headers: Headers, value: string) {
	const current = headers.get('Vary');
	const values = new Set((current ?? '').split(',').map((item) => item.trim()).filter(Boolean));
	values.add(value);
	headers.set('Vary', [...values].join(', '));
}
