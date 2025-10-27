'use client';

import Link from "next/link";
import { useEffect } from "react";

export default function GlobalError({
  reset,
}: {
  reset: () => void;
}) {
  useEffect(() => {
    console.error("App-level error boundary triggered");
  }, []);

  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background text-foreground">
        <h1 className="text-2xl font-semibold">Something went wrong</h1>
        <p className="text-sm text-muted-foreground">
          Please retry the action or return to the intake dashboard.
        </p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => reset()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Try again
          </button>
          <Link
            href="/tender"
            className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted"
          >
            Go to intake
          </Link>
        </div>
      </body>
    </html>
  );
}
