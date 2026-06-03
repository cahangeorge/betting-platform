

export const index = 3;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/backtest/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/3.CYycMS9z.js","_app/immutable/chunks/D1_b4O1c.js","_app/immutable/chunks/DwQVe2Pk.js","_app/immutable/chunks/Bsjbtr5B.js","_app/immutable/chunks/CpoPCl8A.js"];
export const stylesheets = [];
export const fonts = [];
