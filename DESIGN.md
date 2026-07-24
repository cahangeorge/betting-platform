# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-07-13
- Primary product surfaces: the current SvelteKit workbench in `frontend/`, especially the operator flow `Prepare -> Analyze -> Tickets -> Monitoring`
- Current implementation evidence reviewed:
  - `AGENTS.md`
  - `frontend/src/app.css`
  - `frontend/src/lib/navigation.ts`
  - `frontend/src/routes/+layout.svelte`
  - `frontend/src/lib/components/WorkflowHeader.svelte`
  - `frontend/src/lib/components/BetslipReviewCallout.svelte`
  - `frontend/src/lib/components/BetSlipDrawer.svelte`
  - `frontend/src/lib/components/BetslipFAB.svelte`
  - `frontend/src/lib/components/BottomNav.svelte`
  - `frontend/src/lib/components/Sidebar.svelte`
  - `frontend/src/lib/components/jobs/ScheduledJobRunTable.svelte`
  - `frontend/src/routes/prepare/+page.svelte`
  - `frontend/src/routes/analyze/+page.svelte`
  - `frontend/src/routes/analyze/strategy.helpers.ts`
  - `frontend/src/routes/tickets/+page.svelte`
  - `frontend/src/lib/components/TicketsPanel.svelte`
- Product and verification evidence reviewed:
  - `docs/plans/2026-06-23-bet-platform-product-spec.md`
  - `docs/plans/2026-06-23-bet-platform-implementation-roadmap.md`
  - `docs/plans/2026-06-23-bet-platform-test-plan.md`
  - `docs/platform-overview.md`
  - `docs/platform-migration/frontend-futurist-ui-playbook.md`
  - `sports-betting-ux-report.md`
- Visual evidence reviewed: repository screenshots were inspected, including the historical Python flow captures and the root data-page captures. They are not a current visual baseline; several are outdated or show the login screen.
- Evidence limitation: live browser inspection was attempted during this refresh, but the installed Playwright/Chrome MCP runtimes could not start a browser because Chrome/X-server support was unavailable. Current route source and design tokens are therefore the authoritative evidence for this contract.
- Governance: this file supersedes the older futurist playbook where it conflicts with the current rectangular, dark-default decision-workbench system. It does not replace product/API contracts.

## Brand
- Personality: operational, trustworthy, calm, precise, and configurable without feeling technical by default
- Trust signals:
  - every analysis and ticket batch shows its source dataset, prediction run, creation time, and persisted status;
  - partial results remain visible and are not presented as full success;
  - reused/deduplicated runs are labeled explicitly;
  - disabled strategies and actions always explain why;
  - paper execution is visibly distinguished from external/live placement.
- Avoid:
  - decorative dashboard chrome that competes with the primary decision;
  - hidden side effects or automatic placement;
  - raw IDs or JSON as the normal path for non-experts;
  - one long wall containing configuration, automation, results, and history at equal emphasis;
  - green/red status cues without an icon or text label;
  - celebratory or urgency copy that encourages chasing losses.

## Product goals
- Goals:
  - continue directly from a completed Argentina all-leagues scrape into analysis;
  - run the prepared scope through every runnable strategy present in the strategy catalog;
  - expose progress, result counts, warnings, and failures per strategy;
  - make comparison and review easier than configuration;
  - preserve prediction lineage when moving into ticket generation;
  - let an operator generate, inspect, adjust, place, and later settle ticket batches without losing context;
  - make the full flow usable on desktop and mobile.
- Non-goals:
  - changing prediction mathematics or ticket-engine rules in the UI layer;
  - hiding inactive or incompatible strategies to make completion appear better;
  - automatically placing generated tickets without a review/confirmation step;
  - duplicating Monitoring as a second operations console inside Analyze or Tickets;
  - replacing the existing navigation shell or creating a parallel design system.
