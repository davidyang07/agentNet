"use client"; // Error boundaries must be Client Components.

import { useEffect } from "react";

import { Button, ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/States";

/**
 * The landing page, or the console shell itself, threw while rendering.
 * Console screens have their own boundary inside the shell, so this only
 * catches what sits above them.
 */
export default function AppError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-full items-start justify-center bg-canvas p-6">
      <ErrorState
        className="w-full max-w-xl"
        title="AgentShield hit an error"
        detail={error.digest ? `${error.message} (${error.digest})` : error.message}
        action={
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => retry()}>
              Try again
            </Button>
            <ButtonLink size="sm" variant="ghost" href="/">
              Home
            </ButtonLink>
          </div>
        }
      />
    </div>
  );
}
