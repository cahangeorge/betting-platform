

export const index = 5;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/dashboard/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/5.2IDSEzfW.js","_app/immutable/chunks/3FlrN-ph.js","_app/immutable/chunks/C4cPfI8Q.js","_app/immutable/chunks/s800rUjo.js"];
export const stylesheets = ["_app/immutable/assets/5.M2sklF1r.css"];
export const fonts = [];