- Success signals:
  - the latest valid prepared dataset can be analyzed with all runnable strategies using one primary action;
  - every selected strategy receives a terminal status or an honest running status;
  - failed strategies can be retried without rerunning successful strategies;
  - a reviewed analysis can open Tickets with the exact prediction run(s) preselected;
  - a generated batch is immediately reviewable and never confused with a placed ticket;
  - no supported viewport has body-level horizontal scrolling;
  - configuration survives recoverable request errors and refreshes where practical.

## Personas and jobs
- Primary personas:
  - operator/non-expert: wants a guided, safe default from prepared data to useful tickets;
  - betting analyst/power user: compares strategies, markets, edge, reliability, and lineage;
  - technical administrator: inspects failures, schedules recurring work, and confirms backend truthfulness.
- User jobs:
  - confirm that Argentina leagues and their match coverage are ready;
  - run all compatible strategies without selecting them one by one;
  - understand which strategies succeeded, failed, were skipped, or reused a prior run;
  - filter and compare candidates, then send selected candidates or complete runs into ticket generation;
  - generate tickets using understandable risk, market, odds, count, and bankroll controls;
  - review and swap legs safely before placement;
  - monitor active tickets and settle only after source results are ready.
- Key contexts of use:
  - repeated desktop configuration and comparison sessions;
  - tablet review while monitoring jobs;
  - mobile status checks, approvals, and small configuration adjustments;
  - slow or degraded scraping/prediction services where partial state must remain useful.

## Information architecture
- Primary navigation: `Home -> Prepare -> Analyze -> Opportunities -> Tickets -> Monitoring`; route paths and global navigation labels remain stable.
- Primary task path: `Prepare data -> Analyze all runnable strategies -> Review candidates -> Generate tickets -> Review/adjust batch -> Place or keep as generated -> Monitor/settle`.
- `Opportunities` remains an optional discovery route, not a required detour between Analyze and Tickets.
- Each workflow route uses `WorkflowHeader` plus a compact progress indicator. The indicator is orientation, not navigation lock-in: completed stages are links, current stage is marked with text and `aria-current="step"`.

### Analyze route hierarchy
1. **Header and data readiness**
   - Page name is `Analiză`, while the route stays `/analyze`.
   - Show latest prepared dataset/job, country, included leagues, match count, date range, freshness, and status.
   - When entered from Prepare, use the explicit scrape/dataset/run query parameter or server context; do not silently replace it with “latest”.
   - The common path defaults to the latest valid Argentina all-leagues prepared scope.
   - Missing/stale/partial data produces a clear prerequisite card with `Revino la Prepare` and, where safe, `Continuă cu datele disponibile`.
2. **Analysis configuration**
   - Summary-first form: scope, strategies, markets, future period, deduplication.
   - Scope is prefilled from Prepare and collapsed to a readable summary. Editing country/league/date is an explicit secondary action.
   - Strategy selector shows every catalog strategy. `Selectează toate strategiile rulabile` is the default state.
   - Inactive, incompatible, or invalid strategies remain visible but disabled with a reason and a link to strategy configuration.
   - Market choices use readable labels; backend keys are supporting metadata, not the primary label.
   - Autopredict scheduling and raw/advanced model configuration live in an `Automatizare și opțiuni avansate` disclosure below the manual run controls.
3. **Preflight and execution**
   - A sticky/adjacent summary states dataset, league count, match count, runnable strategy count, market count, dedupe behavior, and expected action.
   - The single primary CTA is `Rulează analiza pentru N strategii`.
   - Execution changes into a per-strategy progress list with `queued`, `running`, `completed`, `partial`, `failed`, `skipped`, or `reused` states.
   - Global progress is derived from strategy terminal states; it never replaces them.
   - Allow `Retry failed` only after at least one strategy fails and keep completed results intact.
