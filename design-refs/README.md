# Design references

Layout references for the UI redesign. `CLAUDE.md` § UI rules says how to use them. Match their
density and hierarchy, but take every token from `DESIGN.md`, never from these images.

`<screen>.png` is the 1440px reference. `<screen>-390.png` is the 390px one, where the source has
a real mobile layout. `before/` holds the console as it was before the redesign, captured from a
live "Security-plane assault" run. `token-audit.md` lists every colour, font and spacing value the
frontend hardcodes instead of taking from a shared token.

| File | Source | Shows |
|---|---|---|
| `shell.png`, `shell-390.png` | linear.app (homepage hero) | App shell: sidebar, issue view, properties rail, agent panel |
| `list.png` | linear.app (homepage, "Build, review, and ship") | Grouped issue list. Desktop only: Linear hides it on mobile |
| `topology.png` | wiz.io/solutions/ai-spm ("Attack path analysis extended to AI") | Security Graph attack path from Internet to an AI training bucket |
| `activity.png` | axiom.co/docs/query-data/stream ("Event stream") | Log/event stream: time column, key-value rows, filter bar |
| `remediation.png`, `remediation-390.png` | github.com/expressjs/express/pull/7459/files | PR "Files changed": file tree, hunks, line-level diff |

To re-capture (from the repo root; see `scripts/screenshot.mjs` for setup):

```sh
node scripts/screenshot.mjs https://linear.app design-refs shell --wait 9000 \
  --selector '[aria-label^="A screenshot of the Linear app"]'
node scripts/screenshot.mjs https://linear.app design-refs list --wait 3000 \
  --selector '[class*="_listPanel"]' --hide '[class*="_diffLayer"]'
node scripts/screenshot.mjs https://www.datocms-assets.com/75231/1699868014-ai-attack-path-analysis.jpg \
  design-refs topology --selector img
node scripts/screenshot.mjs https://axiom.co/docs/doc-assets/shots/event-stream-1.png \
  design-refs activity --selector img
node scripts/screenshot.mjs https://github.com/expressjs/express/pull/7459/files design-refs remediation --wait 4000
```

`topology` and `activity` are static product screenshots served as images, so they have no
390px version. The Linear selectors depend on class names that Linear may change.
