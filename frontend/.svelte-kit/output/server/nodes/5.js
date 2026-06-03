

export const index = 5;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/dashboard/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/5.CZnwP-s1.js","_app/immutable/chunks/P8c6hErI.js","_app/immutable/chunks/D4NU76ih.js","_app/immutable/chunks/Bj5Gt00x.js"];
export const stylesheets = ["_app/immutable/assets/5.M2sklF1r.css"];
export const fonts = [];
