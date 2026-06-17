import type { PageLoad } from './$types';
import { redirect } from '@sveltejs/kit';
import { authApi } from '$lib/api/auth';

export const load: PageLoad = async () => {
	try {
		await authApi.getMe();
		redirect(302, '/');
	} catch {
		return {};
	}
};
