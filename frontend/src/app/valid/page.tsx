"use client";

import { useEffect, useMemo, useState } from "react";

interface TextAnchor {
  page?: number | string;
  snippet?: string;
}

interface Fact {
  id: string;
  factType: string;
  payload: Record<string, unknown>;
  confidence?: number;
  status?: string;
  decisionAt?: string;
  decisionNotes?: string | null;
  provenance?: { textAnchors: TextAnchor[] };
}

interface AnnexurePayload extends Record<string, unknown> {
  name?: string;
  pageRange?: {
    start?: number | string;
    end?: number | string;
  };
}

interface Annexure {
  id: string;
  annexureType: string;
  payload: AnnexurePayload;
  confidence?: number;
  status?: string;
  decisionAt?: string;
  decisionNotes?: string | null;
  provenance?: { textAnchors: TextAnchor[] };
}

function getTenderIdFromSearch(searchParams: URLSearchParams): string | null {
  return searchParams.get("tenderId");
}

let cachedBackendBaseUrl: string | null = null;

function getBackendBaseUrl(): string {
  if (cachedBackendBaseUrl) {
    return cachedBackendBaseUrl;
  }

  const candidates: Array<string | undefined> = [
    process.env.NEXT_PUBLIC_TENDER_BACKEND_URL,
    process.env.NEXT_PUBLIC_API_URL,
    typeof window !== "undefined" ? window.location.origin : undefined,
  ];
  const resolved = candidates.find(
    (value) => typeof value === "string" && value.trim().length > 0,
  );
  if (!resolved) {
    throw new Error(
      "Backend base URL is not configured. Set NEXT_PUBLIC_TENDER_BACKEND_URL or NEXT_PUBLIC_API_URL.",
    );
  }

  cachedBackendBaseUrl = resolved.replace(/\/+$/, "");
  return cachedBackendBaseUrl;
}