4. **Review results**
   - Start with a compact outcome summary: completed strategies, failed strategies, matches analyzed, candidates, ticket-eligible candidates, warnings.
   - Filters: strategy, league, market, reliability, eligibility, minimum edge, and search by team.
   - Desktop uses a sortable table with a sticky header; mobile uses result cards with the same information hierarchy.
   - Candidate detail shows match/kickoff, strategy/model, market/selection, probability, best stored odds, implied probability, edge, reliability, eligibility, quality reasons, and source run.
   - Selection supports individual and bulk add-to-slip actions, plus `Continuă la bilete` with the reviewed run IDs and selected candidate IDs.
   - Recent runs and automation history are secondary disclosures after current results, not competing primary sections.

### Tickets route hierarchy
1. **Header and readiness**
   - Page name is `Bilete`, while the route stays `/tickets`.
   - If opened from Analyze, show the source prediction run(s), strategy coverage, candidate count, and a return link to the filtered analysis.
   - If no usable prediction source exists, show the prerequisite and route back to Analyze; do not silently generate from an unrelated “latest” run.
2. **Metrics**
   - Compact summary: active, won, lost, void, settled, win rate, stake, return, and P/L when provided by stored backend state.
   - Metrics never push the primary generation action below a full screen on mobile.
3. **Primary modes**
   - `Generează`: configuration and preflight for a new automatic batch; this is the default when arriving from Analyze.
   - `Revizuiește lotul`: generated tickets awaiting inspection/adjustment; activate automatically after generation.
   - `Active`: placed/open tickets, progress, paper execution, and contextual result refresh/verification.
   - `Istoric`: prior batches and settled tickets with filters and settlement progress.
   - Manual ticket building remains available as a secondary mode/disclosure within `Generează`, not mixed into the automatic form.
4. **Generate**
   - Required controls: source prediction run, bankroll/account, number of tickets, safety/difficulty, markets, minimum odds, maximum odds.
   - Show eligible candidate count and any excluded/low-quality count before generation.
   - Validate ranges inline, including min odds <= max odds, valid bankroll, at least one market, and a usable source run.
   - Automation scheduling is collapsed under `Automatizare`; it reuses the visible configuration and previews the schedule in plain language.
   - The primary CTA is explicit: `Generează N bilete din run #X`.
5. **Review batch**
   - Distinguish `generated`, `placed/open`, and `settled` with text and status badges.
   - Each ticket shows reference, leg count, probability/chance, total odds, stake, potential return, source run, and quality warnings.
   - Legs show match, kickoff, league, market, selection, model probability, stored odds, and eligibility/reliability.
   - Swap flow uses direct source and target selection, validates conflicts, previews before/after probability and odds, then requires confirmation.
   - Placement has a sticky review summary and never happens as an implicit result of generation.
   - A generated-only draft may be abandoned through `Renunță la lotul draft`, followed by an explicit confirmation. This action removes only the unactivated draft and never implies a refund or stake debit.
6. **Active and history**
   - Active tickets expose settled legs/total, current match state, final score when known, and per-leg result.
   - Result refresh and settlement controls live inside Active/History context, not above every ticket task.
   - History is batch-first: created time, source prediction run, ticket count, finalized count, P/L, then expandable ticket detail.
   - Monitoring links provide exhaustive scheduled-job logs; Tickets shows only the status/actions needed to complete the ticket task.

## Design principles
- **Lineage before convenience:** dataset, prediction run, strategy result, ticket batch, and placed ticket remain visibly connected.
- **All runnable by default:** fulfill “all strategies” with a deterministic select-all-runnable state; never pretend disabled strategies ran.
- **Summary before controls:** show the prepared scope and current selection in human terms before exposing the full catalog.
- **One primary action per stage:** secondary scheduling, strategy creation, manual placement, export, and history do not compete with run/generate/review actions.
- **Progressive disclosure:** common choices stay visible; automation, advanced filters, and technical metadata open on demand and remember their state for the session.
- **Partial success is useful:** retain successful strategy results, identify failed slices, and offer targeted retry.
- **Review before risk:** generated tickets remain drafts until the operator reviews and deliberately places them.
- **Mobile is a decision surface, not a compressed desktop:** replace wide tables and multi-column forms with cards, sheets, summaries, and sticky actions.
- Tradeoffs:
  - prefer one additional review step over accidental placement or ambiguous lineage;
  - prefer visible disabled strategies over a cleaner but misleading list;
  - prefer paginated/virtualized results over rendering every candidate at once;
  - prefer plain operational language over model or scheduler jargon.

