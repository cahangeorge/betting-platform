import type { PageLoad } from './$types';
import { createPublicPageMetaTags, createWebPageSchema } from '$lib/seo/site';

const title = 'Utilizare responsabilă';
const description =
	'Principii Betfront pentru folosirea responsabilă a analizelor sportive: buget prestabilit, limite clare, pauze și absența promisiunilor de câștig.';

export const load: PageLoad = ({ url }) => ({
	...createPublicPageMetaTags(url, { title, description }),
	pageJsonLd: createWebPageSchema(url, {
		name: `${title} | Betfront`,
		description
	})
});
