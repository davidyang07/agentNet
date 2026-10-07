---
version: 1.0
name: AgentShield-console
description: "AgentShield's operator console, specialized from the Linear design analysis (getdesign `linear.app`). Linear supplies the skeleton: a near-black canvas, a four-step surface ladder carrying hierarchy without shadows, hairline borders, light-gray ink, Inter type with tight tracking, and a single lavender accent used scarcely. AgentShield replaces Linear's marketing scale with console density (13px body), and adds a security-state palette — the one place colour carries meaning. Every colour on screen is either structure (neutral), interaction (lavender), or the compromise status of something (red / amber / teal / mint / gray)."

# Token names are the CSS custom properties in frontend/src/app/globals.css
# (`--color-<name>`, `--radius-<name>`, `--text-<name>`); Tailwind exposes them as
# `bg-<name>`, `text-<name>`, `border-<name>`, `rounded-<name>`. The Linear name each
# one replaces is in the Colors section.
colors:
  # Structure — surface ladder (darkest first) and hairlines
  canvas: "#08090a"
  surface: "#0f1011"
  raised: "#151618"
  overlay: "#1c1d20"
  line: "#23252a"
  line-strong: "#34343a"
  # Ink
  fg: "#f7f8f8"
  fg-muted: "#9ba1ab"
  fg-subtle: "#7d838c"
  # Interaction (never meaning)
  accent: "#5e6ad2"
  accent-hover: "#5560c8"
  accent-soft: "#181b28"
  accent-line: "#2b2f55"
  on-accent: "#ffffff"
  # Security state / severity (meaning only)
  critical: "#d33a3e"
  critical-soft: "#271516"
  critical-line: "#541f21"
  high: "#e8742a"
  high-soft: "#291c14"
  high-line: "#5b331a"
  warn: "#ecaa0b"
  warn-soft: "#2a2210"
  warn-line: "#5c460f"
  contained: "#21a3bc"
  contained-soft: "#112226"
  contained-line: "#15434d"
  ok: "#7df1cb"
  ok-soft: "#1c2b27"
  ok-line: "#365f52"
  neutral: "#80858e"
  neutral-soft: "#1d1e20"
  neutral-line: "#37393d"
  # Graph edges — structure, so neutral steps distinguished by lightness
  edge-mesh: "#2c2e33"
  edge-access: "#3e4047"
  edge-oversight: "#565961"

typography:
  display:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: 600
    lineHeight: 1.125
    letterSpacing: -1.44px
  page-title:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.45
    letterSpacing: -0.2px
  metric:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.4px
  section-title:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.55
    letterSpacing: 0
  body:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  label:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0
  micro:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.45
    letterSpacing: 0
  mono:
    fontFamily: Geist Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0

rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px

components:
  shell-frame:
    backgroundColor: "{colors.canvas}"
  content-inset:
    backgroundColor: "{colors.surface}"
    border: "1px {colors.line}"
    rounded: "{rounded.lg}"
    margin: 8px 8px 8px 0
  sidebar-item:
    textColor: "{colors.fg-muted}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.sm}"
    padding: 6px 8px
  sidebar-item-active:
    backgroundColor: "{colors.overlay}"
    textColor: "{colors.fg}"
  panel:
    backgroundColor: "{colors.raised}"
    border: "1px {colors.line}"
    rounded: "{rounded.lg}"
    padding: 16px
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: 0 12px
    height: 32px
  button-default:
    backgroundColor: "{colors.overlay}"
    textColor: "{colors.fg}"
    border: "1px {colors.line-strong}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: 0 12px
    height: 32px
  button-ghost:
    textColor: "{colors.fg-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
  status-badge:
    backgroundColor: "{colors.overlay}"
    textColor: "{colors.fg-muted}"
    border: "1px {colors.line}"
    typography: "{typography.micro}"
    rounded: "{rounded.full}"
    padding: 1px 8px
  state-dot:
    size: 8px
    rounded: "{rounded.full}"
  metric-tile:
    backgroundColor: "{colors.raised}"
    border: "1px {colors.line}"
    rounded: "{rounded.lg}"
    padding: 14px
  table-row:
    typography: "{typography.caption}"
    border: "1px {colors.line} bottom"
    height: 36px
  graph-node:
    fill: "state colour"
    shape: "node type"
  banner-critical:
    backgroundColor: "{colors.critical-soft}"
    border: "1px {colors.critical-line}"
    textColor: "{colors.fg}"
  banner-warn:
    backgroundColor: "{colors.warn-soft}"
    border: "1px {colors.warn-line}"
    textColor: "{colors.fg}"
---

## Overview

AgentShield is an operator console for watching compromise spread through a typed graph of
agents, tools, credentials, resources and sentinels. The design is **Linear's product
language, specialized for a security instrument**:

