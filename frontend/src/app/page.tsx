"use client";

import Image from "next/image";
import Link from "next/link";

import { WORKFLOW } from "@/components/shell/nav";
import { ButtonLink } from "@/components/ui/Button";
import { BrandMark, IconArrowRight } from "@/components/ui/icons";
import { useExperiment } from "@/lib/experiment/ExperimentProvider";
import { shortId } from "@/lib/format";

// A live "Security-plane assault" run (seed 42), captured from the console
// itself. Re-capture it after a visible change to Watch — see
// design-refs/README.md.
import watchShot from "./_landing/hero-watch.jpg";

/**
 * The front door: what AgentShield does, the four steps, and the way into the
 * console — all on one desktop screen. Plain statements only, no claims the
 * console cannot back (CLAUDE.md › UI rules).
 */
export default function LandingPage() {
  const { control, hydrating } = useExperiment();
  const activeRun = !hydrating ? control.experimentId : null;

  return (
    <div className="flex min-h-full flex-col bg-canvas">
      <header className="border-b border-line">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 lg:px-6">
          <Link href="/" className="flex items-center gap-2 text-fg">
            <BrandMark className="size-5" />
            <span className="text-sm font-semibold">AgentShield</span>
          </Link>
          <nav aria-label="Primary" className="flex items-center gap-1">
            <Link
              href="/history"
              className="rounded-md px-2.5 py-1.5 text-sm font-medium text-fg-muted transition-colors hover:text-fg"
            >
              Runs
            </Link>
            <ButtonLink href={activeRun ? "/watch" : "/setup"} size="sm">
              Open console
            </ButtonLink>
          </nav>
        </div>
      </header>

      <main className="flex flex-1 flex-col">
        <section className="mx-auto grid w-full max-w-6xl flex-1 content-center items-center gap-10 px-4 py-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-12 lg:px-6 lg:py-16">
          <div>
            <h1 className="text-balance text-4xl font-semibold text-fg lg:text-5xl">
              Measure how far one compromised agent spreads.
            </h1>
            <p className="mt-4 text-pretty text-lg text-fg-muted">
              Model a multi-agent system as a typed security graph, attack it reproducibly, and
              re-test the fixes it recommends.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-2">
              {activeRun ? (
                <>
                  <ButtonLink href="/watch" variant="primary">
                    Resume run {shortId(activeRun)}
                    <IconArrowRight className="size-3.5" />
                  </ButtonLink>
                  <ButtonLink href="/setup">Start a new assessment</ButtonLink>
                </>
              ) : (
                <>
                  <ButtonLink href="/setup" variant="primary">
                    Start an assessment
                    <IconArrowRight className="size-3.5" />
                  </ButtonLink>
                  <ButtonLink href="/history">Open past runs</ButtonLink>
                </>
              )}
            </div>
          </div>

          <figure className="overflow-hidden rounded-lg border border-line bg-surface p-1.5 shadow-panel">
            <Image
              src={watchShot}
              alt="The Watch step: the security graph coloured by compromise, the outbreak curve, and live events."
              priority
              sizes="(min-width: 1024px) 620px, 100vw"
              className="h-auto w-full rounded-md"
            />
          </figure>
        </section>

        <section aria-label="How an assessment works" className="border-t border-line">
          <ol className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-8 sm:grid-cols-2 lg:grid-cols-4 lg:px-6">
            {WORKFLOW.map((step) => (
              <li key={step.href} className="flex items-start gap-3">
                <span
                  aria-hidden
                  className="flex size-6 shrink-0 items-center justify-center rounded-full border border-line-strong text-xs font-semibold text-fg-muted"
                >
                  {step.step}
                </span>
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-fg">{step.label}</h2>
                  <p className="mt-0.5 text-sm text-fg-muted">{step.summary}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer className="border-t border-line">
        <p className="mx-auto max-w-6xl px-4 py-5 text-xs text-fg-subtle lg:px-6">
          Deterministic simulation. Results are reproducible from{" "}
          <span className="font-mono">(seed, config)</span> — not real-world security evidence.
        </p>
      </footer>
    </div>
  );
}
