

export const index = 10;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/trades/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/10.Cu5tvSvb.js","_app/immutable/chunks/3FlrN-ph.js","_app/immutable/chunks/DutNeEKB.js","_app/immutable/chunks/C1gqFcTI.js","_app/immutable/chunks/C4cPfI8Q.js","_app/immutable/chunks/s800rUjo.js","_app/immutable/chunks/CqpbUPs7.js","_app/immutable/chunks/MbpM-SjM.js","_app/immutable/chunks/C3xQm-EV.js"];
export const stylesheets = ["_app/immutable/assets/10.De1oOA8V.css"];
export const fonts = [];