- **Kept from Linear:** the near-black canvas, the surface ladder (canvas → surface → raised →
  overlay) that carries hierarchy instead of shadows, 1px hairlines, light-gray ink, Inter with
  tight tracking on titles, an inset content area beside a quiet sidebar, and one lavender accent
  used scarcely.
- **Changed for the console:**
  - **Density.** Linear's marketing scale (16px body, 80px display) becomes a console scale: 13px
    working text, 18px page titles, 24px metrics.
  - **Meaning.** Linear's marketing has one semantic colour (success green). A security console
    needs a full **security-state palette**. It is the only place hue carries meaning, and it is
    tuned so the states stay distinguishable under colour-vision deficiency.
  - **Accent.** The lavender stays, but only for interaction: the primary action, focus, selection
    and a traced attack path. It never encodes state. The quarantine colour was moved away from
    purple to teal so the two can never be confused.
  - **Legibility.** Linear's tertiary ink (#62666d, 3.3:1) is lifted to #7d838c (5.0:1), so the
    smallest console text still passes WCAG AA.

**The one rule:** every colour on screen is *structure* (neutral grays), *interaction*
(lavender), or *compromise status* (the state palette). Nothing is decorative.

## Colors

### Structure

| Token | Value | Linear equivalent | Use |
|---|---|---|---|
| `canvas` | #08090a | canvas (#010102) | App frame and sidebar. Lifted off pure black so hairlines on it stay visible. |
| `surface` | #0f1011 | surface-1 | The inset content area. Table headers sit on it. |
| `raised` | #151618 | surface-2 | Panels, tiles and cards inside the content area. |
| `overlay` | #1c1d20 | surface-3 | Hover, the selected nav item, the active segment, badge fill, popovers. |
| `line` | #23252a | hairline | The default 1px border and divider. |
| `line-strong` | #34343a | hairline-strong | Borders of controls (inputs, default buttons). |

### Ink

| Token | Value | Contrast on `raised` | Use |
|---|---|---|---|
| `fg` | #f7f8f8 | 17.0:1 | Titles, values, identifiers, anything the eye should land on. |
| `fg-muted` | #9ba1ab | 7.0:1 | Body copy, table cells, descriptions. |
| `fg-subtle` | #7d838c | 4.7:1 | Labels, hints, column headers, timestamps. |

Text always wears ink. A state colour never colours a word. It goes on a dot, icon, meter, bar
or graph mark *beside* the word.

### Interaction

| Token | Value | Use |
|---|---|---|
| `accent` | #5e6ad2 | The primary button fill (white text, 4.7:1), the focus ring, the selected-row tint and a traced attack path. |
| `accent-hover` | #5560c8 | Primary button hover. Darker rather than lighter, so the white label keeps ≥4.5:1. |
| `accent-soft` / `accent-line` | #181b28 / #2b2f55 | Selected rows, selected chips. |

There is never more than one primary button per screen region. Links are ink with a hover
underline, not accent-coloured.

### Security state and severity — the only meaningful colours

| State | Severity token | Value | Reads as |
|---|---|---|---|
| Healthy | `neutral` | #80858e | Unremarkable. Gray, so a healthy fleet looks calm. |
| Suspicious | `warn` | #ecaa0b | Amber: flagged, not confirmed. |
| Compromised | `critical` | #d33a3e | Deep red: attacker-controlled. |
| Quarantined | `contained` | #21a3bc | Teal: isolated, cannot propagate. Deliberately far from the lavender accent. |
| Recovered | `ok` | #7df1cb | Light mint: trusted again. |
| — (findings only) | `high` | #e8742a | Orange: between critical and warn on the findings scale. |

How the palette was chosen: candidates were searched in OKLCH and checked with the dataviz
skill's validator against `canvas`.

- **The four co-occurring graph states** (suspicious, compromised, quarantined, recovered), checked
  across all pairs:
  - colour-vision-deficient separation: worst ΔE **17.0**, against a target of 8
  - normal vision: worst ΔE **22.3**, against a floor of 15
  - contrast: all ≥3:1 against the canvas
- **Compromised vs recovered.** This is the classic red/green failure. Lightness separates them:
  deep red at L 0.58, light mint at L 0.88. That is why recovered is mint rather than a mid green.
- **The findings scale** (critical → high → warn) is ordinal. Its lightness is monotonic with
  visible steps. Its hue spread (red → orange → amber) follows security-severity convention, so it
  always carries a text label and icon.

Each state also has two tints, both mixed into `surface`:

- `-soft` (12%) for banner and selected-row backgrounds
- `-line` (35%) for their borders

