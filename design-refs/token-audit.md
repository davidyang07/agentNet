# Hardcoded design values audit: `frontend/src`

> **Status:** this is the record from *before* the redesign. The redesign pass removed every
> colour literal, default-palette class, sub-11px text size and arbitrary Tailwind spacing value
> listed here. Colours now come from `DESIGN.md` via `globals.css`, and the canvas/WebGL renderers
> read them through `frontend/src/lib/theme.ts`, which also fixes the ignored canvas fonts.
> What remains is renderer geometry: graph ring offsets, node sizes and chart padding. It stays
> in `TopologyGraph.tsx`, `lib/graph/model.ts` and `OutbreakChart.tsx`, with the values that size
> text named.
> Line numbers refer to the pre-redesign code.

**Scope:** every `.ts`, `.tsx` and `.css` file under `frontend/src`, excluding `frontend/src/lib/api/schema.d.ts`. All component, app, `lib/graph`, `severity.ts` and `vocabulary.ts` files were read in full. I also ran ripgrep sweeps for hex, rgb/hsl/oklch, default-palette classes, `[..]` arbitrary values, `style=`, font props, Sigma settings, SVG/canvas attributes and px/rem units.

**Reference:** design tokens are defined in `@theme` at `frontend/src/app/globals.css` L18–L84. I did not count anything inside that block.

**Method:** this was a read-only audit, run on the `ui-redesign` branch before any UI change. Every line number below was checked against the file with `rg -n` or `sed -n`.

## Summary

| Category | Occurrences | Files |
|---|---|---|
| Colors: literal values (hex/rgb/rgba in TS, plus CSS outside `@theme`) | 25 | 7 |
| Colors: Tailwind default-palette classes | 4 | 4 |
| Colors: applied from JS constants (inline `style`, SVG attrs, Sigma attrs, canvas) | 22 | 4 |
| Token values duplicated in JS/TS (exact; a subset of the literal colors, plus 1 radius) | 16 (+3 near-duplicates) | 4 |
| Token names referenced by string | 8 | 3 |
| Fonts / type | 9 | 4 |
| Spacing (padding/margin/gap/inset/offset) | 28 | 9 |
| Fixed sizing (width/height/size/stroke width) | 20 | 7 |
| Other (border width, opacity, duration, radius, transition) | 13 | 7 |
| Borderline / probably fine | 21 groups | — |

Some rows overlap. "Token values duplicated" is a subset of the literal colors, plus one radius and the font stacks. "Applied from JS constants" lists the places that *consume* those literals. The two rows are not additive.

### Key findings
1. **`SEVERITY_HEX` (`frontend/src/lib/severity.ts` L44–L51) duplicates all 6 severity token values.** Its doc comment (L39–L43) says "the graph is the only consumer". That is no longer true:
   - The map is also used by the outbreak chart: `OutbreakChart.tsx` L17, L18, L127, L128, L144, L152, and inline styles at L216 and L266.
   - The legend swatches use it too, in `GraphLegend.tsx` L77. These are DOM/SVG elements that could use the `bg-*`/`fill-*` token classes instead.
2. **`TopologyGraph.tsx` has the most hardcoded values:**
   - 10 color literals. Seven of them restate token values: accent, neutral, canvas ×3 and fg ×2.
   - 2 canvas font strings.
   - About 19 pixel constants for rings, halos, label chips and step badges.
3. **Some palette colors exist only in JS, with no token:**
   - Edge-layer colors (`vocabulary.ts` L230, L235, L240).
   - The inactive layer swatch `#2a3040` (`GraphLegend.tsx` L137).
   - Chart gridline and crosshair (`OutbreakChart.tsx` L122, L137).
   - Selected-edge color `#5f7fae` and label foreground `#c7cfdb` (`TopologyGraph.tsx` L167, L21).
   - Scrollbar-hover color `#3c465a` (`globals.css` L135).
4. **Some text sizes fall below the type scale.** There are 7 `text-[9px]`/`text-[10px]` classes, and the canvas uses 9px/10px. All of these are smaller than the smallest token, `text-2xs` (0.6875rem = 11px).
5. **Default palette leakage:** `text-white` ×2, `bg-white` and `via-white/[0.04]`. The `@theme` block does not reset `--color-*: initial`, so the whole default Tailwind palette still compiles.
6. **The canvas `ctx.font` strings in `TopologyGraph.tsx` (L352, L401) embed `var(--font-geist-*)`, which Canvas 2D cannot parse, so Chromium ignores both assignments.** Verified in Chromium: after either assignment, `ctx.font` still reads `10px sans-serif`. Graph labels and attack-path step numbers therefore render in the fallback `10px sans-serif`, not Geist Mono 500 or Geist Sans 600.