async function fetchJson<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const resolvedInput =
    typeof input === "string" && input.startsWith("/")
      ? `${getBackendBaseUrl()}${input}`
      : input;

  const response = await fetch(resolvedInput, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export default function ValidationPage() {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [annexures, setAnnexures] = useState<Annexure[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutating, setIsMutating] = useState<string | null>(null);

  const refreshData = async (id: string) => {
    const [factRes, annexureRes] = await Promise.all([
      fetchJson<{ items: Fact[] }>(`/api/dashboard/tenders/${id}/facts`),
      fetchJson<{ items: Annexure[] }>(
        `/api/dashboard/tenders/${id}/annexures`,
      ),
    ]);
    setFacts(factRes.items);
    setAnnexures(annexureRes.items);
  };

  const tenderId = useMemo(() => {
    if (typeof window === "undefined") return null;
    return getTenderIdFromSearch(new URLSearchParams(window.location.search));
  }, []);

  useEffect(() => {
    if (!tenderId) return;
    setIsLoading(true);
    setError(null);
    void (async () => {
      try {
        await refreshData(tenderId);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setIsLoading(false);
      }
    })();
  }, [tenderId]);

  const decideFact = async (
    factId: string,
    decision: "approved" | "rejected",
  ) => {
    if (!tenderId) return;
    setIsMutating(`fact:${factId}`);
    setError(null);
    try {
      await fetchJson(`/api/dashboard/facts/${factId}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      await refreshData(tenderId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsMutating(null);
    }
  };

  const decideAnnexure = async (
    annexureId: string,
    decision: "approved" | "rejected",
  ) => {
    if (!tenderId) return;
    setIsMutating(`annexure:${annexureId}`);
    setError(null);
    try {
      await fetchJson(`/api/dashboard/annexures/${annexureId}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      await refreshData(tenderId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsMutating(null);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 px-4 py-16">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">
          AI Validation Checklist
        </h1>
        <p className="text-muted-foreground">
          Review the results the AI produced for a tender before you publish
          them to the dashboard.
        </p>
        {!tenderId ? (
          <p className="text-sm text-destructive">
            Provide a tenderId query parameter to load data.
          </p>
        ) : null}
      </header>

      {error ? (
        <div className="rounded border border-destructive/60 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading data…</p>
      ) : null}

      <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <h2 className="text-lg font-medium">Extracted Facts</h2>
        {facts.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No facts available yet.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {facts.map((fact) => (
              <li
                key={fact.id}
                className="rounded border bg-background p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-semibold">{fact.factType}</p>
                    <p className="text-xs text-muted-foreground">
                      Confidence: {(fact.confidence ?? 0).toFixed(2)}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="block text-xs uppercase tracking-wide text-muted-foreground">
                      {fact.status ?? "pending"}
                    </span>
                    {fact.decisionAt ? (
                      <span className="block text-[10px] text-muted-foreground">
                        Decided {new Date(fact.decisionAt).toLocaleString()}
                      </span>
                    ) : null}
                  </div>
                </div>
                {fact.decisionNotes ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Notes: {fact.decisionNotes}
                  </p>
                ) : null}
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    onClick={() => decideFact(fact.id, "approved")}
                    disabled={isMutating === `fact:${fact.id}`}
                    className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => decideFact(fact.id, "rejected")}
                    disabled={isMutating === `fact:${fact.id}`}
                    className="rounded-md bg-destructive px-3 py-1 text-xs font-medium text-destructive-foreground transition hover:bg-destructive/80 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
                <pre className="mt-3 overflow-x-auto rounded bg-muted px-3 py-2 text-xs text-muted-foreground">
                  {JSON.stringify(fact.payload, null, 2)}
                </pre>
                {fact.provenance?.textAnchors?.length ? (
                  <div className="mt-3 rounded border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                    <p className="font-medium text-foreground">Provenance</p>
                    <ul className="mt-2 list-inside space-y-1">
                      {fact.provenance.textAnchors.map((anchor, index) => (
                        <li key={index}>
                          Page {anchor.page ?? "n/a"} —{" "}
                          {anchor.snippet ?? "snippet unavailable"}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <h2 className="text-lg font-medium">Annexures</h2>
        {annexures.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No annexure references found.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {annexures.map((annexure) => (
              <li
                key={annexure.id}
                className="rounded border bg-background p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-semibold">
                      {annexure.payload.name ?? annexure.annexureType}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Range:{" "}
                      {annexure.payload.pageRange
                        ? `Pages ${annexure.payload.pageRange.start}–${annexure.payload.pageRange.end}`
                        : "N/A"}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="block text-xs uppercase tracking-wide text-muted-foreground">
                      {annexure.status ?? "pending"}
                    </span>
                    {annexure.decisionAt ? (
                      <span className="block text-[10px] text-muted-foreground">
                        Decided {new Date(annexure.decisionAt).toLocaleString()}
                      </span>
                    ) : null}
                  </div>
                </div>
                {annexure.decisionNotes ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Notes: {annexure.decisionNotes}
                  </p>
                ) : null}
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    onClick={() => decideAnnexure(annexure.id, "approved")}
                    disabled={isMutating === `annexure:${annexure.id}`}
                    className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white transition hover:bg-emerald-500 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => decideAnnexure(annexure.id, "rejected")}
                    disabled={isMutating === `annexure:${annexure.id}`}
                    className="rounded-md bg-destructive px-3 py-1 text-xs font-medium text-destructive-foreground transition hover:bg-destructive/80 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
                <pre className="mt-3 overflow-x-auto rounded bg-muted px-3 py-2 text-xs text-muted-foreground">
                  {JSON.stringify(annexure.payload, null, 2)}
                </pre>
                {annexure.provenance?.textAnchors?.length ? (
                  <div className="mt-3 rounded border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                    <p className="font-medium text-foreground">Provenance</p>
                    <ul className="mt-2 list-inside space-y-1">
                      {annexure.provenance.textAnchors.map((anchor, index) => (
                        <li key={index}>
                          Page {anchor.page ?? "n/a"} —{" "}
                          {anchor.snippet ?? "snippet unavailable"}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
