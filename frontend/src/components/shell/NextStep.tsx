import Link from "next/link";

import { nextStep, WORKFLOW } from "@/components/shell/nav";
import { ButtonLink } from "@/components/ui/Button";
import { IconArrowRight } from "@/components/ui/icons";

/** Header action pointing at the next workflow step — always in view. */
export function NextStepButton({ from }: { from: string }) {
  const next = nextStep(from);
  if (!next) return null;
  return (
    <ButtonLink href={next.href} size="sm">
      Next: {next.label}
      <IconArrowRight className="size-3.5" />
    </ButtonLink>
  );
}

/** The end of a step's screen: where to go once you have read it. */
export function NextStepCard({ from }: { from: string }) {
  const next = nextStep(from);
  if (!next) return null;
  return (
    <Link
      href={next.href}
      className="group flex items-center justify-between gap-4 rounded-lg border border-line bg-raised px-4 py-3 shadow-panel transition-colors duration-100 hover:border-line-strong"
    >
      <span className="min-w-0">
        <span className="eyebrow block">
          Next · step {next.step} of {WORKFLOW.length}
        </span>
        <span className="block text-sm font-medium text-fg">{next.label}</span>
        <span className="block text-xs text-fg-muted">{next.summary}</span>
      </span>
      <IconArrowRight className="size-4 shrink-0 text-fg-subtle transition-colors group-hover:text-fg" />
    </Link>
  );
}
