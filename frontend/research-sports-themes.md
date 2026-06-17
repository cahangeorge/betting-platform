# Sports Betting Intelligence Platform — UI Theme Research

> Five design directions for `betfront`. Each includes a concrete palette, typography, and motifs ready for Tailwind/CSS implementation.

---

## 1. Stadium Broadcast (Floodlight)

**Vibe:** Saturday night under the lights. Pitch greens, floodlight whites, crowd murmur.

| Token | Hex | Usage |
|---|---|---|
| Background | `#060B14` | Deep stadium night |
| Surface | `#0F172A` | Card/panel base |
| Accent | `#4ADE80` | Pitch green — live odds, active bets |
| Success | `#22C55E` | Win/positive EV |
| Danger | `#EF4444` | Loss/negative EV |
| Text Primary | `#F8FAFC` | Floodlight white |
| Text Secondary | `#94A3B8` | Haze gray |

**Typography**
- Display: `Inter` or `Geist` — 800 weight, tight tracking (-0.02em), sizes 48–96px for hero stats
- Body: `Inter` — 400/500, 14–16px
- Data/mono: `JetBrains Mono` — 500, 12–14px for odds, probabilities, timestamps

**Visual Motifs**
- Subtle horizontal pitch-line dividers (1px `#1E293B`) between table rows
- Grass-texture hero backgrounds (CSS `repeating-linear-gradient` or WebGL shader)
- Stadium floodlight bloom glow on active cards (`box-shadow: 0 0 40px rgba(74,222,128,0.08)`)
- Corner flags / goal-post iconography for match states

**Why it works for betting:** Green = money *and* the pitch. The floodlight atmosphere creates urgency without neon overstimulation. Familiar to any fan who watches night matches.

**Real-world refs:** UEFA broadcast overlays, Sky Sports Monday Night Football graphics, LED perimeter boards.

---

## 2. Athletic / Training App

**Vibe:** Nike Training Club, Under Armour Baselayer. Performance, discipline, team identity.

| Token | Hex | Usage |
|---|---|---|
| Background | `#000000` | Absolute black (Nike NTC foundation) |
| Surface | `#1C1C1E` | iOS dark gray cards |
| Accent | `#FF3B30` | Team red — primary CTA, active league |
| Success | `#34C759` | Apple-style green for wins |
| Danger | `#FF9500` | Warning orange for losses (not blood-red) |
| Text Primary | `#FFFFFF` |
| Text Secondary | `#8E8E93` |

**Typography**
- Display: `SF Pro Display` or `Inter` — Bold Condensed style, uppercase for headers, 32–64px
- Body: `SF Pro Text` or `Inter` — 400/500, 15–17px
- Accent: `Oswald` or `Bebas Neue` — 700, tracking +0.05em, for team names and league badges

**Visual Motifs**
- Full-bleed hero imagery with dark gradient overlay (`linear-gradient(to top, rgba(0,0,0,0.9), transparent)`)
- Bold colorway blocks by league/competition (Premier League = purple, La Liga = red)
- Circular progress rings for prediction confidence (SVG `stroke-dasharray`)
- High-contrast stat badges: black text on solid color blocks

**Why it works for betting:** Betting *is* performance analysis. The training-app aesthetic reframes gambling as disciplined, data-driven decision-making. Reduces stigma.

**Real-world refs:** Nike Training Club (2019 Premium), Under Armour MapMyRun Baselayer refresh, Adidas Running app.

---

## 3. Sports Data / Football Manager

**Vibe:** StatsBomb Kitbag, Opta dashboards, FM scouting screens. Dense, precise, trusted.

| Token | Hex | Usage |
|---|---|---|
| Background | `#020617` | Void black (StatsBomb IQ) |
| Surface | `#0F172A` | Card/panel |
| Surface Elevated | `#1E293B` | Hover/selected row |
| Accent | `#38BDF8` | Sky blue — links, active filters, xG highlights |
| Success | `#4ADE80` | Positive xG diff, win probability |
| Danger | `#F87171` | Negative diff, loss |
| Text Primary | `#F1F5F9` |
| Text Secondary | `#64748B` | Muted labels |

**Typography**
- Display: `Manrope` — 800, tight tracking, 24–40px for section headers
- Body: `DM Sans` — 400/500, 13–15px
- Data/Table: `JetBrains Mono` or `IBM Plex Mono` — 500, tabular-nums, 12–14px

**Visual Motifs**
- Data grid tables with 1px `#1E293B` row borders (no vertical borders)
- Heatmap cells: `hsl()` interpolation from blue (low) → green (mid) → red (high)
- Radar charts for team/player comparison (recharts/plotly)
- Sticky column headers with subtle bottom shadow
- Color-coded gradient bars for probability distributions (red→yellow→green)

