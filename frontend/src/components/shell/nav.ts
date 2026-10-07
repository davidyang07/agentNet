/**
 * The assessment workflow, as the navigation itself. Each step is one screen
 * with one job, in the order an operator does them; every piece of
 * information lives on exactly one of these screens.
 */
export type WorkflowStep = {
  href: string;
  /** 1-based position in the workflow. */
  step: number;
  label: string;
  /** What the operator does on this screen, in one line. */
  summary: string;
  /** Needs an active run to show anything. */
  needsRun: boolean;
};

export const WORKFLOW: readonly WorkflowStep[] = [
  {
    href: "/setup",
    step: 1,
    label: "Set up",
    summary: "Choose the system and the attacks, then launch.",
    needsRun: false,
  },
  {
    href: "/watch",
    step: 2,
    label: "Watch",
    summary: "See compromise spread through the graph, live.",
    needsRun: true,
  },
  {
    href: "/results",
    step: 3,
    label: "Results",
    summary: "How far it got, and what the defense cost.",
    needsRun: true,
  },
  {
    href: "/fix",
    step: 4,
    label: "Fix & re-test",
    summary: "Apply a fix and prove it changes the outcome.",
    needsRun: true,
  },
];

/** Outside the workflow: every persisted run, for replay and comparison. */
export const ARCHIVE = {
  href: "/history",
  label: "Runs",
  summary: "Every past run — replay it, or compare two.",
} as const;

export function workflowStep(href: string): WorkflowStep {
  const step = WORKFLOW.find((s) => s.href === href);
  if (!step) throw new Error(`${href} is not a workflow step`);
  return step;
}

export function nextStep(href: string): WorkflowStep | null {
  return WORKFLOW[workflowStep(href).step] ?? null;
}

/** "Step 2 of 4" — the eyebrow every workflow screen opens with. */
export function stepLabel(href: string): string {
  return `Step ${workflowStep(href).step} of ${WORKFLOW.length}`;
}

/** Prefix match so `/history/<id>` still highlights "Runs". */
export function isActivePath(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
