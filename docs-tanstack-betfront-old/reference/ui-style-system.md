# UI Style System from Old TanStack App

## Typography

Imported Google fonts:

- `Fraunces` for display titles.
- `Manrope` for sans body UI.

## Palette

Light theme core tokens:

- `--sea-ink`: dark blue/green text.
- `--sea-ink-soft`: muted text.
- `--lagoon`: bright teal.
- `--lagoon-deep`: deep teal action color.
- `--palm`: green accent.
- `--sand`: warm pale background.
- `--foam`: pale green/white background.
- `--surface`: translucent white panel.
- `--surface-strong`: stronger translucent panel.
- `--line`: low-opacity border.

Dark theme inverted these tokens into teal-on-dark surfaces.

## Background treatment

The body used layered radial gradients plus a linear gradient for a soft sports/analytics feel:

- large teal glow top-left
- green glow top-right
- low teal glow bottom
- subtle grid overlay through `body::after`

## Layout classes

- `page-wrap`: central max-width page container.
- `island-shell`: translucent rounded card with border/backdrop style.
- `display-title`: display-font heading.
- `island-kicker`: small uppercase context label.
- `feature-card`: raised/animated feature cards.
- `nav-link`: active navigation affordance.

## Motion

The old UI used `rise-in` style entry animations and hover translate effects on cards/buttons.

## Accessibility notes

- Many icon links had `sr-only` labels.
- Buttons and controls used real `button`, `input`, and Radix primitives.
- Some controls depended on emoji labels; Svelte migration should pair emoji with text labels and ARIA where needed.

## Migration notes for Svelte platform

- The active Svelte UI already has its own design system; do not blindly copy CSS.
- Reuse useful patterns: glass cards, clear workflow tabs, status badges, progress/log panels.
- Prefer current `frontend/src/lib/components` primitives and Tailwind 4 tokens.