## Visual language
- Color:
  - retain the current dark-default semantic tokens in `frontend/src/app.css`;
  - football green = primary/ready/completed, blue = information/link, gold = warning/running/reused, destructive red = failed/lost;
  - color is always paired with text, icon, or shape;
  - light mode must preserve the same semantic hierarchy.
- Typography:
  - existing sport/condensed face for short page and section headings;
  - existing sans face for controls and explanatory text;
  - existing mono face for odds, probability, edge, IDs, counts, dates, and run/batch references;
  - body text is 14px minimum; essential mobile controls and results should not rely on 10–11px text.
- Spacing/layout rhythm:
  - 4px base with an 8px primary rhythm;
  - route content uses the existing `workbench-page`/`max-w-7xl` boundary rather than unconstrained width;
  - 24px section gaps desktop, 16px mobile; dense rows use 8–12px internal spacing.
- Shape/radius/elevation:
  - preserve the rectangular zero-radius system;
  - one border/elevation level for ordinary cards, stronger border/accent for current stage or warning;
  - avoid nested cards deeper than two visual levels.
- Motion:
  - 150–220ms fade/slide for disclosures, sheets, and state transitions;
  - progress updates do not reorder rows or move focus;
  - no infinite decorative animation; existing reduced-motion fallback applies.
- Imagery/iconography:
  - `lucide-svelte` only;
  - icons reinforce a visible label and do not become unlabeled primary actions;
  - no decorative sports imagery in mission-critical forms.

## Components
- Existing components to reuse:
  - `WorkflowHeader`, `BetslipReviewCallout`, `BetSlipDrawer`, `BetslipFAB`;
  - `Card`, `Button`, `Input`, `Select`, `Badge`, `Tabs`, `Dialog`, `Sheet`, `Skeleton`, `Separator`, `Table`, `Tooltip`;
  - `ScheduledJobRunTable` for secondary operational history;
  - existing sidebar, bottom navigation, command palette, focus, theme, and connectivity behaviors.
- New/changed route-level components:
  - `WorkflowProgress`: linked stage orientation for Prepare/Analyze/Tickets/Monitoring;
  - `DataReadinessSummary`: prepared dataset lineage, coverage, freshness, and prerequisite actions;
  - `AnalysisConfigurator`: summary-first scope, markets, strategies, and dedupe controls;
  - `StrategySelectionList`: select-all-runnable, search/filter, compatibility and disabled reasons;
  - `StrategyRunProgress`: stable per-strategy execution states and targeted retry;
  - `AnalysisResultsExplorer`: facets, desktop table, mobile cards, selection, and ticket handoff;
  - `TicketGenerationConfigurator`: source run, bankroll, risk, markets, odds, count, and preflight;
  - `TicketBatchReview`: generated batch summary, ticket cards, warnings, and placement action;
  - `TicketLegSwap`: direct source/target selection plus before/after confirmation;
  - `TicketStatusCard`: shared generated/active/history ticket and leg hierarchy;
  - `StickyWorkflowAction`: responsive summary plus primary CTA that respects shell safe areas.
- Variants and states:
  - selected/unselected, compatible/incompatible, ready/stale/missing;
  - queued/running/completed/partial/failed/skipped/reused/cancelled;
  - generated/placed/open/won/lost/void;
  - loading/empty/error/success/disabled/offline.