**Why it works for betting:** This is the language analysts and serious bettors already speak. Dense data feels authoritative. The dark void reduces eye strain during long research sessions.

**Real-world refs:** StatsBomb IQ, Opta Search, Football Manager 2024 scouting, FBref tables.

---

## 4. Motorsport Telemetry

**Vibe:** F1 timing screens, pit wall, sector deltas. Precision, speed, team colors.

| Token | Hex | Usage |
|---|---|---|
| Background | `#050505` | Carbon / cockpit black |
| Surface | `#1A1A1A` | Telemetry panel |
| Surface Elevated | `#2D2D2D` | Active sector |
| Accent | `#00F260` | Signal green — live data, best lap |
| Accent Secondary | `#A855F7` | Purple — sector best, personal best |
| Success | `#00F260` |
| Danger | `#FF3B30` | Red flag, incident, DNF |
| Text Primary | `#EAEAED` | Dashboard white |
| Text Secondary | `#6B7280` | Inactive telemetry |

**Typography**
- Display: `JetBrains Mono` — 700, 20–32px for timing data
- Body: `Inter` — 400, 13–15px
- Telemetry: `JetBrains Mono` — 500, tabular-nums, 11–14px (crucial for aligning decimals)

**Visual Motifs**
- Sector time coloring: purple = overall best, green = personal best, yellow = within 0.1s, white = default, red = off pace
- Thin vertical separator lines between data columns (1px `#333`)
- Animated live indicators: pulsing 4px green dot (`animation: pulse 2s infinite`)
- Tire compound badges: soft = red, medium = yellow, hard = white, wet = blue
- Mini sparkline charts in table cells for form/momentum

**Why it works for betting:** Betting on live events *is* a race against time. The F1 aesthetic communicates real-time urgency and precision. Color-coding by performance delta is immediately readable.

**Real-world refs:** F1 Live Timing app, matteocelani/f1-telemetry, PITWALL dashboard, RaceControl messages.

---

## 5. Minimalist / Apple Sports

**Vibe:** Apple Sports app. Restraint, speed, hierarchy. Data density without clutter.

| Token | Hex | Usage |
|---|---|---|
| Background | `#000000` | Pure black |
| Surface | `#1C1C1E` | Elevated card |
| Surface Secondary | `#2C2C2E` | Segmented control bg |
| Accent | `#0A84FF` | iOS blue — primary action |
| Success | `#30D158` | iOS green |
| Danger | `#FF453A` | iOS red |
| Text Primary | `#FFFFFF` |
| Text Secondary | `#8E8E93` | iOS gray |

**Typography**
- Display: `SF Pro Display` or `Inter` — SF’s variable font width axis for compact scores (e.g., "3–1"), 36–64px
- Body: `SF Pro Text` or `Inter` — 400/500, 15–17px
- Data: `SF Mono` or `IBM Plex Mono` — 500, 13px

**Visual Motifs**
- Vibrancy effects: labels at 60% opacity with background bleed-through (CSS `mix-blend-mode: overlay` or backdrop-filter)
- Motion backgrounds: subtle animated gradient shifts (±10% hue drift) behind hero sections
- System-style segmented controls instead of heavy tabs
- Iconography over text wherever possible (team logos, sport glyphs)
- Generous whitespace: 24–32px section padding, 16px card padding
- Tabular data grids with generous line-height (1.6) for scannability

**Why it works for betting:** Apple’s design philosophy is "get to the answer in one tap." For betting, this means odds, form, and predictions surfaced instantly without cognitive load. The starkness feels premium and trustworthy.

**Real-world refs:** Apple Sports app (iOS 17+), Apple TV+ live sports broadcasts, MLB app redesign.

---

## Cross-Cutting Recommendations

| Concern | Recommendation |
|---|---|
| **Live indicator** | Pulsing 6px dot, accent color, 2s CSS pulse animation. Never use text alone ("LIVE"). |
| **Odds formatting** | Always tabular-nums. Decimal odds: 2 decimals (1.85). Fractional: space before slash (5 / 2). |
| **Color blindness** | Never rely on red/green alone. Add icons (▲▼) or patterns to win/loss indicators. |
| **Dark mode default** | All five themes are dark-first. Light mode should invert surfaces, not just invert colors. |
| **Motion** | Subtle parallax on hero, smooth 300ms transitions on card hover. Never flashy — this is money, not a game. |

## Quick Decision Matrix

| If your user is... | Pick... |
|---|---|
| Casual fan, mobile-first | **5. Apple Sports Minimalist** |
| Serious bettor, desktop research | **3. Football Manager Data** |
| Live betting, real-time focus | **4. F1 Telemetry** |
| Brand needs warmth/energy | **2. Athletic Training** |
| Brand needs tradition/authenticity | **1. Stadium Broadcast** |
