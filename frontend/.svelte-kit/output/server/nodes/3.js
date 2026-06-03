

export const index = 3;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/backtest/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/3.4YdCDWyT.js","_app/immutable/chunks/3FlrN-ph.js"];
export const stylesheets = [];
export const fonts = [];
