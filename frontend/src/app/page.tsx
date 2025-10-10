import Link from "next/link";

const ctaClasses =
  "rounded-md bg-slate-900 px-5 py-3 text-center text-sm font-medium text-white transition hover:bg-slate-700";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-8 px-4 py-16">
      <section>
        <h1 className="text-4xl font-semibold tracking-tight">Tender Automation Workspace</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          Use these tools to upload new tenders, review AI results, and follow progress through delivery.
        </p>
      </section>

      <nav className="flex flex-col gap-4 sm:flex-row">
        <Link href="/tender" className={ctaClasses}>
          Start a New Tender
        </Link>
        <Link href="/valid" className={ctaClasses}>
          Validate AI Output
        </Link>
        <Link href="/dashboard" className={ctaClasses}>
          View Dashboard
        </Link>
      </nav>

      <section className="space-y-3 text-sm text-muted-foreground">
        <p>
          This UI is intentionally lightweight; connect it to your own APIs or workflows to power the tender lifecycle.
        </p>
        <p>
          Need a different page? Add it under <code className="rounded bg-muted px-1 py-0.5 text-xs">frontend/src/app</code>
          and link it here.
        </p>
      </section>
    </main>
  );
}

