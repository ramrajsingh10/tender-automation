export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background text-foreground">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-sm text-muted-foreground">
        Check the URL or head back to the intake workspace.
      </p>
      <a
        href="/tender"
        className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted"
      >
        Return to intake
      </a>
    </main>
  );
}
