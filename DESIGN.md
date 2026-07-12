# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-07-12
- Primary product surfaces: SvelteKit workbench routes in `frontend/src/routes/`
- Evidence reviewed: `frontend/src/routes/prepare/+page.svelte`, shared UI primitives, live desktop capture of `/prepare`, `docs/platform-overview.md`

## Brand
- Personality: operational, trustworthy, calm, data-dense only when requested
- Trust signals: explicit source health, persisted job state, honest partial/error states
- Avoid: decorative dashboards, hidden side effects, long walls of controls, equal emphasis for primary and expert actions

## Product goals
- Goals: help an operator prepare reliable data with the fewest visible decisions; make the next action obvious
- Non-goals: hiding advanced scraper capabilities or replacing observability tools
- Success signals: primary scrape setup fits in a short guided flow; optional controls are progressively disclosed; desktop and mobile remain scannable

## Personas and jobs
- Primary personas: betting analyst/operator and technical administrator
- User jobs: choose competitions, select historical/upcoming coverage, review scope, queue a traceable scrape
- Key contexts of use: repeated desktop operations, occasional mobile monitoring, slow or degraded upstream sources

## Information architecture
- Primary navigation: Home → Prepare → Analyze → Opportunities → Tickets → Monitoring
- Core routes/screens: `/prepare` owns collection setup and recent scrape visibility
- Content hierarchy: guided primary setup first; recent jobs second; automation, pipelines, logs and engine controls last

## Design principles
- Progressive disclosure: show the common path first and keep expert controls collapsed
- One decision per group: presets before manual inputs, summaries before execution
- Honest status: never imply success until the backend run is persisted and classified
- Tradeoffs: prefer a shorter, clearer first view over showing the entire catalog at once

## Visual language
- Color: existing semantic football green/blue/gold tokens
- Typography: existing sport headings with compact operational body copy
- Spacing/layout rhythm: 8px-based rhythm, aligned card grids, max-width workbench container
- Shape/radius/elevation: existing card and button primitives; restrained borders and elevation
- Motion: short Svelte transitions for disclosed sections; respect reduced motion
- Imagery/iconography: `lucide-svelte` only; icons support labels rather than replace them

## Components
- Existing components to reuse: `Card`, `Button`, `Input`, `Select`, `Badge`, `Skeleton`, `Separator`
- New/changed components: compact step status, scope presets, progressive country/league catalog, run summary
- Variants and states: selected, ready, incomplete, disabled, loading, empty, warning, success
- Token/component ownership: frontend shared primitives own tokens; route owns workflow composition

## Accessibility
- Target standard: WCAG 2.1 AA
- Keyboard/focus behavior: native buttons, inputs and `details/summary`; visible focus rings; no hover-only actions
- Contrast/readability: retain semantic token contrast and readable 12–14px supporting text
- Screen-reader semantics: headings remain hierarchical; status summaries use text and `aria-live` where state changes
- Reduced motion and sensory considerations: brief nonessential transitions only

## Responsive behavior
- Supported breakpoints/devices: mobile through wide desktop using existing Tailwind breakpoints
- Layout adaptations: stacked cards and full-width actions on mobile; two-column aligned coverage on desktop
- Touch/hover differences: generous touch targets; no interaction depends on hover

## Interaction states
- Loading: skeletons only where catalog/jobs are pending
- Empty: explain the single next action, such as choosing a country
- Error: preserve input and show backend detail near the launch action
- Success: confirm queued job count and expose recent run state
- Disabled: state why the primary action is unavailable
- Offline/slow network: catalog/jobs remain independently recoverable and refreshable

## Content voice
- Tone: concise, direct, operational
- Terminology: use Prepare, competition, coverage, scrape and job consistently
- Microcopy rules: lead with the action; move implementation details into advanced help text

## Implementation constraints
- Framework/styling system: Svelte 5, SvelteKit, Tailwind 4, existing UI primitives
- Design-token constraints: do not introduce parallel color or spacing systems
- Performance constraints: do not render the full league catalog before the user narrows scope
- Compatibility constraints: preserve existing backend payloads, IDs used by tests, and automation semantics
- Test/screenshot expectations: `pnpm check`, unit tests, build, targeted Playwright desktop/mobile screenshots

## Open questions
- [ ] Should user-specific scope presets be persisted server-side after the compact local presets prove useful?
