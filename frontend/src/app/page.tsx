import Link from "next/link";
import { MetricBadge } from "@/components/ui/metric-badge";
import { StatusPill } from "@/components/ui/status-pill";

const flowCards = [
  {
    step: "Step 1",
    title: "Upload the tender bundle",
    body: "Drag and drop the source files or import from Google Cloud Storage. We automatically chunk, embed, and prepare the corpus.",
    cta: { href: "/tender", label: "Start a tender" },
  },
  {
    step: "Step 2",
    title: "Validate AI responses",
    body: "Review the AI-generated answers, check supporting documents, and sign off on the tender for downstream automation.",
    cta: { href: "/tender", label: "Go to intake" },
  },
];

const recentActivity = [
  {
    id: "5ae8",
    label: "Metro Rail PMC",
    status: "Ready for review",
    href: "/tender",
  },
  {
    id: "a21e",
    label: "Healthcare RFP",
    status: "Playbook running",
    href: "/tender",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-16 px-6 py-16">
      <section className="overflow-hidden rounded-3xl bg-hero-gradient px-8 py-12 shadow-card">
        <div className="grid gap-10 md:grid-cols-[1.2fr_minmax(0,0.8fr)]">
          <div className="space-y-5">
            <StatusPill label="Automate tender analysis" variant="accent" />
            <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
              One workspace for uploading tenders and validating AI results
            </h1>
            <p className="text-lg text-foreground/80">
              Keep procurement teams aligned by letting Vertex RAG handle the heavy lifting—import, extract, validate, and ship
              results faster than ever.
            </p>
            <div className="flex flex-wrap items-center gap-4">
              <Link
                href="/tender"
                className="rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-card transition hover:bg-primary/90"
              >
                Start a tender
              </Link>
              <Link
                href="/dashboard"
                className="rounded-full border border-primary/40 px-6 py-3 text-sm font-semibold text-primary shadow-subtle transition hover:border-primary hover:bg-primary/10"
              >
                View dashboard
              </Link>
            </div>
          </div>
          <aside className="grid grid-cols-1 gap-6 rounded-2xl bg-surface/60 p-6 shadow-subtle backdrop-blur">
            <MetricBadge label="Tenders processed" value="128" trend="up" helperText="+12 this month" />
            <MetricBadge label="Average review time" value="18m" trend="neutral" helperText="Playbook to approval" />
            <MetricBadge label="Accuracy checks" value="97%" trend="up" helperText="Met reviewer expectations" />
          </aside>
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        {flowCards.map((card) => (
          <article
            key={card.step}
            className="flex h-full flex-col justify-between gap-6 rounded-2xl border border-border/70 bg-surface p-6 shadow-subtle transition hover:shadow-card"
          >
            <StatusPill label={card.step} variant="default" />
            <div className="space-y-3">
              <h2 className="text-2xl font-semibold text-foreground">{card.title}</h2>
              <p className="text-sm text-muted-foreground">{card.body}</p>
            </div>
            <Link
              href={card.cta.href}
              className="inline-flex w-fit items-center gap-2 text-sm font-semibold text-primary transition hover:text-primary/80"
            >
              {card.cta.label} →
            </Link>
          </article>
        ))}
      </section>

      <section className="grid gap-4 md:grid-cols-[minmax(0,0.6fr)_minmax(0,1fr)]">
        <div className="rounded-2xl border border-border/70 bg-surface p-6 shadow-subtle">
          <h3 className="text-base font-semibold text-foreground">Recent activity</h3>
          <p className="mt-1 text-sm text-muted-foreground">Jump back into tenders that need your attention.</p>
          <ul className="mt-4 space-y-3">
            {recentActivity.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 rounded-xl border border-transparent px-3 py-2 transition hover:border-primary/20 hover:bg-primary/5">
                <div>
                  <p className="text-sm font-semibold text-foreground">{item.label}</p>
                  <p className="text-xs text-muted-foreground">ID {item.id}</p>
                </div>
                <StatusPill label={item.status} variant={item.status.includes("Ready") ? "success" : "accent"} />
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-2xl border border-dashed border-border/70 bg-surface p-6 shadow-subtle">
          <h3 className="text-base font-semibold text-foreground">What’s next?</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Add more playbook questions or connect to downstream approvals once the validation workspace meets your needs.
          </p>
          <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>Expand the question library and map answers into Workfront or Jira.</li>
            <li>Automate reviewer notifications when a tender is ready to approve.</li>
            <li>Attach smoke test scripts so each tender ships with confidence data.</li>
          </ul>
        </div>
      </section>
    </main>
  );
}