Use them for an area that *is* in that state, such as a critical error banner. Never use them as
decoration.

### Graph edges

Edges are structure, so they are neutral. The three edge layers differ by lightness only:

- `edge-mesh` #2c2e33: communication
- `edge-access` #3e4047: tool, credential and resource access
- `edge-oversight` #565961: monitoring and quarantine authority

Only two edge treatments have colour:

- a traced attack path, in `accent`
- edges of the selected node, in `fg-muted`

## Typography

- **Families:**
  - **Inter**, via `next/font/google`, for everything. It is the substitute the Linear analysis
    recommends.
  - **Geist Mono** for identifiers, seeds, ticks, config keys and numbers in logs.
- **Scale:** Tailwind classes map onto the tokens.

| Token | Class | Size / line | Weight | Use |
|---|---|---|---|---|
| display | `text-4xl` → `lg:text-5xl` | 36 / 42 → 48 / 54 | 600, −1 to −1.4px | The landing page's headline only. Never in the console. |
| page-title | `text-xl` | 18 / 26 | 600, −0.2px | One per screen, in `PageHeader`. |
| metric | `text-2xl` | 24 / 30 | 600, −0.4px | KPI values, and the landing page's section headings. |
| section-title | `text-sm` | 13 / 20 | 500 | Panel titles, nav items. |
| body | `text-base` | 14 / 22 | 400 | Page default, prose. |
| body-sm | `text-sm` | 13 / 20 | 400 | Working text in panels and forms. |
| caption | `text-xs` | 12 / 18 | 400 | Descriptions, table cells, event rows. |
| label | `text-xs` | 12 / 18 | 500 | Buttons, section labels (`.eyebrow`), column headers. |
| micro | `text-2xs` | 11 / 16 | 500 | Badges, chart axes, units. **Nothing renders below 11px.** |
| mono | `font-mono text-xs` / `text-2xs` | 12 or 11 | 400 | Ids, ticks, values in logs. |

- **Section labels** use Linear's sidebar-header voice: sentence case, 12px, weight 500,
  `fg-subtle`. They do not use uppercase tracking.
- **Numbers** that change (tables, metrics, logs) use tabular figures.
- **Canvas text** (graph labels) uses the same families. Canvas cannot resolve CSS variables, so
  the font is read from the computed `--font-mono` / `--font-sans` at draw time.

## Layout

- **Spacing:** a 4px base, Tailwind's default scale (`1` = 4px). Panels pad 16px. Tiles pad
  14px. A screen's sections are 16–20px apart. Rows inside a list are separated by a hairline,
  not by gaps.
- **Shell:**
  - **Wide screens** (`lg` and up): a 224px sidebar on `canvas`, and the content in an inset
    `surface` panel (8px from the frame, `rounded.lg`, hairline border) that scrolls on its own.
    The run-context bar is the first row of the inset.
  - **Narrow screens:** the sidebar becomes a horizontal strip.
- **Navigation is the workflow.** The sidebar lists the four steps (Set up, Watch, Results, Fix &
  re-test) as numbered markers joined by a hairline, the current step's marker in `accent`; Runs
  sits apart under Archive. Every step screen opens with a "Step N of 4" eyebrow and points to the
  next step. Each piece of information lives on exactly one screen — never repeat a panel on a
  second screen to save the operator a click.
- **Density.** Match the references in `design-refs/`: list rows about 36px, single-line event
  rows, and labels left with values right.
- **Landing (`/`)** sits outside the shell: full width on `canvas`, no sidebar, content in a
  1152px column (`max-w-6xl`), sections split by hairlines. In order: the headline and one
  factual paragraph, the start or resume buttons, a framed Watch screenshot, the four steps
  (each with its screenshot), what it models / measures / its limits, and a closing call to
  action. Screenshots are real captures of the console in `frontend/src/app/_landing/`. Copy
  states what the tool does and where it stops; it makes no claim the console cannot show.

## Elevation & depth

- **Depth comes from surfaces:** canvas → surface → raised → overlay.
- **Panels** carry a 1px top-edge highlight (`inset 0 1px 0 rgb(255 255 255 / 0.03)`), Linear's
  "pixel-rendered" edge, and no drop shadow.
- **Popovers and tooltips** are the only elements with a real shadow (`shadow-pop`).

## Shapes

| Token | Value | Use |
|---|---|---|
| `xs` | 4px | Chips, small tags, inline code. |
| `sm` | 6px | Nav items, segmented-control segments, inputs inside dense rows. |
| `md` | 8px | Buttons, inputs, banners. |
| `lg` | 12px | Panels, tiles, the content inset. |
| `full` | 9999px | Status badges, dots, meters. |

Graph node **type** is carried by shape and size, never colour:

