import type { Actions, PageServerLoad } from './$types';
import { fail, redirect } from '@sveltejs/kit';
import { propagateAuthCookies } from '$lib/server/auth-cookies';
import { createNoIndexPageMetaTags } from '$lib/seo/site';

type SignupField = 'name' | 'email' | 'password' | 'confirmPassword' | 'legalAccepted';
type SignupErrors = Partial<Record<SignupField, string>>;

function formString(formData: FormData, key: string): string {
	const value = formData.get(key);
	return typeof value === 'string' ? value : '';
}

export const load: PageServerLoad = async ({ cookies, url }) => {
	const token = cookies.get('access_token');
	let authenticated = false;

	if (token) {
		try {
			const apiBase = process.env.BET_API_URL || 'http://localhost:8001';
			const response = await fetch(`${apiBase}/api/v1/auth/me`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			authenticated = response.ok;
		} catch {
			// Visitor is not authenticated; render the signup page.
		}
	}

	if (authenticated) {
		redirect(302, '/');
	}

	return createNoIndexPageMetaTags(url, {
		title: 'Creează un cont',
		description: 'Creează un cont Betfront pentru acces la spațiul privat de analiză.'
	});
};

export const actions: Actions = {
	default: async ({ cookies, request }) => {
		const formData = await request.formData();
		const name = formString(formData, 'name').trim();
		const email = formString(formData, 'email').trim().toLowerCase();
		const password = formString(formData, 'password');
		const confirmPassword = formString(formData, 'confirmPassword');
		const legalAccepted = formString(formData, 'legalAccepted') === 'accepted';
		const errors: SignupErrors = {};

		if (!name) errors.name = 'Numele este obligatoriu.';
		if (!email) errors.email = 'Adresa de email este obligatorie.';
		else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
			errors.email = 'Adresa de email nu este validă.';
		}
		if (!password) errors.password = 'Parola este obligatorie.';
		else if (password.length < 8) errors.password = 'Folosește cel puțin 8 caractere.';
		if (password !== confirmPassword) errors.confirmPassword = 'Parolele nu coincid.';
		if (!legalAccepted) {
			errors.legalAccepted =
				'Trebuie să confirmi vârsta legală aplicabilă și acceptarea documentelor informative.';
		}

		const values = { name, email, legalAccepted };
		if (Object.keys(errors).length > 0) {
			return fail(400, { errors, values });
		}

		try {
			const apiBase = process.env.BET_API_URL || 'http://localhost:8001';
			const response = await fetch(`${apiBase}/api/v1/auth/signup`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name, email, password })
			});

			if (!response.ok) {
				const errorMessage =
					response.status === 409
						? 'Există deja un cont pentru această adresă de email.'
						: 'Contul nu a putut fi creat. Verifică datele și reîncearcă.';
				return fail(response.status, { error: errorMessage, values });
			}

			if (!propagateAuthCookies(cookies, response.headers)) {
				return fail(502, {
					error: 'Contul a fost creat, dar sesiunea securizată nu a putut fi inițializată. Autentifică-te din nou.',
					values
				});
			}
		} catch {
			return fail(502, {
				error: 'Serviciul de creare a contului nu este disponibil. Reîncearcă.',
				values
			});
		}

		redirect(303, '/');
	}
};
