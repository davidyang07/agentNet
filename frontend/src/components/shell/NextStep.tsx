import { nextStep } from "@/components/shell/nav";
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
