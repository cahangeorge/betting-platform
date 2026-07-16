import type { PageLoad } from './$types';
import { createPublicPageMetaTags, createWebPageSchema } from '$lib/seo/site';

const title = 'Despre platformă';
const description =
	'Vezi cum Betfront organizează datele sportive, analiza statistică și revizuirea biletelor într-un flux trasabil, fără promisiuni de câștig.';

export const load: PageLoad = async ({ url }) => {
	return {
		...createPublicPageMetaTags(url, { title, description }),
		pageJsonLd: createWebPageSchema(url, {
			type: 'AboutPage',
			name: `${title} | Betfront`,
			description
		})
	};
};
