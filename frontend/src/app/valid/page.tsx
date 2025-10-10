export default function ValidationPage() {
  return (
    <main className='mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-4 py-16'>
      <header className='space-y-2'>
        <h1 className='text-3xl font-semibold tracking-tight'>AI Validation Checklist</h1>
        <p className='text-muted-foreground'>
          Review the results the AI produced for a tender before you publish them to the dashboard.
        </p>
      </header>

      <section className='rounded-lg border border-border bg-card p-6 shadow-sm'>
        <p className='text-sm text-muted-foreground'>
          Replace this section with your own validation UI. It might contain extracted metadata, compliance questions, or a
          compare view against the source documents.
        </p>
      </section>

      <section className='rounded-lg border border-border bg-card p-6 shadow-sm'>
        <h2 className='text-lg font-medium'>What to build here</h2>
        <ul className='mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground'>
          <li>Editable fields for key tender attributes.</li>
          <li>A task list for the business analyst to confirm requirements.</li>
          <li>Buttons that call your backend to approve or reject the tender.</li>
        </ul>
      </section>
    </main>
  );
}

