# Politică pachete Svelte pentru Bet frontend

Document pentru agenți. Se aplică doar platformei active `frontend/` (SvelteKit/Svelte 5).

## Principii

- Nu instala global pachete runtime Svelte pentru acest proiect. Tooling-ul global/rulat de agent rămâne tooling: Context7, Playwright, Chrome DevTools MCP, Svelte MCP și skill-uri Codex/OMX.
- Pachetele runtime sunt per-proiect: se adaugă numai în `frontend/package.json` și lockfile, prin `pnpm`, din `frontend/`.
- Nu instala dependențe preventiv. Adaugă un pachet doar când există o nevoie concretă în UI și verificare prin `pnpm check` / teste relevante.

## Ce există acum în `frontend/package.json`

Confirmat în dependențele curente:

- SvelteKit/Svelte/Vite: `@sveltejs/kit`, `svelte`, `vite`, `@sveltejs/vite-plugin-svelte`, `@sveltejs/adapter-node`.
- Tailwind 4: `tailwindcss`, `@tailwindcss/vite`, `postcss`, `autoprefixer`.
- Primitive/UI helpers compatibile shadcn-style: `bits-ui`, `class-variance-authority`, `clsx`, `tailwind-merge`.
- Iconuri: `lucide-svelte`.
- Grafice: `layerchart`.
- Test/diagnostic: `@playwright/test`, `svelte-check`, `typescript`.

Nu este confirmat acum: `shadcn-svelte`, `@tanstack/svelte-table`, `@tanstack/svelte-virtual`, `virtua`, `sveltekit-superforms`, `formsnap`, `@sentry/sveltekit`, `svelte-meta-tags`, `super-sitemap`.

## Recomandări prioritizate pentru Bet

1. `shadcn-svelte`: prima opțiune pentru extinderea design system-ului, dar numai dacă nu este deja instalat/generat în proiect. Verifică întâi `package.json` și componentele existente.
2. `@tanstack/svelte-table`: pentru tabele complexe din board, odds și tickets (sortare, filtrare, coloane, stări).
3. `@tanstack/svelte-virtual` sau `virtua`: doar pentru liste/tabele lungi unde randarea devine măsurabil grea.
4. `sveltekit-superforms` + `formsnap`: doar dacă formularele devin complexe (validare bogată, server actions, erori pe câmpuri, formulare reutilizabile).
5. `@sentry/sveltekit`: mai târziu, pentru hardening în producție și observabilitate erori frontend.
6. `svelte-meta-tags` / `super-sitemap`: prioritate joasă pentru Bet acum; folosește mai întâi metadata SvelteKit și conținutul existent.

## Checklist: instalează doar când e nevoie

- Problema nu se rezolvă simplu cu SvelteKit/Svelte, componentele existente sau utilitare locale.
- Pachetul este necesar pentru un ecran/flow concret, nu pentru „poate va trebui”.
- `frontend/package.json` nu îl are deja.
- Instalarea se face din `frontend/` cu `pnpm`, iar `package.json` + lockfile rămân versionate împreună.
- După schimbare rulează cel puțin `pnpm check`; adaugă teste unit/e2e când comportamentul UI se schimbă.

## Evită pentru moment

- Instalări globale de pachete runtime Svelte.
- Biblioteci UI mari care dublează Tailwind/bits-ui/shadcn-style fără nevoie clară.
- Pachete SEO dedicate înainte să existe obiectiv SEO concret.
- Virtualizare pentru liste mici.
- Biblioteci de formulare pentru formulare simple.
- Orice dependență nouă fără verificarea impactului în `frontend/package.json` și lockfile.