- agent: circle
- tool: square
- credential: diamond
- resource: hexagon
- security control: shield
- sentinel: triangle

## Iconography

- **lucide-react only.** No other icon set, no emoji, no hand-drawn icons.
- **Size:** 16px (`size-4`) in nav and buttons, 14px (`size-3.5`) inline with 12px text.
- **Stroke** 1.75.
- **Colour:** icons take the colour of their text (`currentColor`), except a status icon, which
  takes its state colour.

## Components

- **Panel** (`components/ui/Panel.tsx`) is the only container. It uses `raised` with a hairline and
  `rounded.lg`. Its header is a 13px/500 title with a 12px `fg-muted` description.
- **Status badge:**
  - shape: a pill on `overlay` with a hairline, 11px `fg-muted` text
  - state: an 8px dot in the state colour (the dot is the only colour)
  - a running run's dot pulses
- **Metric tile:** an `eyebrow` label, a 24px `fg` value, and a 4px meter whose fill is the state
  colour. The value itself is never coloured.
- **Stat row:** label left, mono value right, dotted leader. If the value has a state, a dot sits
  before the value.
- **Table:**
  - header row: `eyebrow` labels on `surface`
  - rows: hairline-separated, 12px
  - a clickable row tints `overlay` on hover
  - the selected row is `accent-soft`
- **Event row** (activity stream, after Axiom):
  - layout: tick in mono `fg-subtle`, a state dot, the event label in `fg`, the actors in mono,
    the details right-aligned in `fg-subtle`
  - one line, truncated, never wrapped
- **Inputs:** `surface` (one step down from the panel they sit on), a `line-strong` hairline,
  `rounded.md`, 32px tall. Focus turns the border `accent`. A selected chip or preset uses
  `accent-soft` / `accent-line` with an ink label.
- **Run progress** in the run bar is a neutral `fg-subtle` meter. Progress is not a security
  state.
- **Buttons:**
  - `primary`: accent fill, white label
  - `default`: overlay with a strong hairline
  - `ghost`: text only
  - `danger`: critical tint with ink text
  - all are 32px tall (28px for `sm`), `rounded.md`
- **Banners:**
  - critical (error) and warn banners use their `-soft` background and `-line` border, with `fg`
    text and a state icon
  - the disclaimer is plain `fg-subtle` micro text
- **Remediation diff** (after GitHub "Files changed"): a config key in mono, the before value
  struck in `fg-subtle`, `→`, then the proposed value in an `ok` chip.
- **Graph:**
  - background: the `surface` inset
  - node fill: the state colour; node shape: the type
  - labels: mono, 11px, on a `canvas` chip; `fg-muted`, or `fg` for whatever the operator is
    looking at (selected, hovered or on a traced path)
  - halo: a white ring on the selected node
  - attack path: drawn in `accent`, with numbered steps

## Data visualization

- **Outbreak chart.** A stacked area of `critical` (compromised) under `contained`
  (quarantined), with a 2px `raised` gap between the bands.
  - axes and grid use `line` and `fg-subtle` at 11px
  - the hover crosshair uses `line-strong`
  - there is always a legend, and the end of each band is labelled directly with ink text
- **Status is never colour alone.** Every state appears with its label in the legend, the
  inspector, the badge or the tooltip.

## Do's and Don'ts

### Do

- Put colour on marks (dots, meters, nodes, bands), and keep the words beside them in ink.
- Use the surface ladder for hierarchy, and skip a level only for the content inset.
- Keep one primary button per region.
- Keep working text at 12–13px, and never go below 11px.

### Don't

- No gradients, gradient text, glassmorphism or glow effects.
- No emoji or non-lucide icons.
- No marketing copy.
- Never use accent lavender to mean anything about security, and never give a state colour to
  something that is not in that state.
- Never colour a number by its value. Put a dot or meter beside it.
- Don't use Tailwind's default palette (`white`, `zinc-*`, `red-*` …). It is disabled in
  `globals.css`, so only these tokens exist.

## Responsive behavior

| Width | Changes |
|---|---|
| ≥1024px (`lg`) | Sidebar plus content inset. Two- and three-column panel grids. |
| <1024px | The sidebar becomes a horizontal scroll strip under the run bar. The content is full-bleed. Panels stack. |
| 390px | Tables keep their columns and scroll horizontally inside their panel, and cells don't wrap. The graph keeps its full panel width. |

Touch targets are at least 32px tall.

## Provenance

Derived from `npx getdesign@latest add linear.app` (Linear's marketing analysis). The values
not listed here (display type, marketing cards, pricing components) do not apply to the console
and were dropped. Layout references live in `design-refs/`, and the hardcoded-value audit that
preceded this system is `design-refs/token-audit.md`.
