# Sports Betting Dashboard UX Research Report

## 1. Desktop Layout Patterns

### A. Three-Column (bet365 / Betfair Exchange)
```
+-------------+-------------------+-----------+
|  SPORTS     |   MATCH LIST      |  BETSLIP  |
|  NAV        |   / MARKETS       |  (Fixed)  |
|  (Sidebar)  |   (Scrollable)    |           |
+-------------+-------------------+-----------+
```
**When to use:** Power users, multi-market bet builders, high data density.
**Accessibility:** Sidebar must be collapsible (`aria-expanded`), skip-to-content link.
**Implementation (SvelteKit/Tailwind):**
- `grid grid-cols-[220px_1fr_320px]` on `lg:`.
- Use `<aside>` for nav and betslip; `<main>` for content.
- Betslip: `position: sticky; top: 0; height: 100vh; overflow-y: auto`.

### B. Top-Nav + Single Panel (FanDuel / DraftKings)
```
+-------------------------------------------+
|  LOGO  |  SPORT |  LEAGUE |  SEARCH | USER |
+-------------------------------------------+
|         MATCH LIST / MARKETS              |
|              (Full Width)                 |
+-------------------------------------------+
```
**When to use:** Casual users, mobile-first parity, promotional highlights.
**Accessibility:** Horizontal submenus need arrow-key navigation; avoid horizontal-only scroll without visible affordance.
**Implementation:**
- `flex flex-col` on root.
- Top nav: `sticky top-0 z-50`.
- Betslip as a slide-over `<dialog>` or bottom sheet.

---

## 2. Match Listings: Card Grid vs List vs Table

### Card Grid (FanDuel Default)
```
+----------+  +----------+  +----------+
| Team A   |  | Team C   |  | Team E   |
|  -110    |  |  +205    |  |  +140    |
| Team B   |  | Team D   |  | Team F   |
|  -110    |  |  -245    |  |  -165    |
+----------+  +----------+  +----------+
```
**When to use:** Pre-match overview, casual browsing, high glanceability.
**Accessibility:** Cards must be keyboard-focusable (`tabindex="0"`) and triggerable with Enter/Space. Use `<article>`.
**Implementation:**
- `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4`.
- Odds buttons: `min-h-[48px]` touch target.

### List View (bet365 In-Play)
```
+-------------------------------------------+
| [LIVE] Team A  1-0  Team B     [1.90]    |
| 1st Half  32'    [Over 2.5] [1.85] [2.10]|
+-------------------------------------------+
```
**When to use:** Dense slates, in-play where speed > aesthetics.
**Accessibility:** Row actions exposed; avoid hover-only reveals.
**Implementation:**
- `flex justify-between items-center py-3 border-b`.

### Table View (Betfair Exchange / Pinnacle)
```
+-------------------------------------------+
| Selection    | Back | Lay | Vol | Trend   |
+-------------------------------------------+
| Team A       | 2.50 | 2.52| 45k | ▲ 0.10  |
+-------------------------------------------+
```
**When to use:** Exchange/serious bettors, volume and price depth required.
**Accessibility:** `<table>` with `<th scope="col">`. Sortable headers need `aria-sort`.
**Implementation:**
- `w-full text-sm`.
- Alternating row backgrounds: `even:bg-slate-50`.

---

## 3. Quick-Action Patterns

### One-Click Bet
- **Pattern:** Tapping an odd instantly adds it to a *sticky* betslip; no modal.
- **When to use:** Live betting, single-selection sports (MLB run line).
- **Accessibility:** Provide `aria-live="polite"` region for betslip updates; toast confirmation.
- **Implementation:**
  - Global betslip store (Svelte `writable`/`runes`).
  - Sticky footer: `fixed bottom-0 left-0 right-0 z-50` on mobile.

### Quick-Stake / Preset Buttons
```
[  £5  ] [  £10  ] [  £25  ] [  £50  ] [ Custom ]
```
- **When to use:** Repeat betting, reducing friction.
- **Accessibility:** `<fieldset>` with `<legend>Stake</legend>`; radio inputs visually hidden.
- **Implementation:**
  - `flex gap-2`.
  - Active state: `ring-2 ring-offset-2 ring-blue-500`.