- Token/component ownership:
  - shared primitives and `app.css` own semantic tokens and control styling;
  - route feature components own workflow composition and domain-specific display;
  - do not introduce a second primitive library or parallel color/spacing tokens.

## Accessibility
- Target standard: WCAG 2.2 AA.
- Keyboard/focus behavior:
  - entire flow is operable with keyboard only;
  - bulk strategy selection is a real button/checkbox control with deterministic focus;
  - tabs follow expected arrow-key/activation behavior;
  - dialogs/sheets trap focus, close with Escape, restore focus to the trigger, and provide labelled titles;
  - sticky action bars do not obscure focused controls;
  - focus remains stable when strategy progress updates.
- Contrast/readability:
  - meet at least 4.5:1 for normal text and 3:1 for large text/UI boundaries;
  - never rely on low-opacity text for essential status or explanation;
  - pair outcome colors with status words and icons;
  - use tabular/monospaced numerals where changing values would shift layout.
- Screen-reader semantics:
  - one `h1`, ordered section headings, explicit fieldsets/legends for grouped choices;
  - selection counts and filters have accessible names;
  - progress uses a labelled list and current status text, not color alone;
  - debounced `aria-live="polite"` announcements report meaningful progress totals; failures use an appropriate alert without repeating on every poll;
  - result tables use captions and column headers; mobile cards preserve equivalent labelled data;
  - icon-only fallback actions require an accessible name.
- Reduced motion and sensory considerations:
  - honor the global `prefers-reduced-motion` behavior;
  - no flashing/pulsing state is required to understand progress;
  - success/failure is communicated with text and shape as well as color.
- Touch:
  - interactive targets are at least 44x44 CSS pixels on touch layouts;
  - no essential interaction depends on hover, drag, or long press;
  - swap and reorder actions always have explicit select/confirm alternatives.

## Responsive behavior
- Supported breakpoints/devices:
  - compact mobile: 320–479px;
  - mobile/large phone: 480–767px;
  - tablet: 768–1023px;
  - desktop shell: 1024–1279px;
  - wide desktop: 1280px and above.
- Layout adaptations:
  - **wide desktop:** bounded `max-w-7xl` workbench; 8/4 or 9/3 configuration + sticky summary rail; results can use full-width sortable tables;
  - **desktop/tablet:** configuration groups become two columns only when labels and values fit; sticky summary becomes a full-width top/bottom bar; no third persistent rail competes with the app sidebar or bet slip;
  - **mobile:** single column, compact linked workflow header, result/ticket cards instead of wide tables, secondary filters in a Sheet, disclosures closed by default;
  - long league/strategy/result lists use search, pagination, or virtualization instead of unbounded page height;
  - horizontal chip rows may scroll internally with visible affordance, but the page body must not scroll horizontally.
- Touch/hover differences:
  - desktop hover can reveal supplementary tooltips, never required information;
  - mobile shows the same information through labelled disclosure/tap;
  - primary mobile CTA is sticky above the existing 4rem BottomNav and `env(safe-area-inset-bottom)`;
  - sticky CTA, BottomNav, BetslipFAB, and open bottom-sheet bet slip must never overlap; bet slip state takes priority.
- Data density:
  - desktop table columns: match, strategy, market/selection, probability, odds, edge, reliability, status/action;
  - lower-priority lineage and quality details move into expandable detail;
  - mobile card first line answers “what match and pick?”, second line “how strong?”, third line “which strategy/run?”, followed by the action.

## Interaction states
- Loading:
  - load readiness, strategies, catalog, metrics, runs, and results independently;
  - use skeletons matching final height for initial content and compact inline progress for refreshes;
  - keep already loaded data visible during background polling.
- Empty:
  - no prepared data: explain the prerequisite and link to Prepare;
  - no runnable strategies: link to Strategy configuration and list disabled reasons;
  - no candidates: distinguish “analysis finished with no qualifying candidates” from failure;
  - no bankroll: link directly to Account setup;
  - no ticket batches/active tickets: present the relevant generate/analyze action.
