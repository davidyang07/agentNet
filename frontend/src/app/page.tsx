"use client";

import Image, { type StaticImageData } from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

import { METRIC_DESCRIPTORS } from "@/components/insights/SecurityMetrics";
import { WORKFLOW } from "@/components/shell/nav";
import { ButtonLink } from "@/components/ui/Button";
import { BrandMark, IconArrowRight } from "@/components/ui/icons";
import { useExperiment } from "@/lib/experiment/ExperimentProvider";
import { shortId } from "@/lib/format";
import { SCENARIOS } from "@/lib/vocabulary";

// Product screenshots, captured from a live "Security-plane assault" run
// (seed 42) in the console itself. Re-capture them after a visible change to
// these screens — see design-refs/README.md.
import heroShot from "./_landing/hero-watch.jpg";
import setupShot from "./_landing/step-setup.jpg";
import watchShot from "./_landing/step-watch.jpg";
import resultsShot from "./_landing/step-results.jpg";
import fixShot from "./_landing/step-fix.jpg";

const STEP_DETAIL: Record<string, { text: string; shot: StaticImageData }> = {
  "/setup": {
    text: "Pick a preset or describe the system — agent count, topology, tools, credentials, sentinels — and the attacks to run against it.",
    shot: setupShot,
  },
  "/watch": {
    text: "The security graph, coloured by each node's state as compromise spreads, with the outbreak curve under it and every event beside it. Select a node to trace it back to patient zero.",
    shot: watchShot,
  },
  "/results": {
    text: "Compromise fraction, blast radius, retained utility and security-plane integrity — then every metric with the definition it is computed from.",
    shot: resultsShot,
  },
  "/fix": {
    text: "Each finding is a configuration change. Re-testing runs it before and after from the same seed, so the difference is the fix's doing; a defense on/off check does the same for the defense itself.",
    shot: fixShot,
  },
};

const LIMITS = [
  "Results are simulation evidence, reproducible from (seed, config) — not evidence about a deployed system.",
  "Agents are deterministic mocks by default; LLM-backed agents need an OpenAI-compatible model endpoint.",
  "A single seed is one sample. Re-test a fix across several seeds before treating it as robust.",
];

/**
 * The front door: what AgentShield does, how an assessment runs, and the way
 * into the console. Plain statements only — no claims the console cannot back
 * (CLAUDE.md › UI rules). Layout after design-refs/landing.png.
 */
export default function LandingPage() {
  const { control, hydrating } = useExperiment();
  const activeRun = !hydrating ? control.experimentId : null;

  return (
    <div className="min-h-full bg-canvas">
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

      <main>
        <section className="mx-auto max-w-6xl px-4 pb-12 pt-16 lg:px-6 lg:pb-16 lg:pt-24">
          <h1 className="max-w-3xl text-4xl font-semibold text-fg lg:text-5xl">
            Measure how far one compromised agent spreads.
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-fg-muted">
            AgentShield models a multi-agent system — agents, tools, credentials, resources and the
            sentinels watching them — as a typed security graph, runs reproducible attacks against
            it, and re-tests the fixes it recommends.
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

          <figure className="mt-12 overflow-hidden rounded-lg border border-line bg-surface p-1.5 shadow-panel lg:mt-16">
            <Image
              src={heroShot}
              alt="The Watch step: the security graph coloured by compromise, the outbreak curve, and live events."
              priority
              sizes="(min-width: 1152px) 1128px, 100vw"
              className="h-auto w-full rounded-md"
            />
          </figure>
        </section>

        <section aria-labelledby="how" className="border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-14 lg:px-6 lg:py-20">
            <h2 id="how" className="text-2xl font-semibold text-fg">
              How an assessment works
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-fg-muted">
              Four steps, in order. The console&apos;s sidebar is this list.
            </p>

            <ol className="mt-10 grid gap-x-6 gap-y-10 md:grid-cols-2">
              {WORKFLOW.map((step) => {
                const detail = STEP_DETAIL[step.href];
                return (
                  <li key={step.href} className="flex flex-col gap-4">
                    <div className="flex items-start gap-3">
                      <span
                        aria-hidden
                        className="mt-px flex size-6 shrink-0 items-center justify-center rounded-full border border-line-strong text-xs font-semibold text-fg-muted"
                      >
                        {step.step}
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-base font-semibold text-fg">{step.label}</h3>
                        <p className="mt-1 text-sm text-fg-muted">{detail.text}</p>
                      </div>
                    </div>
                    <div className="overflow-hidden rounded-lg border border-line bg-surface p-1 shadow-panel">
                      <Image
                        src={detail.shot}
                        alt={`The ${step.label} step.`}
                        sizes="(min-width: 768px) 540px, 100vw"
                        className="h-auto w-full rounded-md"
                      />
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        </section>

        <section aria-label="Scope" className="border-t border-line">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 lg:grid-cols-3 lg:px-6 lg:py-20">
            <ScopeList title="What it models">
              <li>Agents, tools and MCP servers, credentials, resources and sentinels, as typed nodes.</li>
              <li>Communication, trust, access, monitoring and quarantine-authority edges.</li>
              <li>{SCENARIOS.length} attack scenarios: {SCENARIOS.map((s) => s.label.toLowerCase()).join(", ")}.</li>
            </ScopeList>
            <ScopeList title="What it measures">
              {METRIC_DESCRIPTORS.map((metric) => (
                <li key={metric.key}>{metric.label}</li>
              ))}
            </ScopeList>
            <ScopeList title="Limits">
              {LIMITS.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ScopeList>
          </div>
        </section>

        <section className="border-t border-line">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-10 lg:px-6">
            <p className="text-sm text-fg-muted">
              Start from a preset and change what you need. Every run is kept under Runs.
            </p>
            <ButtonLink href={activeRun ? "/watch" : "/setup"} variant="primary">
              {activeRun ? "Resume run" : "Start an assessment"}
              <IconArrowRight className="size-3.5" />
            </ButtonLink>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-xs text-fg-subtle lg:px-6">
          <span className="flex items-center gap-2">
            <BrandMark className="size-4" />
            AgentShield — deterministic adversarial simulation for multi-agent systems.
          </span>
          <span className="flex items-center gap-4">
            <Link href="/setup" className="transition-colors hover:text-fg">
              Set up
            </Link>
            <Link href="/history" className="transition-colors hover:text-fg">
              Runs
            </Link>
          </span>
        </div>
      </footer>
    </div>
  );
}

function ScopeList({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-fg">{title}</h2>
      <ul className="mt-3 flex list-disc flex-col gap-1.5 pl-4 text-sm text-fg-muted marker:text-fg-subtle">
        {children}
      </ul>
    </div>
  );
}
