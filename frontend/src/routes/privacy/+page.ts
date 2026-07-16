import type { PageLoad } from './$types';
import { createNoIndexPageMetaTags, createWebPageSchema } from '$lib/seo/site';

const title = 'Notă de confidențialitate';
const description =
	'Informații despre datele folosite de Betfront pentru cont, autentificare și fluxurile de analiză ale utilizatorului.';

export const load: PageLoad = ({ url }) => ({
	...createNoIndexPageMetaTags(url, { title, description }),
	pageJsonLd: createWebPageSchema(url, { name: `${title} | Betfront`, description })
});
