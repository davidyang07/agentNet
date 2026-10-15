"use client"; // Error boundaries must be Client Components.

import { useEffect } from "react";

import { Button, ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/States";

/**
 * A screen that throws while rendering falls back to this, inside the console
 * shell — the sidebar, run bar and the live run keep going — rather than
 * blanking the whole page.
 */
export default function ConsoleError({
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
    <div className="p-4 lg:p-5">
      <ErrorState
        title="This screen hit an error"
        detail={error.digest ? `${error.message} (${error.digest})` : error.message}
        action={
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => retry()}>
              Try again
            </Button>
            <ButtonLink size="sm" variant="ghost" href="/setup">
              Back to Set up
            </ButtonLink>
          </div>
        }
      />
    </div>
  );
}
