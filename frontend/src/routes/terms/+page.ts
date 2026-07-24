import type { PageLoad } from './$types';
import { createNoIndexPageMetaTags, createWebPageSchema } from '$lib/seo/site';

const title = 'Termeni informativi';
const description =
	'Condițiile informative pentru folosirea Betfront ca instrument de analiză și revizuire a deciziilor sportive.';

export const load: PageLoad = ({ url }) => ({
	...createNoIndexPageMetaTags(url, { title, description }),
	pageJsonLd: createWebPageSchema(url, { name: `${title} | Betfront`, description })
});
