export default function TenderPage() {
  return (
    <main className='mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-4 py-16'>
      <header className='space-y-2'>
        <h1 className='text-3xl font-semibold tracking-tight'>New Tender Intake</h1>
        <p className='text-muted-foreground'>
          Drop in the tender documents (RFP, BOQ, annexures) and plug this page into your preferred ingestion pipeline.
        </p>
      </header>

      <section className='rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground'>
        <p>Upload widget goes here when you connect to your backend.</p>
        <p className='mt-2 text-xs'>For now this is a placeholder so you can wire up your own form or drag-and-drop flow.</p>
      </section>

      <section className='space-y-2 text-sm text-muted-foreground'>
        <p>Suggested next steps:</p>
        <ul className='list-disc space-y-1 pl-5'>
          <li>Send files to an ingestion API or Cloud Storage bucket.</li>
          <li>Trigger AI extraction/analysis jobs.</li>
          <li>Redirect to the validation page once processing completes.</li>
        </ul>
      </section>
    </main>
  );
}