### Bet Builder (Coral/DK SGP)
- **Pattern:** Accordion legs inside event page; cross-event selection via unified flow.
- **When to use:** Same-Game Parlays, cross-match accumulators.
- **Accessibility:** Each leg is a removable `<li>` in a list; focus returns to trigger on removal.
- **Implementation:**
  - `details/summary` for leg categories.
  - Sticky summary footer: `sticky bottom-0`.

---

## 4. In-Play / Live Interface

### Pattern: "TV Mode" Split (FanDuel / bet365)
```
+-------------------+-------------------+
|  VISUALIZER /     |  MARKETS PANEL    |
|  LIVE STREAM      |  (Grouped by      |
|                   |   market type)    |
+-------------------+-------------------+
|  STATS BAR (Possession, Shots, etc)   |
+---------------------------------------+
```
**When to use:** High-engagement events where users watch and bet simultaneously.
**Accessibility:** Ensure live region for score updates; stream must have captions toggle.
**Implementation:**
- `grid grid-cols-1 lg:grid-cols-2 gap-4`.
- Stats bar: `flex overflow-x-auto gap-6 py-2`.
- Markets: auto-scroll to top on score change? No — avoid scroll hijacking.

### Mobile Live Pattern
- Scoreboard sticky at top.
- Markets below in swipeable tabs (`overflow-x-auto` scroll-snap).
- Betslip is a bottom sheet (`<dialog>` or fixed div) triggered by selection.
- **Implementation:**
  - Scoreboard: `sticky top-0 bg-black text-white z-40`.
  - Tabs: `snap-x snap-mandatory`.

---

## 5. Mobile-Responsive Patterns

### Bottom Navigation
```
+----------------------------------+
|           CONTENT                 |
|                                 |
+----------------------------------+
| [Sports] [Live] [Promos] [Bets]  |
+----------------------------------+
```
- **When to use:** Primary navigation on mobile; betslip badge essential.
- **Accessibility:** `aria-current="page"` on active tab; label + icon.
- **Implementation:** `fixed bottom-0 flex justify-around h-16 bg-white border-t`.

### Swipeable Cards (bet365 iOS "Deck of Cards")
- **Pattern:** Vertical swipe scrolls current view; horizontal swipe changes sport/league.
- **When to use:** Native app feel, reducing thumb travel.
- **Accessibility:** Provide buttons as alternative to swipe gestures.
- **Implementation:** Use Svelte actions with `touchstart/touchend` or library like `swiper`; ensure `aria-roledescription="carousel"`.

### Sticky Bet Slip
- Always visible once a selection is made.
- Collapses to a "n selections" bar; expands on tap.
- **Implementation:**
  - `fixed bottom-16 left-2 right-2` (above bottom nav).
  - Transition height with Svelte `transition:slide`.

---

## 6. Data Density vs Readability

| Platform | Density | Font Size | Notes |
|---|---|---|---|
| bet365 | High | Small (14px) | Experienced users; more markets per viewport. |
| FanDuel | Medium | Medium (16px) | Balanced; curated defaults. |
| DraftKings | Medium-High | Medium | Systematic drill-down. |
| Pinnacle | Very High | Small | Sharp bettors; price/point paramount. |

**Principles:**
1. **Progressive Disclosure:** Show primary markets (1X2, Over/Under); hide props behind "More".
2. **User Toggle:** Allow "Compact / Comfortable" view switch in settings.
3. **Whitespace:** Use padding, not borders, to separate cards in low-density mode.

**Accessibility:** Minimum text size must respect browser settings (use `rem`); contrast ratio 4.5:1 for odds text.

---

## 7. Implementation Checklist for SvelteKit + Tailwind

- [ ] Use CSS Grid for desktop three-column; Flexbox for mobile stacks.
- [ ] All interactive odds are `<button>` with `aria-pressed` when selected.
- [ ] Betslip uses Svelte stores; updates announced via `aria-live` region.
- [ ] Live score updates use `<output>` or `aria-live="assertive"` sparingly.
- [ ] Touch targets min `44x44px` (Tailwind `min-h-11 min-w-11`).
- [ ] Bottom sheet betslip uses `<dialog>` element for focus trapping.
- [ ] Respect `prefers-reduced-motion` for live odds flashing/swiping.
- [ ] Provide "Skip to betslip" and "Skip to markets" links.

*Report compiled from industry analysis of bet365, FanDuel, DraftKings, Pinnacle, and Betfair Exchange patterns.*
