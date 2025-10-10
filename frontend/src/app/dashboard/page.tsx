export default function DashboardPage() {
  return (
    <main className='mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-4 py-16'>
      <header className='space-y-2'>
        <h1 className='text-3xl font-semibold tracking-tight'>Tender Dashboard</h1>
        <p className='text-muted-foreground'>
          This page is ready for your reporting widgets—populate it with tables, charts, or timeline views from your data source.
        </p>
      </header>

      <section className='grid gap-4 md:grid-cols-2'>
        <div className='rounded-lg border border-border bg-card p-6 shadow-sm'>
          <p className='text-sm text-muted-foreground'>Add summary metrics here.</p>
        </div>
        <div className='rounded-lg border border-border bg-card p-6 shadow-sm'>
          <p className='text-sm text-muted-foreground'>Show upcoming deadlines or tasks.</p>
        </div>
      </section>

      <section className='rounded-lg border border-border bg-card p-6 shadow-sm'>
        <p className='text-sm text-muted-foreground'>Hook this area up to your preferred table or chart component to list tenders.</p>
      </section>
    </main>
  );
}

