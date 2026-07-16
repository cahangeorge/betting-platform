import type { PageLoad } from './$types';
import { createPublicPageMetaTags, createWebPageSchema } from '$lib/seo/site';

const title = 'Metodologie și limite';
const description =
	'Află cum Betfront pregătește datele, rulează modelele statistice și păstrează trasabilitatea rezultatelor, împreună cu limitele interpretării.';

export const load: PageLoad = ({ url }) => ({
	...createPublicPageMetaTags(url, { title, description }),
	pageJsonLd: createWebPageSchema(url, {
		name: `${title} | Betfront`,
		description
	})
});
