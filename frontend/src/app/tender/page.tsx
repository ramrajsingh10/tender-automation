"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  completeFileUpload,
  createTenderSession,
  FileRecord,
  getTenderStatus,
  initFileUpload,
  ParseMetadata,
  TenderSessionResponse,
  triggerParsing,
  uploadFileToSignedUrl,
  UploadLimits,
  UploadInitResponse,
  RagIngestionStatus,
  retryRagIngestion,
} from "../../lib/tenderApi";

const DEFAULT_ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
] as const;
const DEFAULT_ACCEPT_EXTENSIONS = [".pdf", ".docx"] as const;
const MIME_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
    "DOCX",
};

const formatFileSize = (bytes: number): string => {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }
  if (bytes >= 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${bytes} bytes`;
};

type LocalFileStatus = "pending" | "uploading" | "uploaded" | "failed";

interface LocalFile {
  id: string;
  file: File;
  status: LocalFileStatus;
  progress: number;
  error?: string;
  remote?: FileRecord;
}

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

export default function TenderPage() {
  const [tenderId, setTenderId] = useState<string | null>(null);
  const [session, setSession] = useState<TenderSessionResponse | null>(null);
  const [uploadLimits, setUploadLimits] = useState<UploadLimits | null>(null);
  const [localFiles, setLocalFiles] = useState<LocalFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [parsingRequested, setParsingRequested] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isSessionLoading, setIsSessionLoading] = useState(true);
  const [isIngestionMutating, setIsIngestionMutating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const allowedMimeTypes = useMemo(() => {
    if (
      uploadLimits?.allowedMimeTypes &&
      uploadLimits.allowedMimeTypes.length > 0
    ) {
      return uploadLimits.allowedMimeTypes;
    }
    return [...DEFAULT_ALLOWED_TYPES];
  }, [uploadLimits?.allowedMimeTypes]);

  const maxSizeBytes = uploadLimits?.maxFileSizeBytes ?? 5 * 1024 * 1024;
  const maxSizeLabel = formatFileSize(maxSizeBytes);
  const allowedTypeLabel = useMemo(() => {
    const labels = allowedMimeTypes.map((type) => MIME_LABELS[type] ?? type);
    return labels.join(", ");
  }, [allowedMimeTypes]);
  const acceptAttribute = useMemo(() => {
    const deduped = new Set<string>([
      ...DEFAULT_ACCEPT_EXTENSIONS,
      ...allowedMimeTypes,
    ]);
    return Array.from(deduped).join(",");
  }, [allowedMimeTypes]);
  const isSessionReady = Boolean(tenderId && uploadLimits && !isSessionLoading);

  const refreshSession = useCallback(async () => {
    if (!tenderId) return null;
    try {
      const data = await getTenderStatus(tenderId);
      setSession(data);
      return data;
    } catch (error) {
      setErrorMessage((error as Error).message);
      return null;
    }
  }, [tenderId]);

  useEffect(() => {
    let isMounted = true;
    setIsSessionLoading(true);
    (async () => {
      try {
        const created = await createTenderSession();
        if (!isMounted) return;
        setTenderId(created.tenderId);
        setUploadLimits(created.uploadLimits);
        const initial = await getTenderStatus(created.tenderId);
        if (!isMounted) return;
        setSession(initial);
      } catch (error) {
        if (!isMounted) return;
        setErrorMessage((error as Error).message);
      } finally {
        if (isMounted) {
          setIsSessionLoading(false);
        }
      }
    })();
    return () => {
      isMounted = false;
    };
  }, []);

  const startParsing = useCallback(async () => {
    if (!tenderId) return;
    try {
      setIsProcessing(true);
      const updated = await triggerParsing(tenderId);
      setSession(updated);
    } catch (error) {
      setParsingRequested(false);
      setErrorMessage((error as Error).message);
    } finally {
      setIsProcessing(false);
    }
  }, [tenderId]);

  const requestParsing = useCallback(() => {
    if (!session || session.ragIngestion.status !== "done") {
      setErrorMessage(
        "RAG ingestion has not completed yet. Wait for ingestion to finish or retry it before running the playbook.",
      );
      return;
    }
    setParsingRequested(true);
    void startParsing().catch(() => {
      setParsingRequested(false);
    });
  }, [session, startParsing]);

  useEffect(() => {
    if (!tenderId || !session) return;

    const shouldPoll =
      session.status === "parsing" ||
      session.status === "uploading" ||
      session.ragIngestion.status === "pending" ||
      session.ragIngestion.status === "running";

    if (shouldPoll) {
      const interval = setInterval(() => {
        void refreshSession();
      }, 5000);
      return () => clearInterval(interval);
    }

    if (
      session.status === "uploaded" &&
      session.ragIngestion.status === "done" &&
      !parsingRequested &&
      !isProcessing
    ) {
      requestParsing();
    }
  }, [
    isProcessing,
    parsingRequested,
    refreshSession,
    requestParsing,
    session,
    tenderId,
  ]);

  const updateLocalFile = useCallback(
    (id: string, partial: Partial<LocalFile>) => {
      setLocalFiles((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...partial } : item)),
      );
    },
    [],
  );

  const handleUpload = useCallback(
    async (files: File[]) => {
      if (!tenderId || !uploadLimits) {
        setErrorMessage(
          "Upload session not ready yet. Please wait and try again.",
        );
        return;
      }
      if (!files.length) return;

      setIsUploading(true);
      setErrorMessage(null);

      for (const file of files) {
        const id = crypto.randomUUID();
        const isSizeValid = file.size <= maxSizeBytes;
        const isTypeValid = allowedMimeTypes.includes(file.type);

        if (!isSizeValid || !isTypeValid) {
          setLocalFiles((prev) => [
            ...prev,
            {
              id,
              file,
              status: "failed",
              progress: 0,
              error: !isSizeValid
                ? `File exceeds the ${maxSizeLabel} limit.`
                : `Unsupported file type. Allowed: ${allowedTypeLabel}.`,
            },
          ]);
          continue;
        }

        setLocalFiles((prev) => [
          ...prev,
          {
            id,
            file,
            status: "uploading",
            progress: 0,
          },
        ]);

        let initResponse: UploadInitResponse | null = null;
        try {
          initResponse = await initFileUpload(tenderId, {
            filename: file.name,
            sizeBytes: file.size,
            contentType: file.type || "application/octet-stream",
          });

          await uploadFileToSignedUrl(initResponse, file, (percent) => {
            updateLocalFile(id, { progress: percent });
          });

          const remoteRecord = await completeFileUpload(
            tenderId,
            initResponse.fileId,
            { status: "uploaded" },
          );
          updateLocalFile(id, {
            status: "uploaded",
            progress: 100,
            remote: remoteRecord,
          });
        } catch (error) {
          const message = (error as Error).message;
          updateLocalFile(id, {
            status: "failed",
            progress: 0,
            error: message,
          });
          if (initResponse) {
            try {
              await completeFileUpload(tenderId, initResponse.fileId, {
                status: "failed",
                error: message,
              });
            } catch {
              // ignore follow-up failure
            }
          }
          setErrorMessage(message);
        } finally {
          await refreshSession();
        }
      }

      setIsUploading(false);
    },
    [
      allowedMimeTypes,
      allowedTypeLabel,
      maxSizeBytes,
      maxSizeLabel,
      refreshSession,
      tenderId,
      updateLocalFile,
      uploadLimits,
    ],
  );

  const handleRetryIngestion = useCallback(async () => {
    if (!tenderId) return;
    setErrorMessage(null);
    setIsIngestionMutating(true);
    try {
      await retryRagIngestion(tenderId);
      await refreshSession();
    } catch (error) {
      setErrorMessage((error as Error).message);
    } finally {
      setIsIngestionMutating(false);
    }
  }, [refreshSession, tenderId]);

  const handleFileInput = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      if (!isSessionReady) {
        event.preventDefault();
        return;
      }
      const files = event.target.files;
      if (files) {
        void handleUpload(Array.from(files));
        event.target.value = "";
      }
    },
    [handleUpload, isSessionReady],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLLabelElement>) => {
      event.preventDefault();
      if (!isSessionReady) return;
      setIsDragging(false);
      const files = Array.from(event.dataTransfer.files ?? []);
      void handleUpload(files);
    },
    [handleUpload, isSessionReady],
  );

  const handleDragOver = useCallback(
    (event: React.DragEvent<HTMLLabelElement>) => {
      event.preventDefault();
      setIsDragging(true);
    },
    [],
  );

  const handleDragLeave = useCallback(
    (event: React.DragEvent<HTMLLabelElement>) => {
      event.preventDefault();
      setIsDragging(false);
    },
    [],
  );

  const parseInfo = useMemo<ParseMetadata | null>(
    () => session?.parse ?? null,
    [session],
  );
  const isReadyForValidation = session?.status === "parsed";

  const tenderStatus =
    session?.status ?? (isSessionLoading ? "uploading" : "uploading");
  const ingestionStatus: RagIngestionStatus =
    session?.ragIngestion?.status ?? "pending";
  const ingestionError = session?.ragIngestion?.lastError ?? null;

  const uploadStepState: StepState =
    tenderStatus === "uploading" ? "active" : "completed";

  const ingestionStepState: StepState =
    ingestionStatus === "running"
      ? "active"
      : ingestionStatus === "done"
        ? "completed"
        : ingestionStatus === "failed"
          ? "failed"
          : tenderStatus === "uploading"
            ? "pending"
            : "active";

  const playbookStepState: StepState =
    tenderStatus === "parsing"
      ? "active"
      : tenderStatus === "parsed"
        ? "completed"
        : tenderStatus === "failed"
          ? "failed"
          : ingestionStatus === "done"
            ? "pending"
            : "pending";

  const validationStepState: StepState =
    tenderStatus === "parsed"
      ? "completed"
      : tenderStatus === "failed"
        ? "failed"
        : "pending";

  const uploadDescription =
    tenderStatus === "uploading"
      ? "Documents are being streamed to secure storage."
      : "Documents are stored securely.";

  const ingestionDescription =
    ingestionStatus === "running"
      ? "Importing documents into the Vertex RAG corpus."
      : ingestionStatus === "done"
        ? "Documents are ready inside the Vertex RAG corpus."
        : ingestionStatus === "failed"
          ? "Ingestion failed. Retry to requeue the import job."
          : "Waiting for uploads to finish before starting ingestion.";

  const canStartProcessing =
    tenderStatus === "uploaded" && ingestionStatus === "done";

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-4 py-16">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">
          New Tender Intake
        </h1>
        <p className="text-muted-foreground">
          Upload tender packs and kick off automated parsing. Once completed,
          jump to the validation workspace for review.
        </p>
      </header>

      {errorMessage ? (
        <div className="rounded border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {errorMessage}
        </div>
      ) : null}

      <section className="grid gap-4 rounded-xl border border-dashed border-border bg-muted/50 p-6 text-center">
        <label
          htmlFor="tender-upload"
          aria-disabled={!isSessionReady}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/40 px-6 py-10 transition ${
            !isSessionReady
              ? "cursor-not-allowed opacity-60"
              : isDragging
                ? "border-primary bg-primary/10 text-primary"
                : "hover:border-primary/70 hover:bg-muted"
          }`}
          onClick={(event) => {
            if (!isSessionReady) {
              event.preventDefault();
              event.stopPropagation();
            }
          }}
        >
          <div className="space-y-2">
            <p className="text-lg font-medium">Drag &amp; drop files here</p>
            <p className="text-sm text-muted-foreground">
              {allowedTypeLabel} - up to {maxSizeLabel} each
            </p>
          </div>
          <button
            type="button"
            className="mt-4 rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              if (!isSessionReady) {
                return;
              }
              fileInputRef.current?.click();
            }}
            disabled={!isSessionReady}
          >
            {isSessionReady ? "Browse files" : "Preparing upload..."}
          </button>
          <input
            ref={fileInputRef}
            id="tender-upload"
            type="file"
            multiple
            accept={acceptAttribute}
            className="sr-only"
            onChange={handleFileInput}
          />
        </label>
          <p className="text-xs text-muted-foreground">
            Files are streamed directly to secure Cloud Storage. Once everything
            lands, we automatically run the Vertex AI playbook.
          </p>
      </section>

      <section className="space-y-3">
        <header className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Uploads</h2>
          {tenderId ? (
            <span className="text-xs text-muted-foreground">
              Tender ID: {tenderId}
            </span>
          ) : null}
        </header>
        <div className="space-y-2 rounded-lg border bg-card p-4 text-sm">
          {localFiles.length === 0 ? (
            <p className="text-muted-foreground">No files uploaded yet.</p>
          ) : (
            <ul className="space-y-2">
              {localFiles.map((item) => (
                <li
                  key={item.id}
                  className="rounded border border-border/60 bg-background p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="space-y-1">
                      <p className="font-medium">{item.file.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {(item.file.size / 1024 / 1024).toFixed(2)} MB -{" "}
                        {item.file.type || "unknown type"}
                      </p>
                    </div>
                    <div className="text-right text-xs uppercase tracking-wide text-muted-foreground">
                      {item.status === "uploading" && (
                        <span className="text-primary">
                          Uploading {item.progress}%
                        </span>
                      )}
                      {item.status === "uploaded" && (
                        <span className="text-emerald-600">Uploaded</span>
                      )}
                      {item.status === "failed" && (
                        <span className="text-destructive">Failed</span>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className={`h-full transition-all ${item.status === "failed" ? "bg-destructive" : "bg-primary"}`}
                      style={{
                        width: `${item.status === "uploaded" ? 100 : item.progress}%`,
                      }}
                    />
                  </div>
                  {item.error ? (
                    <p className="mt-2 text-xs text-destructive">
                      {item.error}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {isUploading ? (
            <p className="text-xs text-muted-foreground">Uploading files...</p>
          ) : null}
        </div>
      </section>

      <section className="space-y-3">
        <header className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Processing status</h2>
          <span className="text-xs uppercase tracking-wide text-primary">
            {session?.status ?? "loading..."}
          </span>
        </header>
        <div className="space-y-4 rounded-lg border bg-card p-4 text-sm text-muted-foreground">
          <div className="space-y-3">
            <StatusStep
              label="Upload files"
              description={uploadDescription}
              state={uploadStepState}
            />
            <StatusStep
              label="Ingest into Vertex RAG corpus"
              description={ingestionDescription}
              state={ingestionStepState}
            />
            <StatusStep
              label="AI playbook processing"
              description={
                tenderStatus === "failed"
                  ? "Processing failed. Review the error and retry."
                  : "Extracting structured data from your tender pack."
              }
              state={playbookStepState}
            />
            <StatusStep
              label="Ready for validation"
              description="Switch to the validation workspace to review results."
              state={validationStepState}
            />
          </div>
          <p>
            {ingestionStatus === "failed" ? (
              <span className="text-destructive">
                RAG ingestion failed.{" "}
                {ingestionError
                  ? `Reason: ${ingestionError}`
                  : "Retry the ingestion job to continue."}
              </span>
            ) : ingestionStatus === "running" ? (
              "Importing documents into Vertex RAG. This may take a minute for large tenders."
            ) : ingestionStatus === "done" ? (
              tenderStatus === "parsed"
                ? "Playbook complete! Head over to the validation workspace to review extracted data."
                : tenderStatus === "parsing"
                  ? "The managed Vertex AI playbook is running. This may take a minute for large tenders."
                  : "Documents are ready in Vertex RAG. Start the playbook when you are ready."
            ) : (
              "Waiting for uploads to finish before starting ingestion."
            )}
          </p>

          {ingestionStatus === "failed" ? (
            <button
              type="button"
              onClick={handleRetryIngestion}
              className="inline-flex items-center justify-center rounded-md border border-destructive px-3 py-2 text-xs font-medium text-destructive transition hover:bg-destructive/10 disabled:opacity-60"
              disabled={isIngestionMutating}
            >
              {isIngestionMutating ? "Retrying..." : "Retry ingestion"}
            </button>
          ) : null}

          {session?.status === "uploaded" && !parsingRequested ? (
            <button
              type="button"
              onClick={requestParsing}
              className="mt-1 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
              disabled={isProcessing || !canStartProcessing}
            >
              {isProcessing ? "Starting..." : "Start processing now"}
            </button>
          ) : null}

          {session?.status === "failed" ? (
            <button
              type="button"
              onClick={requestParsing}
              className="inline-flex items-center justify-center rounded-md border border-destructive px-3 py-2 text-xs font-medium text-destructive transition hover:bg-destructive/10 disabled:opacity-60"
              disabled={isProcessing}
            >
              Retry processing
            </button>
          ) : null}

          {parseInfo?.outputUri ? (
            <p className="text-xs">
              Output stored at{" "}
              <span className="font-medium text-foreground">
                {parseInfo.outputUri}
              </span>
              . You can inspect the JSON in Cloud Storage.
            </p>
          ) : null}

          {session?.ragFiles?.length ? (
            <div className="rounded-md border border-dashed border-muted px-3 py-2">
              <p className="text-xs font-medium text-foreground">
                RAG corpus artifacts
              </p>
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {session.ragFiles.map((item) => (
                  <li key={item.ragFileName}>
                    <span className="font-mono text-foreground">
                      {item.ragFileName}
                    </span>
                    {item.sourceUri ? (
                      <span className="text-muted-foreground">
                        {" "}
                        → {item.sourceUri}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </section>


      <footer className="border-t pt-4 text-xs text-muted-foreground">
        <p>
          Upload policy: {allowedTypeLabel} — max {maxSizeLabel} per file
        </p>
        {isReadyForValidation ? (
          <p className="mt-2">
            Processing complete. Review the extracted data on the{" "}
            <a
              className="text-primary underline"
              href={`/valid?tenderId=${tenderId ?? ""}`}
            >
              validation page
            </a>
            .
          </p>
        ) : null}
      </footer>
    </main>
  );
}
