#!/usr/bin/env node
// Screenshots one URL at desktop (1440px) and mobile (390px) widths.
//
//   node scripts/screenshot.mjs <url> <out-dir> [name] [options]
//
// Writes <out-dir>/<name>.png (1440×900) and <out-dir>/<name>-390.png (390×844).
// <name> defaults to the URL's last path segment ("index" for "/").
//
// Options:
//   --full-page            capture the whole page, not just the viewport — including
//                          content inside an app-shell scroll container (<main>)
//   --selector <css>       capture only the first element matching <css>
//   --wait <ms>            settle time after load, for late fonts/data (default 1500)
//   --hide <css>           hide matching elements before capturing, e.g. a cookie
//                          banner over the content (repeatable)
//   --session <key=value>  seed sessionStorage before the page loads (repeatable).
//                          The console re-adopts the run in
//                          `agentshield.activeExperimentId`, so
//                          `--session agentshield.activeExperimentId=<id>` opens
//                          any run-dependent screen with that run active.
//
// Playwright is a frontend dev dependency (resolved from frontend/node_modules).
// Install its browser once with `cd frontend && npx playwright install chromium`;
// CHROMIUM_PATH overrides the executable where a Chromium is already installed.

import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const { chromium } = createRequire(path.join(repoRoot, "frontend", "package.json"))("playwright");

const VIEWPORTS = [
  { suffix: "", width: 1440, height: 900, isMobile: false },
  { suffix: "-390", width: 390, height: 844, isMobile: true },
];

const USAGE = "usage: node scripts/screenshot.mjs <url> <out-dir> [name] " +
  "[--full-page] [--selector <css>] [--wait <ms>] [--hide <css>]... [--session <key=value>]...";

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    "full-page": { type: "boolean", default: false },
    selector: { type: "string" },
    wait: { type: "string", default: "1500" },
    hide: { type: "string", multiple: true, default: [] },
    session: { type: "string", multiple: true, default: [] },
    help: { type: "boolean", short: "h", default: false },
  },
});

if (values.help || positionals.length < 2 || positionals.length > 3) {
  console.error(USAGE);
  process.exit(values.help ? 0 : 2);
}

const [url, outDir, nameArg] = positionals;
const name = nameArg ?? (new URL(url).pathname.split("/").filter(Boolean).pop() || "index");
const waitMs = Number(values.wait);
const session = values.session.map((pair) => {
  const eq = pair.indexOf("=");
  if (eq < 1) {
    console.error(`--session expects key=value, got "${pair}"\n${USAGE}`);
    process.exit(2);
  }
  return [pair.slice(0, eq), pair.slice(eq + 1)];
});

// Overflow of the page's main scroller: the largest outermost vertical scroll
// container. Ones nested inside it (an event log) are panels meant to scroll in
// place, and so is a smaller sibling (a sidebar).
const innerOverflow = (page) =>
  page.evaluate(() => {
    const scrolls = (el) => /(auto|scroll)/.test(getComputedStyle(el).overflowY);
    const nested = (el) => {
      for (let up = el.parentElement; up; up = up.parentElement) if (scrolls(up)) return true;
      return false;
    };
    let main = null;
    for (const el of document.querySelectorAll("*")) {
      if (!scrolls(el) || nested(el)) continue;
      const area = el.clientWidth * el.clientHeight;
      if (area > 0 && (!main || area > main.clientWidth * main.clientHeight)) main = el;
    }
    return main ? Math.max(0, main.scrollHeight - main.clientHeight) : 0;
  });

// An app shell sized to the viewport (h-dvh + an overflow-y-auto <main>)
// scrolls inside <main>, so Playwright's fullPage stops at the viewport. Grow
// the viewport until <main> no longer overflows, stopping if growing stops
// helping (content that is itself sized to the viewport).
async function growToContent(page) {
  let overflow = await innerOverflow(page);
  while (overflow > 1) {
    const before = page.viewportSize();
    await page.setViewportSize({ width: before.width, height: before.height + overflow });
    await page.waitForTimeout(300);
    const next = await innerOverflow(page);
    if (next >= overflow) {
      await page.setViewportSize(before);
      await page.waitForTimeout(300);
      return;
    }
    overflow = next;
  }
}

await mkdir(outDir, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
let captured = 0;

try {
  for (const viewport of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      isMobile: viewport.isMobile,
      hasTouch: viewport.isMobile,
      deviceScaleFactor: 1,
    });
    if (session.length > 0) {
      await context.addInitScript((entries) => {
        try {
          for (const [key, value] of entries) window.sessionStorage.setItem(key, value);
        } catch {
          // Cross-origin frames have no access to the top page's storage.
        }
      }, session);
    }

    const page = await context.newPage();
    await page.goto(url, { waitUntil: "load", timeout: 60_000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(waitMs);
    for (const css of values.hide) {
      await page.addStyleTag({ content: `${css} { visibility: hidden !important; }` });
    }

    const file = path.join(outDir, `${name}${viewport.suffix}.png`);
    const options = { path: file, animations: "disabled" };
    if (values.selector) {
      // Layouts often hide an element at one width (a desktop-only panel), so
      // a missing match skips that width rather than failing the whole run.
      const target = page.locator(values.selector).first();
      if (await target.isVisible()) {
        // Below-the-fold content often lazy-loads or animates in on scroll.
        await target.scrollIntoViewIfNeeded();
        await page.waitForTimeout(waitMs);
        await target.screenshot(options);
      } else {
        console.error(`skipped ${viewport.width}px: "${values.selector}" is not visible`);
        await context.close();
        continue;
      }
    } else {
      if (values["full-page"]) await growToContent(page);
      await page.screenshot({ ...options, fullPage: values["full-page"] });
    }
    console.log(file);
    captured++;
    await context.close();
  }
} finally {
  await browser.close();
}

if (captured === 0) process.exit(1);
