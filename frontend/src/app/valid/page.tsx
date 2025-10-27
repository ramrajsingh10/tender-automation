"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getPlaybookResults,
  getTenderStatus,
  queryRag,
  deleteRagFiles,
  PlaybookRun,
  RagQueryRequest,
  RagQueryResponse,
  TenderSessionResponse,
  TenderStatus,
} from "../../lib/tenderApi";

type StepState = "pending" | "active" | "completed" | "failed";

function StatusStep({
  label,
  description,
  state,
}: {
  label: string;
  description: string;
  state: StepState;
}) {
  const dotClass =
    state === "completed"
      ? "bg-primary"
      : state === "failed"
        ? "bg-destructive"
        : "bg-muted";

  return (
    <div className="flex items-start gap-3">
      <div className="mt-1 h-3 w-3">
        {state === "active" ? (
          <span className="block h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        ) : (
          <span className={`block h-3 w-3 rounded-full ${dotClass}`} />
        )}
      </div>
      <div className="space-y-1">
        <p className="font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}

function getTenderIdFromSearch(searchParams: URLSearchParams): string | null {
  return searchParams.get("tenderId");
}

export default function ValidationPage() {
  const [tenderId, setTenderId] = useState<string | null>(null);
  const [tenderStatus, setTenderStatus] =
    useState<TenderSessionResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [isStatusLoading, setIsStatusLoading] = useState(false);

  const [playbookRun, setPlaybookRun] = useState<PlaybookRun | null>(null);
  const [playbookError, setPlaybookError] = useState<string | null>(null);
  const [isPlaybookLoading, setIsPlaybookLoading] = useState(false);

  const [ragQuestion, setRagQuestion] = useState("");
  const [ragResponse, setRagResponse] = useState<RagQueryResponse | null>(null);
  const [isRagLoading, setIsRagLoading] = useState(false);
  const [ragError, setRagError] = useState<string | null>(null);
  const [isClientReady, setIsClientReady] = useState(false);
  const [isDeletingRagFiles, setIsDeletingRagFiles] = useState(false);
  const [ragDeleteError, setRagDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    setTenderId(getTenderIdFromSearch(params));
    setIsClientReady(true);
  }, []);

  const loadStatus = async (id: string) => {
    setIsStatusLoading(true);
    setStatusError(null);
    try {
      const data = await getTenderStatus(id);
      setTenderStatus(data);
      return data;
    } catch (err) {
      setStatusError((err as Error).message);
      throw err;
    } finally {
      setIsStatusLoading(false);
    }
  };

  const loadPlaybook = async (id: string) => {
    setIsPlaybookLoading(true);
    setPlaybookError(null);
    try {
      const run = await getPlaybookResults(id);
      setPlaybookRun(run);
    } catch (err) {
      setPlaybookRun(null);
      setPlaybookError((err as Error).message);
    } finally {
      setIsPlaybookLoading(false);
    }
  };

  const handleRemoveRagFiles = async () => {
    if (!tenderId) {
      return;
    }
    setRagDeleteError(null);
    setIsDeletingRagFiles(true);
    try {
      await deleteRagFiles(tenderId);
      await loadStatus(tenderId);
      setPlaybookRun(null);
    } catch (err) {
      setRagDeleteError(
        err instanceof Error ? err.message : "Failed to remove RAG files.",
      );
    } finally {
      setIsDeletingRagFiles(false);
    }
  };

  useEffect(() => {
    if (!tenderId) {
      setTenderStatus(null);
      setPlaybookRun(null);
      return;
    }
    void loadStatus(tenderId);
  }, [tenderId]);

  useEffect(() => {
    if (!tenderId) {
      return;
    }
    if (tenderStatus?.parse?.outputUri) {
      void loadPlaybook(tenderId);
    } else {
      setPlaybookRun(null);
    }
  }, [tenderId, tenderStatus?.parse?.outputUri]);

  const statusState = tenderStatus?.status ?? ("uploading" as TenderStatus);

  const handleRagQuery = async () => {
    if (!tenderId) {
      setRagError("Load a tender before querying the agent.");
      return;
    }
    if (!ragQuestion.trim()) {
      setRagError("Ask a question about the tender first.");
      return;
    }
    setIsRagLoading(true);
    setRagError(null);
    try {
      const request: RagQueryRequest = {
        tenderId,
        question: ragQuestion.trim(),
      };
      const response = await queryRag(request);
      setRagResponse(response);
    } catch (err) {
      setRagResponse(null);
      setRagError(err instanceof Error ? err.message : "Query failed.");
    } finally {
      setIsRagLoading(false);
    }
  };

  const playbookGeneratedAt = useMemo(() => {
    if (!playbookRun?.generatedAt) return null;
    try {
      return new Date(playbookRun.generatedAt).toLocaleString();
    } catch {
      return playbookRun.generatedAt;
    }
  }, [playbookRun]);

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
        {!isClientReady ? (
          <p className="text-sm text-muted-foreground">
            Loading tender context…
          </p>
        ) : !tenderId ? (
          <p className="text-sm text-destructive">
            Provide a tenderId query parameter to load data.
          </p>
        ) : null}
      </header>

      <section className="space-y-3 rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
        <StatusStep
          label="Uploads received"
          description="Tender documents have been uploaded to storage."
          state={
            statusState && statusState !== "uploading" ? "completed" : "active"
          }
        />
        <StatusStep
          label="RAG import & agent pass"
          description={
            statusState === "failed"
              ? "Processing failed. Review the tender in the intake page to retry."
              : "Running the managed Vertex AI playbooks across the tender bundle."
          }
          state={
            statusState === "failed"
              ? "failed"
              : statusState === "parsed"
                ? "completed"
                : statusState === "uploading" || !statusState
                  ? "pending"
                  : "active"
          }
        />
        <StatusStep
          label="Results ready for validation"
          description={
            playbookRun
              ? "AI answers are ready to review below."
              : statusState === "parsed"
                ? "Waiting for Vertex AI playbook output… refresh shortly."
                : "Results will appear once processing completes."
          }
          state={
            statusState === "failed"
              ? "failed"
              : playbookRun
                ? "completed"
                : statusState === "parsed"
                  ? "active"
                  : "pending"
          }
        />
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <button
            type="button"
            onClick={() => tenderId && void loadStatus(tenderId)}
            className="rounded-md border border-border bg-background px-3 py-1 text-xs font-medium text-foreground transition hover:bg-muted disabled:opacity-50"
            disabled={!tenderId || isStatusLoading}
          >
            {isStatusLoading ? "Refreshing…" : "Refresh status"}
          </button>
          {tenderStatus?.parse?.outputUri ? (
            <button
              type="button"
              onClick={() => tenderId && void loadPlaybook(tenderId)}
              className="rounded-md border border-border bg-background px-3 py-1 text-xs font-medium text-foreground transition hover:bg-muted disabled:opacity-50"
              disabled={!tenderId || isPlaybookLoading}
            >
              {isPlaybookLoading ? "Refreshing answers…" : "Refresh answers"}
            </button>
          ) : null}
        </div>
        {statusError ? (
          <p className="text-xs text-destructive">{statusError}</p>
        ) : null}
      </section>

      {playbookError ? (
        <div className="rounded border border-destructive/60 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {playbookError}
        </div>
      ) : null}

      <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-medium">Ask the tender</h2>
            <p className="text-sm text-muted-foreground">
              Query the managed Vertex Agent Builder corpus for quick answers
              about the uploaded documents.
            </p>
          </div>
        </div>
        <div className="mt-4 space-y-3">
          <textarea
            className="w-full min-h-[120px] rounded border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            placeholder="What is the submission deadline for this tender?"
            value={ragQuestion}
            onChange={(event) => setRagQuestion(event.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleRagQuery}
              disabled={isRagLoading || !tenderId}
              className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
            >
              {isRagLoading ? "Asking…" : "Ask question"}
            </button>
            <p className="text-xs text-muted-foreground">
              Results stream back directly from Vertex AI Search.
            </p>
          </div>
          {ragError ? (
            <p className="text-sm text-destructive">{ragError}</p>
          ) : null}
          {ragResponse?.answers?.length ? (
            <div className="space-y-3">
              {ragResponse.answers.map((answer, index) => (
                <div
                  key={index}
                  className="rounded border bg-background p-4 text-sm text-foreground"
                >
                  <p className="whitespace-pre-line">{answer.text}</p>
                  {answer.citations?.length ? (
                    <details className="mt-3 text-xs text-muted-foreground">
                      <summary className="cursor-pointer text-primary">
                        View citations
                      </summary>
                      <pre className="mt-2 max-h-64 overflow-y-auto rounded bg-muted/60 p-2">
                        {JSON.stringify(answer.citations, null, 2)}
                      </pre>
                    </details>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          {ragResponse?.documents?.length ? (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-foreground">
                Top retrieved documents
              </h3>
              <ul className="space-y-2 text-sm text-muted-foreground">
                {ragResponse.documents.map((doc, index) => (
                  <li
                    key={doc.id ?? index}
                    className="rounded border bg-background/80 px-3 py-2"
                  >
                    <p className="font-medium text-foreground">
                      {doc.title ?? doc.uri ?? `Result ${index + 1}`}
                    </p>
                    {doc.snippet ? (
                      <p className="text-xs text-muted-foreground">
                        {doc.snippet}
                      </p>
                    ) : null}
                    {doc.uri ? (
                      <a
                        className="mt-1 inline-flex text-xs text-primary underline"
                        href={doc.uri}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open source
                      </a>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </section>

      {tenderStatus?.ragFiles?.length ? (
        <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <header className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-medium">RAG corpus artifacts</h2>
              <p className="text-sm text-muted-foreground">
                Review or remove the RagFile handles generated during ingestion.
              </p>
            </div>
            <button
              type="button"
              onClick={handleRemoveRagFiles}
              className="inline-flex items-center justify-center rounded-md border border-muted px-3 py-2 text-xs font-medium text-muted-foreground transition hover:bg-muted disabled:opacity-60"
              disabled={isDeletingRagFiles}
            >
              {isDeletingRagFiles
                ? "Removing from corpus�?�"
                : "Remove from RAG corpus"}
            </button>
          </header>
          <ul className="mt-4 space-y-2 text-xs text-muted-foreground">
            {tenderStatus.ragFiles.map((item) => (
              <li key={item.ragFileName}>
                <span className="font-mono text-foreground">
                  {item.ragFileName}
                </span>
                {item.sourceUri ? (
                  <span className="text-muted-foreground">
                    {" "}
                    �+' {item.sourceUri}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
          {ragDeleteError ? (
            <p className="mt-3 text-xs text-destructive">{ragDeleteError}</p>
          ) : null}
        </section>
      ) : null}

      <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-medium">AI playbook answers</h2>
            <p className="text-sm text-muted-foreground">
              These results are generated automatically using the Vertex Agent
              playbooks after each upload.
            </p>
          </div>
          {playbookGeneratedAt ? (
            <p className="text-xs text-muted-foreground">
              Generated at {playbookGeneratedAt}
            </p>
          ) : null}
        </div>
        {isPlaybookLoading ? (
          <p className="mt-4 text-sm text-muted-foreground">Loading answers…</p>
        ) : playbookRun && playbookRun.results.length ? (
          <div className="mt-4 space-y-4">
            {playbookRun.results.map((result) => (
              <div
                key={result.questionId}
                className="rounded border bg-background p-4 shadow-sm"
              >
                <header className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">
                      {result.question}
                    </p>
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      {result.questionId}
                    </p>
                  </div>
                </header>
                {result.answers.length ? (
                  <div className="mt-3 space-y-3 text-sm text-foreground">
                    {result.answers.map((answer, index) => (
                      <div key={index} className="space-y-2">
                        <p className="whitespace-pre-line">{answer.text}</p>
                        {answer.citations?.length ? (
                          <details className="text-xs text-muted-foreground">
                            <summary className="cursor-pointer text-primary">
                              Citations
                            </summary>
                            <pre className="mt-2 max-h-48 overflow-y-auto rounded bg-muted/60 p-2">
                              {JSON.stringify(answer.citations, null, 2)}
                            </pre>
                          </details>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-muted-foreground">
                    No answer returned for this prompt.
                  </p>
                )}
                {result.documents.length ? (
                  <div className="mt-4 space-y-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Top supporting documents
                    </h4>
                    <ul className="space-y-1 text-xs text-muted-foreground">
                      {result.documents.map((doc, index) => (
                        <li key={doc.id ?? index}>
                          <span className="font-medium text-foreground">
                            {doc.title ?? doc.uri ?? `Document ${index + 1}`}
                          </span>
                          {doc.uri ? (
                            <>
                              {" "}
                              —{" "}
                              <a
                                href={doc.uri}
                                className="text-primary underline"
                                target="_blank"
                                rel="noreferrer"
                              >
                                View
                              </a>
                            </>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm text-muted-foreground">
            No AI results available yet. Trigger processing from the intake page
            once uploads are complete.
          </p>
        )}
      </section>
    </main>
  );
}