- Error:
  - preserve configuration and successful slices;
  - show the failing resource/strategy and actionable recovery;
  - global errors never erase partial per-strategy results;
  - degraded backend messages say which data is unavailable.
- Partial:
  - show completed/failed/total counts and warnings;
  - permit review of successful results plus targeted retry;
  - downstream Tickets includes only eligible successful run data and states exclusions.
- Success:
  - analysis success states strategy/run IDs and candidate counts;
  - generation success states batch ID and generated count, then opens Review;
  - placement success states ticket references and whether placement is local paper or external/live.
- Disabled:
  - every disabled primary action exposes a nearby reason;
  - incompatibility, missing source, invalid range, empty market selection, and missing bankroll are distinct reasons.
- Offline/slow network:
  - retain server-loaded data and current inputs;
  - pause aggressive polling and expose manual refresh;
  - do not claim queued work when the create request was not confirmed;
  - connectivity banner remains global, while local action errors remain near the action.
- Stale/conflict:
  - stale prepared data and odds are labelled with timestamps;
  - changed odds or invalid/duplicate legs require explicit review; never silently mutate a reviewed ticket.

## Content voice
- Tone: concise, direct, operational, non-promotional.
- Terminology:
  - user-facing primary workflow copy is Romanian;
  - route paths and code identifiers remain English;
  - use `set de date pregătit`, `analiză`, `strategie`, `piață`, `run de predicție`, `candidat`, `lot de bilete`, `bilet generat`, `bilet plasat`, and `verificare rezultate` consistently;
  - expose technical backend keys and IDs as secondary metadata where they help support/debugging.
- Microcopy rules:
  - buttons state the effect and scope: `Rulează analiza pentru 12 strategii`, not `Run`;
  - empty states explain one next action;
  - dedupe copy says `Refolosește run-ul existent pentru aceleași intrări`, not merely `avoid reprediction`;
  - generated is never called placed;
  - partial completion includes counts;
  - destructive or risk-bearing actions use explicit confirmation copy;
  - tooltips explain model terms without making performance claims.

## Implementation constraints
- Framework/styling system: Svelte 5, SvelteKit 2, Tailwind 4, current repo UI primitives, `lucide-svelte`.
- Design-token constraints:
  - extend current semantic tokens only when a real missing state exists;
  - preserve zero-radius rectangular surfaces and dark-default theme;
  - do not add a second component framework or hardcoded per-route palettes.
- Data/lineage constraints:
  - UI state must be derived from persisted backend jobs/runs/batches whenever available;
  - Analyze -> Tickets handoff passes explicit IDs, not an ambiguous latest-run assumption;
  - “all strategies” means the strategy catalog snapshot plus compatibility state at run creation;
  - schedules preview and persist the same visible configuration used by the immediate action;
  - existing same-origin `/api` cookie behavior remains unchanged.
- Performance constraints:
  - do not render all countries, leagues, strategies, predictions, or tickets without narrowing, pagination, or virtualization;
  - polling updates existing rows in place and stops at terminal states;
  - lazy-load secondary history, automation, and detail panels;
  - avoid layout shifts in progress, odds, edge, and metrics.
- Compatibility constraints:
  - preserve route paths, backend payload contracts, run/batch lineage, test IDs where they encode product behavior, app shell, mobile BottomNav, and bet-slip behavior;
  - no UI-only synthetic success;
  - no raw JSON editor in the standard workflow;
  - strategy management remains available through the dedicated strategy/configuration route.
- Test/screenshot expectations:
  - use official Svelte MCP guidance and the Svelte autofixer for changed `.svelte`/`.svelte.ts` files;
  - run targeted unit tests, `pnpm check`, `pnpm test:unit`, `pnpm build`, then hybrid Playwright;
  - capture `/analyze` and `/tickets` at 390x844, 768x1024, and 1440x900;
  - cover full, empty, loading, partial failure, hard error, reused run, no bankroll, generated batch, and active ticket states;
  - verify keyboard-only completion of immediate analysis and ticket-generation preflight;
  - verify no body-level horizontal overflow and no sticky-action overlap with BottomNav/BetslipFAB.

