import type { LayoutServerLoad } from './$types';
import { error, redirect } from '@sveltejs/kit';
import { isPublicPagePath } from '../lib/seo/public-routes.ts';

export const load: LayoutServerLoad = async ({ url, route, locals }) => {
	if (route.id === null) {
		error(404, 'Pagina nu a fost găsită');
	}

	const isPublicRoute = isPublicPagePath(url.pathname);

	const user = locals.user;
	if (!user && url.pathname === '/') {
		redirect(302, '/about');
	}

	if (!user && !isPublicRoute) {
		redirect(302, '/login');
	}

	return {
		user
	};
};