---

## Colors

### Literal values (25)

#### `frontend/src/lib/severity.ts`
- L45: `critical: "#f2555f",`. Same as `--color-critical`.
- L46: `high: "#f5834e",`. Same as `--color-high`.
- L47: `warn: "#e0b341",`. Same as `--color-warn`.
- L48: `contained: "#a273f2",`. Same as `--color-contained`.
- L49: `ok: "#3fb87a",`. Same as `--color-ok`.
- L50: `neutral: "#7b8698",`. Same as `--color-neutral`.

#### `frontend/src/lib/vocabulary.ts`
- L230: `color: "#2b3340",`. Mesh edge color (`EDGE_LAYER_META.mesh`); no token.
- L235: `color: "#3a4c63",`. Access edge color; no token.
- L240: `color: "#3d3357",`. Oversight edge color; no token.

#### `frontend/src/components/graph/TopologyGraph.tsx`
- L20: `const ACCENT = "#4d8dfd";`. Same as `--color-accent`.
- L21: `const LABEL_FG = "#c7cfdb";`. Canvas label text; no token (sits between fg and fg-muted).
- L22: `const LABEL_BG = "rgba(10, 12, 16, 0.82)";`. `--color-canvas` (#0a0c10) at 82% alpha.
- L143: `defaultNodeColor: "#7b8698",`. Same as `--color-neutral`.
- L167: `return { ...data, color: "#5f7fae", size: 1.6, zIndex: 2 };`. Edge color for edges touching the selection; no token.
- L260: `if (!rgba) return "rgba(60, 68, 82, 0.55)";`. Fallback dim color; no token.
- L262–L264: `+ 10 * 3) / 4` / `+ 12 * 3) / 4` / `+ 16 * 3) / 4`. Canvas RGB (10,12,16) hard-wired into `dim()`; this is `--color-canvas`.
- L322: `ctx.strokeStyle = isSelected ? "#e7ecf3" : …`. Same as `--color-fg`.
- L322: `… : "rgba(231, 236, 243, 0.55)";`. `--color-fg` at 55% alpha (second literal on the same line).
- L400: `ctx.fillStyle = "#0a0c10";`. Same as `--color-canvas`; text color of the step number.

#### `frontend/src/components/insights/OutbreakChart.tsx`
- L14: `const SURFACE = "#10131a";`. Same as `--color-surface`.
- L122: `stroke="#1c222c"`. Gridlines; near `--color-overlay` (#1c212b) but not equal.
- L137: `stroke="#4d5b73"`. Hover crosshair; no token.

#### `frontend/src/components/graph/GraphLegend.tsx`
- L137: `style={{ background: active ? meta.color : "#2a3040" }}`. Inactive layer swatch; literal in an inline style.

#### `frontend/src/components/ui/Field.tsx`
- L120: `… fill='none' stroke='%2398a3b4' stroke-width='1.4'><path d='M3 4.5 6 7.5 9 4.5'/></svg>…`. URL-encoded `#98a3b4` = `--color-fg-muted`, inside the select chevron's data URI.

#### `frontend/src/app/globals.css` (outside `@theme`)
- L135: `background-color: #3c465a;`. Scrollbar thumb hover; no token.

### Tailwind default-palette classes (4)

#### `frontend/src/components/ui/Button.tsx`
- L16: `"border-accent-line bg-accent text-white hover:bg-accent-hover hover:border-accent-hover",`. Primary button text uses `white`, not `fg`.

#### `frontend/src/components/insights/WorkflowTracker.tsx`
- L43: `stage.state === "active" && "bg-accent text-white",`. Active-stage number badge.

#### `frontend/src/components/ui/Field.tsx`
- L180: `"absolute top-0.5 size-3 rounded-full bg-white transition-[left] duration-150",`. Toggle knob.

#### `frontend/src/components/ui/States.tsx`
- L97: `… bg-gradient-to-r from-transparent via-white/[0.04] to-transparent …`. Skeleton shimmer; default `white` with an arbitrary opacity.

### Colors applied from JS constants (22)

These places paint with a JS color value instead of a token class or CSS variable. The underlying literals are listed above.

#### `frontend/src/lib/graph/model.ts`
- L132: `return SEVERITY_HEX[SECURITY_STATE_SEVERITY[node.securityState] ?? "neutral"];`. Sigma node color comes from the duplicate hex map.

#### `frontend/src/components/graph/TopologyGraph.tsx`
- L111: `color: nodeColor(node),`. Sigma node attribute, set via `SEVERITY_HEX`.
- L144: `defaultEdgeColor: EDGE_LAYER_META.mesh.color,`. Uses the non-token hex from `vocabulary.ts`.
- L161: `return { ...data, color: ACCENT, size: 2.4, zIndex: 3 };`. Attack-path edges.
- L172: `color: dimmed ? dim(EDGE_LAYER_META[layer].color) : EDGE_LAYER_META[layer].color,`
- L217: `const color = nodeColor(node);`. Live recolor, via `SEVERITY_HEX`.
- L332: `ctx.strokeStyle = ACCENT;`. Path ring.
- L380: `ctx.fillStyle = LABEL_BG;`. Label chip.
- L383: `ctx.fillStyle = LABEL_FG;`. Label text.
- L396: `ctx.fillStyle = ACCENT;`. Step badge.

#### `frontend/src/components/insights/OutbreakChart.tsx`
- L17: `{ key: "compromised" as const, label: "Compromised", color: SEVERITY_HEX.critical },`
- L18: `{ key: "quarantined" as const, label: "Quarantined", color: SEVERITY_HEX.contained },`
- L127: `<path d={geometry.compromisedPath} fill={SEVERITY_HEX.critical} fillOpacity="0.85" />`. Could be `fill-critical`.
- L128: `<path d={geometry.quarantinedPath} fill={SEVERITY_HEX.contained} fillOpacity="0.85" />`
- L144: `fill={SEVERITY_HEX.critical}`. Hover dot.
- L145: `stroke={SURFACE}`. Uses the `#10131a` literal.
- L152: `fill={SEVERITY_HEX.contained}`. Hover dot.
- L153: `stroke={SURFACE}`
- L216: `style={{ background: s.color }}`. Tooltip swatch; inline color.
- L266: `style={{ background: s.color }}`. Legend swatch; inline color. `SEVERITY_BG` classes exist for this.

#### `frontend/src/components/graph/GraphLegend.tsx`
- L77: `style={{ background: SEVERITY_HEX[SECURITY_STATE_SEVERITY[state]] }}`. State swatch; could be `SEVERITY_BG[…]`.
- L137: `style={{ background: active ? meta.color : "#2a3040" }}`. Edge-layer swatch from `EDGE_LAYER_META` (its literal is counted above).

---

## Token values duplicated in JS/TS

These are the most important entries. Each hardcodes a value that already exists as a token, so the two copies can drift apart.

### Maps that duplicate token values

#### `frontend/src/lib/severity.ts`
- L44: `export const SEVERITY_HEX: Record<Severity, string> = {`. A severity-to-hex map. All 6 entries below match `@theme` exactly:
  - L45: `critical: "#f2555f",`. Matches `--color-critical` (globals.css L46).
  - L46: `high: "#f5834e",`. Matches `--color-high` (L48).
  - L47: `warn: "#e0b341",`. Matches `--color-warn` (L50).
  - L48: `contained: "#a273f2",`. Matches `--color-contained` (L52).
  - L49: `ok: "#3fb87a",`. Matches `--color-ok` (L54).
  - L50: `neutral: "#7b8698",`. Matches `--color-neutral` (L56).
- Consumers:
  - `frontend/src/lib/graph/model.ts` L3 (import) and L132.
  - `frontend/src/components/insights/OutbreakChart.tsx` L5 (import), L17, L18, L127, L128, L144, L152.
  - `frontend/src/components/graph/GraphLegend.tsx` L9 (import) and L77.
- L39–L43 doc comment: says "the graph is the only consumer". That is stale: the outbreak chart and legend also use the map.

### Single constants that duplicate token values

#### `frontend/src/components/graph/TopologyGraph.tsx`
- L20: `const ACCENT = "#4d8dfd";`. Same as `--color-accent`.
- L22: `const LABEL_BG = "rgba(10, 12, 16, 0.82)";`. `--color-canvas` RGB plus alpha.
- L143: `defaultNodeColor: "#7b8698",`. Same as `--color-neutral`, which also equals `SEVERITY_HEX.neutral`.
- L262–L264: `… + 10 * 3) / 4` / `… + 12 * 3) / 4` / `… + 16 * 3) / 4`. `--color-canvas` RGB channels used in the dim mix.
- L322: `"#e7ecf3"`. Same as `--color-fg`.
- L322: `"rgba(231, 236, 243, 0.55)"`. `--color-fg` RGB plus alpha.
- L381: `roundRect(ctx, box[0], box[1], box[2], box[3], 3);`. Corner radius 3 = `--radius-xs` (3px).
- L400: `ctx.fillStyle = "#0a0c10";`. Same as `--color-canvas`.

#### `frontend/src/components/insights/OutbreakChart.tsx`
- L14: `const SURFACE = "#10131a";`. Same as `--color-surface`.

#### `frontend/src/components/ui/Field.tsx`
- L120: `stroke='%2398a3b4'`. Same as `--color-fg-muted`, URL-encoded in the SVG data URI.

### Near-duplicates (close to a token, but not equal)
- `frontend/src/components/insights/OutbreakChart.tsx` L122: `stroke="#1c222c"`. Differs from `--color-overlay` `#1c212b` by one step in G and B; probably meant to be the token.
- `frontend/src/components/graph/TopologyGraph.tsx` L352: `"500 10px var(--font-geist-mono, ui-monospace), ui-monospace, monospace"`. Re-states the `--font-mono` stack (globals.css L20) without `"SFMono-Regular"`.
- `frontend/src/components/graph/TopologyGraph.tsx` L401: `"600 9px var(--font-geist-sans, ui-sans-serif), sans-serif"`. Re-states the `--font-sans` stack (globals.css L19) without `system-ui`.

---

## Token names referenced by string

No TS/TSX file contains `var(--color-*)`, `var(--text-*)`, `var(--radius-*)` or `var(--shadow-*)`, and nothing calls `getComputedStyle`/`getPropertyValue`.

#### `frontend/src/components/graph/TopologyGraph.tsx`
- L352: `ctx.font = "500 10px var(--font-geist-mono, ui-monospace), ui-monospace, monospace";`. References the next/font variable, not the `--font-mono` token. Canvas does not resolve `var()`, so Chromium ignores the assignment (verified; see key finding 6).
- L401: `ctx.font = "600 9px var(--font-geist-sans, ui-sans-serif), sans-serif";`. Same issue, with `--font-geist-sans`.

#### `frontend/src/app/layout.tsx`
- L10: `variable: "--font-geist-sans",`. Defines the variable that `@theme --font-sans` (globals.css L19) consumes. The name is repeated in globals.css and TopologyGraph.tsx.
- L15: `variable: "--font-geist-mono",`. Same, for `--font-mono` (globals.css L20).

#### `frontend/src/lib/severity.ts`
- L39: `* Hex values mirroring the \`--color-*\` severity tokens in globals.css.`. Comment only.
- L54–L61: `SEVERITY_TEXT`, e.g. `critical: "text-critical",`. Token-based class names kept in a JS map. These are fine, but they restate the token names.
- L63–L70: `SEVERITY_BG`, e.g. `critical: "bg-critical",`. Same as above.
- L72–L79: `SEVERITY_CHIP`, e.g. `critical: "bg-critical-soft text-critical ring-critical/25",`. Same as above.

---

## Fonts / type

The type scale has no size below `text-2xs`, which is 0.6875rem (11px). Every entry below is smaller than that.

No matches were found for the following:
- `font-[..]`
- inline `fontSize`/`fontFamily`/`fontWeight`/`letterSpacing`/`lineHeight`
- `text-4xl` or larger
- arbitrary `tracking-[..]`/`leading-[..]`
- Sigma `labelFont`/`labelSize`/`labelColor` (Sigma labels are disabled: `renderLabels: false`, TopologyGraph.tsx L133)

#### `frontend/src/components/insights/OutbreakChart.tsx`
- L159: `<text x={PAD.left - 6} y={PAD.top + 4} textAnchor="end" className="fill-fg-subtle text-[9px]">`. Y-axis max label.
- L166: `className="fill-fg-subtle text-[9px]"`. Y-axis zero label.
- L174: `className="fill-fg-subtle text-[9px]"`. "tick N of M" label.
- L184: `className="fill-fg-muted text-[10px]"`. End label for the compromised band.
- L194: `className="fill-fg-muted text-[10px]"`. End label for the quarantined band.

#### `frontend/src/components/insights/WorkflowTracker.tsx`
- L41: `"flex size-4 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold",`. Stage number.

#### `frontend/src/components/graph/NodeInspector.tsx`
- L139: `className="flex size-4 shrink-0 items-center justify-center rounded-full border border-line text-[9px] text-fg-subtle"`. Causal-trace step number.

#### `frontend/src/components/graph/TopologyGraph.tsx`
- L352: `ctx.font = "500 10px var(--font-geist-mono, ui-monospace), ui-monospace, monospace";`. Canvas label: size, weight and family all hardcoded.
- L401: `ctx.font = "600 9px var(--font-geist-sans, ui-sans-serif), sans-serif";`. Canvas step-badge number.

---

## Spacing (padding / margin / gap / inset / offset)

#### `frontend/src/components/ui/States.tsx`
- L77: `<span aria-hidden className="mt-[3px] size-1.5 shrink-0 rounded-full bg-warn" />`. Optical alignment of the banner dot.
- L88: `<span aria-hidden className="mt-[5px] size-1 shrink-0 rounded-full bg-fg-subtle" />`. Disclaimer dot.

#### `frontend/src/components/run/RunConfigurator.tsx`
- L209: `<span aria-hidden className="mt-[5px] size-1 shrink-0 rounded-full bg-accent/70" />`. Scenario bullet.

#### `frontend/src/components/ui/Metric.tsx`
- L95: `<span aria-hidden className="min-w-3 flex-1 translate-y-[-3px] border-b border-dotted border-line" />`. Leader-line offset.

#### `frontend/src/components/insights/Panels.tsx`
- L157: `<SeverityDot severity={severity} className="translate-y-[-1px]" />`

#### `frontend/src/components/activity/EventRow.tsx`
- L31: `<SeverityDot severity={severity} className="translate-y-[-1px]" />`

#### `frontend/src/components/ui/Field.tsx`
- L122: `backgroundPosition: "right 6px center",`. Inline style; chevron inset, paired with `pr-6` on L117.

#### `frontend/src/components/insights/OutbreakChart.tsx`
- L10: `const PAD = { top: 10, right: 46, bottom: 18, left: 30 };`. Chart margins in px.
- L13: `const BAND_GAP = 2;`. Gap between stacked bands, in px.
- L159: `<text x={PAD.left - 6} y={PAD.top + 4} …`. Axis-label offsets 6 and 4.
- L163: `x={PAD.left - 6}`
- L172: `y={size.height - 4}`
- L182: `x={geometry.points[geometry.points.length - 1].x + 6}`. End-label gap.
- L192: `x={geometry.points[geometry.points.length - 1].x + 6}`
- L207: `left: Math.min(Math.max(hovered.x - 60, 4), Math.max(4, size.width - 130)),`. Inline style `left`. 60 is the half tooltip width, 4 the edge inset, and 130 an assumed tooltip width.

#### `frontend/src/components/graph/TopologyGraph.tsx` (canvas overlay, px)
- L299: `obstacles.push([x - radius - 4, y - radius - 4, (radius + 4) * 2, (radius + 4) * 2]);`. 4px padding around each node obstacle.
- L311: `traceShape(ctx, shape, x, y, radius + 3.5);`. Offset of the type ring.
- L325: `ctx.arc(x, y, radius + 6.5, 0, Math.PI * 2);`. Offset of the selection/hover halo.
- L335: `ctx.arc(x, y, radius + 5, 0, Math.PI * 2);`. Offset of the path ring.
- L358: `const boxWidth = textWidth + 8;`. Horizontal padding of the label chip.
- L364: `const gap = item.radius + 6;`. Gap from node to label.
- L367: `for (const dy of [0, -15, 15]) {`. Vertical nudge steps when placing labels.
- L369: `[boxX, item.y - 7 + dy, boxWidth, 14]`. Vertical offset of -7 (height 14 is listed under Fixed sizing).
- L384: `ctx.fillText(item.id, box[0] + 4, box[1] + 7.5);`. Label text inset.
- L398: `ctx.arc(x, y - radius - 11, 7, 0, Math.PI * 2);`. Step badge 11px above the node (radius 7 is under Fixed sizing).
- L403: `ctx.fillText(String(index + 1), x, y - radius - 10.5);`. Offset of the step number.

#### `frontend/src/app/globals.css` (outside `@theme`)
- L129: `border: 3px solid transparent;`. Scrollbar thumb inset (transparent border plus `background-clip`).
- L157–L158: `black 12px,` / `black calc(100% - 12px),`. Fade length of the `scrim-y` mask. Note: `scrim-y` is not used anywhere in `src`.

---

## Fixed sizing (width / height / size / stroke width)

#### `frontend/src/app/history/[id]/page.tsx`
- L153: `<div className="flex h-[clamp(340px,52vh,720px)] flex-col">`. Height of the replay graph.

#### `frontend/src/app/activity/page.tsx`
- L67: `<div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_320px] lg:p-5">`. Fixed 320px sidebar column.

#### `frontend/src/components/ui/Field.tsx`
- L120: `<svg … width='12' height='12' viewBox='0 0 12 12' … stroke-width='1.4'>`. Size and stroke of the select chevron, inside the inline-style data URI.

#### `frontend/src/lib/graph/model.ts`
- L108–L117: `export const NODE_SIZE: Record<string, number> = { agent: 3.4, tool: 5, … sentinel: 6.6, … };`. Sigma node sizes.
- L124: `const base = NODE_SIZE[node.nodeType] ?? 4;`. Fallback node size.
- L127: `if (node.nodeType === "agent" && node.attrs.agent_kind === "real") return base * 1.5;`. Size multiplier for real agents.

#### `frontend/src/components/graph/TopologyGraph.tsx`
- L123: `size: 1,`. Base edge width.
- L161: `return { ...data, color: ACCENT, size: 2.4, zIndex: 3 };`. Attack-path edge width.
- L167: `return { ...data, color: "#5f7fae", size: 1.6, zIndex: 2 };`. Width of edges touching the selection.
- L310: `ctx.lineWidth = 1.4;`. Stroke of the type ring.
- L323: `ctx.lineWidth = isSelected ? 1.6 : 1.2;`. Halo stroke.
- L333: `ctx.lineWidth = 1.8;`. Path-ring stroke.
- L369: `[boxX, item.y - 7 + dy, boxWidth, 14]`. Label chip height 14px.
- L398: `ctx.arc(x, y - radius - 11, 7, 0, Math.PI * 2);`. Step badge radius 7px.

#### `frontend/src/components/insights/OutbreakChart.tsx`
- L143: `r="3.5"`. Hover dot radius (compromised).
- L146: `strokeWidth="2"`. Hover dot outline.
- L151: `r="3.5"`. Hover dot radius (quarantined).
- L154: `strokeWidth="2"`
- (Cross-reference only: the 130px tooltip-width assumption at L207 is counted under Spacing.)

#### `frontend/src/app/globals.css` (outside `@theme`)
- L123: `width: 10px;`. Scrollbar.
- L124: `height: 10px;`. Scrollbar.

---

## Other

No arbitrary `rounded-[..]`, `shadow-[..]` or `z-[..]` classes exist anywhere in `src`.

#### `frontend/src/components/ui/States.tsx`
- L121: `"inline-block size-3.5 animate-spin rounded-full border-[1.5px] border-line-strong border-t-accent",`. Arbitrary border width on the spinner.
- L97: `via-white/[0.04]`. Arbitrary opacity (the color itself is counted under default-palette classes).
- L97: `motion-safe:[animation:shimmer_1.6s_infinite]`. Arbitrary animation property with a 1.6s duration.

#### `frontend/src/components/ui/Metric.tsx`
- L69: `"h-full rounded-full transition-[width] duration-300"`. Arbitrary `transition-property`, not a design value.
- L135: `"h-full transition-[width] duration-300"`. Same.

#### `frontend/src/components/shell/RunContextBar.tsx`
- L65: `className="h-full rounded-full bg-accent transition-[width] duration-300"`. Arbitrary `transition-property`.

#### `frontend/src/components/ui/Field.tsx`
- L180: `transition-[left] duration-150`. Arbitrary `transition-property`.

#### `frontend/src/components/graph/TopologyGraph.tsx`
- L308: `ctx.globalAlpha = dimmed ? 0.35 : 0.95;`. Opacity literals for the type ring.
- L381: `roundRect(ctx, box[0], box[1], box[2], box[3], 3);`. Canvas corner radius 3; this equals `--radius-xs`.

#### `frontend/src/components/insights/OutbreakChart.tsx`
- L127: `fillOpacity="0.85"`. Band opacity.
- L128: `fillOpacity="0.85"`

#### `frontend/src/app/globals.css` (outside `@theme`)
- L131: `border-radius: 999px;`. Scrollbar thumb; literal rather than a radius token.
- L163–L176: `@keyframes pulse-ring { … box-shadow: 0 0 0 5px transparent; opacity: 0.7; … }`. Literal 5px spread and opacities. Note: `pulse-ring` is not used anywhere in `src`; `SeverityDot` uses `animate-ping`.

---

## Borderline / probably fine

### Type
- **`leading-4` next to `text-2xs` is redundant.** `text-2xs` already sets a 1rem line-height, so these 12 lines do nothing extra:
  - `frontend/src/components/ui/States.tsx` L62, L87
  - `frontend/src/components/ui/Metric.tsx` L48
  - `frontend/src/components/ui/Field.tsx` L32, L187
  - `frontend/src/components/shell/AppShell.tsx` L87
  - `frontend/src/components/run/RunConfigurator.tsx` L208, L396
  - `frontend/src/components/insights/WorkflowTracker.tsx` L58
  - `frontend/src/components/insights/SecurityMetrics.tsx` L157
  - `frontend/src/components/insights/MetricsComparison.tsx` L82
  - `frontend/src/components/insights/ArmStatusCard.tsx` L49
- **`leading-5`/`leading-6` override the token line-heights.** These use Tailwind's spacing scale, not arbitrary values, but they bypass the line-height paired with each text size:
  - `text-xs leading-5` turns 1.125rem into 1.25rem:
    - `frontend/src/components/ui/States.tsx` L35, L73
    - `frontend/src/components/shell/AppShell.tsx` L158
    - `frontend/src/components/run/RunConfigurator.tsx` L112, L162
    - `frontend/src/components/graph/TopologyWorkspace.tsx` L213, L236
  - `text-sm leading-6` turns 1.25rem into 1.5rem:
    - `frontend/src/components/insights/FindingsList.tsx` L56
    - `frontend/src/app/page.tsx` L257
- **`tracking-tight` comes from Tailwind's default tracking scale.** The project defines no tracking token apart from `.eyebrow`. It appears on 6 lines:
  - `frontend/src/components/ui/Metric.tsx` L39
  - `frontend/src/components/insights/Panels.tsx` L28
  - `frontend/src/components/shell/AppShell.tsx` L33, L156
  - `frontend/src/components/shell/RunContextBar.tsx` L43
  - `frontend/src/app/page.tsx` L254
- **`frontend/src/app/globals.css` L145 `letter-spacing: 0.08em;` and L147 `font-weight: 500;`.** These are inside `.eyebrow`, so they *are* the component token's definition.
- **`font-medium`/`font-semibold` are used throughout.** These are Tailwind default weights; the project defines no weight tokens.

### Colors
- **The keywords `transparent` and `currentColor` are not palette colors:**
  - `frontend/src/components/ui/Button.tsx` L19: `border-transparent bg-transparent`
  - `frontend/src/components/insights/WorkflowTracker.tsx` L34: `bg-transparent`
  - `frontend/src/components/run/ReplayTransport.tsx` L87: `bg-transparent`
  - `frontend/src/components/graph/GraphLegend.tsx` L132: `bg-transparent`
  - `frontend/src/components/graph/GraphLegend.tsx` L26: `color = "currentColor"`
  - `frontend/src/components/ui/States.tsx` L97: `from-transparent … to-transparent`
  - `frontend/src/app/globals.css` L118, L129, L156, L159, L169, L173
  - `frontend/src/components/ui/icons.tsx` L16, L86, L176, L180–L182, L185: `currentColor`
- **`frontend/src/app/globals.css` L157–L158 use `black` in `mask-image`.** It only acts as an alpha mask, so the color itself has no effect.
- **`frontend/src/components/graph/TopologyGraph.tsx` L265 builds a color string at runtime:** ``return `rgb(${r}, ${g}, ${b})`;``. It is not a literal; the hardcoded part is the canvas mix on L262–L264.

### Sizing / geometry
- **Hairlines from Tailwind's `px` scale or a 1-unit stroke:**
  - `frontend/src/components/graph/GraphLegend.tsx` L84 `w-px` and L136 `h-px`
  - `frontend/src/components/ui/Metric.tsx` L129 `gap-px`
  - `frontend/src/components/insights/OutbreakChart.tsx` L123 and L138 `strokeWidth="1"`
- **Intrinsic geometry of icons and glyphs:**
  - `frontend/src/components/ui/icons.tsx`:
    - L12–L14: `width="16" height="16" viewBox="0 0 16 16"`
    - L17: `strokeWidth="1.35"`
    - L92: `strokeWidth="1.8"`
    - L167–L169: 22×22
    - L177: `strokeWidth="1.3"`
    - L186: `strokeWidth="1.15"`
  - `frontend/src/components/graph/GraphLegend.tsx`:
    - L32: `strokeWidth: 1.3`
    - L34: `<svg width="14" height="14" viewBox="0 0 14 14"`
    - L35–L41: shape paths
- **Opacity inside icons:** `frontend/src/components/ui/icons.tsx` L53 `opacity=".95"`, L181–L182 `opacity=".55"`, L188 `opacity=".75"`.
- **Data-driven inline widths** set the percentage width of progress and meter bars:
  - `frontend/src/components/run/ReplayTransport.tsx` L77
  - `frontend/src/components/shell/RunContextBar.tsx` L66
  - `frontend/src/components/ui/Metric.tsx` L70, L136
- **`frontend/src/app/globals.css` L106–L107 focus ring:** `outline: 2px solid var(--color-accent);` / `outline-offset: 1px;`.
- **`frontend/src/app/globals.css` L188–L190 reduced-motion overrides:** `0.01ms`.
- **Named container widths** come from Tailwind defaults; the project defines no container tokens:
  - `frontend/src/components/ui/States.tsx` L35 `max-w-sm`
  - `frontend/src/components/insights/SecurityMetrics.tsx` L157 `max-w-md`
  - `frontend/src/components/insights/MetricsComparison.tsx` L82 `max-w-lg`
  - `frontend/src/components/shell/AppShell.tsx` L158 `max-w-3xl`
  - `frontend/src/app/page.tsx` L249 `max-w-3xl`, L257 `max-w-2xl`
- **Renderer camera, culling and DPR settings in `frontend/src/components/graph/TopologyGraph.tsx`.** These are not visual tokens:
  - L141 `minCameraRatio: 0.15`
  - L142 `maxCameraRatio: 6`
  - L197 `ratio: 1.22`
  - L272 DPR cap `2`
  - L297 off-screen cull margin of `40`
- **Sigma `zIndex` draw order in `frontend/src/components/graph/TopologyGraph.tsx`** (canvas/WebGL ordering, not CSS z-index): L116, L152, L161, L167.
- **`frontend/src/components/graph/TopologyGraph.tsx` L425–L462 `traceShape`:** shape-proportion multipliers such as `r * 0.85` and `r * 1.1`.
- **Graph-unit layout radii in `frontend/src/lib/graph/layout.ts`.** These are normalized to the unit disc, not pixels:
  - L19–L23: `PLANE_RADIUS` 1.3/1.56/1.84
  - L43: radius `1`
  - L116: fallback `1.4`
  - L128: `2.1`

### Other
- **`frontend/src/components/run/ReplayTransport.tsx` L88–L92** use arbitrary *variant* selectors (`[&::-moz-range-thumb]:…`, `[&::-webkit-slider-thumb]:…`). The values they apply are all tokens: `size-3`, `bg-fg`, `shadow-panel`.
- **Motion durations** use Tailwind defaults; there are no project motion tokens. 15 uses across 10 files:
  - `duration-100`: `frontend/src/components/insights/WorkflowTracker.tsx` L31, `frontend/src/components/run/RunConfigurator.tsx` L100, `frontend/src/components/shell/AppShell.tsx` L54, `frontend/src/components/ui/Button.tsx` L11, L111, `frontend/src/components/ui/Field.tsx` L9, L158, L221, `frontend/src/components/graph/GraphLegend.tsx` L129
  - `duration-300`: `frontend/src/components/shell/RunContextBar.tsx` L65, `frontend/src/components/ui/Metric.tsx` L69, L135
  - `duration-150`: `frontend/src/components/ui/Field.tsx` L173, L180
  - `duration-75`: `frontend/src/components/ui/Table.tsx` L64