## Workflow acceptance criteria

### Analyze
- [ ] Opening Analyze from a completed Argentina scrape identifies that exact prepared source and shows all included available Argentine leagues.
- [ ] Every runnable strategy in the returned strategy catalog is selected by default; inactive/incompatible strategies are visible, disabled, and explained.
- [ ] The primary action states the number of strategies and cannot run without a valid prepared source and at least one market.
- [ ] During execution, every selected strategy has its own stable status row and result/warning/error summary.
- [ ] Partial completion retains successful results and offers retry for failed strategies only.
- [ ] Deduplicated strategies are marked `reused` with the persisted run ID.
- [ ] Review supports strategy, league, market, reliability, eligibility, edge, and team filters.
- [ ] Desktop results are sortable without body overflow; mobile results expose equivalent content as cards.
- [ ] Continuing to Tickets carries explicit prediction run/candidate context and can return to the same analysis review.
- [ ] Automation and recent history are accessible but do not compete with the immediate run/review task.

### Tickets
- [ ] Arrival from Analyze preselects the explicit source run(s) and shows eligible/excluded candidate counts.
- [ ] Missing source prediction data or bankroll blocks generation with a clear direct recovery link.
- [ ] Ticket count, safety, markets, and odds range are validated inline before generation.
- [ ] Generation creates a persisted batch, labels it generated rather than placed, and opens batch review immediately.
- [ ] Each generated ticket and leg exposes probability, odds, source lineage, status, and quality warnings.
- [ ] Leg swap has source/target selection, conflict validation, before/after preview, and explicit confirmation.
- [ ] Placement requires deliberate review/confirmation and clearly distinguishes paper from external/live execution.
- [ ] Active-ticket verification controls appear in Active context; historical batch inspection appears in History context.
- [ ] Mobile generation/review completes without horizontal page scroll or collision with BottomNav/bet slip.

### Cross-cutting
- [ ] All primary states are understandable without color alone.
- [ ] Focus, headings, labels, live-region announcements, dialogs, tabs, and tables/cards meet the accessibility contract above.
- [ ] Background polling never erases loaded content, reorders focused rows, or announces noisy repeated updates.
- [ ] A recoverable API failure preserves user inputs and successful partial work.
- [ ] Monitoring remains the exhaustive operations/log destination; workflow pages link to it for deeper diagnosis.

## Open questions
- [ ] Backend/BE owner: which strategy states are authoritative for `runnable`, `inactive`, and `incompatible`, and can the run endpoint return a catalog snapshot plus per-strategy status in one orchestration contract? Impact: exact “all strategies” selection and truthful progress.
- [ ] Backend/BE owner: what explicit dataset/scrape-run identifier should Analyze accept from Prepare for the Argentina all-leagues handoff? Impact: lineage and avoidance of ambiguous latest-data selection.
- [ ] Backend/BE owner: can Tickets accept multiple prediction run IDs, or must Analyze/Tickets establish one orchestration/run-group ID? Impact: all-strategy result aggregation and ticket generation.
- [ ] Product/BE owner: are inactive strategies included by user intent, or only visible with a disabled reason while all active compatible strategies run? Default assumption: run all active compatible strategies.
- [ ] Product owner: should candidate bulk selection persist across pagination/filter changes? Default assumption: yes, for the current analysis review session.
- [ ] Product/DevOps owner: which ticket execution modes are enabled in each environment, and what environment-level banner is required beyond the current paper-execution copy? Impact: placement trust and safety.
- [ ] Product owner: should Romanian become the consistent language across the entire shell in this work, or only in the redesigned workflow content? Default assumption: workflow content first; preserve route paths and global labels until a separate localization pass.
