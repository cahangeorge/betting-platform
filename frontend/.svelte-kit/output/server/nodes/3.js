

export const index = 3;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/backtest/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/3.DSj4tbq-.js","_app/immutable/chunks/P8c6hErI.js","_app/immutable/chunks/CpoPCl8A.js"];
export const stylesheets = [];
export const fonts = [];
