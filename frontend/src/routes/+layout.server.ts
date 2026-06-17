import type { LayoutServerLoad } from './$types';
import { redirect } from '@sveltejs/kit';

export const load: LayoutServerLoad = async ({ url, cookies }) => {
	if (url.pathname === '/' && !cookies.get('access_token')) {
		redirect(302, '/board');
	}

	const publicRoutes = ['/login', '/signup', '/board', '/about'];
	const isPublicRoute =
		publicRoutes.some((route) => url.pathname.startsWith(route));

	let user = null;

	const apiBase = process.env.BET_API_URL || 'http://localhost:8001';

	try {
		const token = cookies.get('access_token');
		if (token) {
			const meRes = await fetch(`${apiBase}/api/v1/auth/me`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (meRes.ok) {
				user = await meRes.json();
			}
		}
	} catch {
		user = null;
	}

	if (!user && !isPublicRoute) {
		redirect(302, '/login');
	}

	if (user && url.pathname === '/board') {
		redirect(302, '/');
	}

	return {
		user
	};
};
