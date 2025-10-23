/* eslint-disable @typescript-eslint/no-explicit-any */
export type TenderStatus = 'uploading' | 'uploaded' | 'parsing' | 'parsed' | 'failed';

export interface UploadLimits {
  maxFileSizeBytes?: number;
  allowedMimeTypes?: string[];
  maxFiles?: number | null;
}

export interface FileRecord {
  fileId: string;
  originalName: string;
  storedName: string;
  contentType: string;
  sizeBytes: number;
  storageUri?: string | null;
  status: 'pending' | 'uploading' | 'uploaded' | 'failed';
  uploadedAt?: string | null;
  error?: string | null;
}

export interface ParseMetadata {
  operationName?: string | null;
  inputPrefix?: string | null;
  outputPrefix?: string | null;
  outputUri?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  lastCheckedAt?: string | null;
  error?: string | null;
}

export interface TenderSessionResponse {
  tenderId: string;
  status: TenderStatus;
  createdAt: string;
  uploadLimits?: UploadLimits;
  files: FileRecord[];
  parse: ParseMetadata;
}

export interface CreateTenderResponse {
  tenderId: string;
  status: TenderStatus;
  uploadLimits: UploadLimits;
}

export interface UploadInitResponse {
  fileId: string;
  uploadUrl: string;
  requiredHeaders: Record<string, string>;
  storagePath: string;
  storageUri: string;
}

export interface UploadCompletionRequest {
  status: 'uploaded' | 'failed';
  error?: string;
}

function getBaseUrl(): string {
  const candidates: Array<string | undefined> = [
    process.env.NEXT_PUBLIC_TENDER_BACKEND_URL,
    process.env.NEXT_PUBLIC_API_URL,
    typeof window !== 'undefined' ? window.location.origin : undefined,
  ];
  const resolved = candidates.find((value) => typeof value === 'string' && value.trim().length > 0);
  if (!resolved) {
    throw new Error(
      'Backend base URL is not configured. Set NEXT_PUBLIC_TENDER_BACKEND_URL or NEXT_PUBLIC_API_URL.',
    );
  }
  return resolved.replace(/\/+$/, '');
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getBaseUrl()}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      message = (body as any)?.detail ?? message;
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function createTenderSession(createdBy?: string): Promise<CreateTenderResponse> {
  return request<CreateTenderResponse>('/api/tenders/', {
    method: 'POST',
    body: JSON.stringify(createdBy ? { createdBy } : {}),
  });
}

export async function getTenderStatus(tenderId: string): Promise<TenderSessionResponse> {
  return request<TenderSessionResponse>(`/api/tenders/${tenderId}`, {
    method: 'GET',
    cache: 'no-store',
  });
}

export async function initFileUpload(
  tenderId: string,
  params: { filename: string; sizeBytes: number; contentType: string },
): Promise<UploadInitResponse> {
  return request<UploadInitResponse>(`/api/tenders/${tenderId}/uploads/init`, {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function completeFileUpload(
  tenderId: string,
  fileId: string,
  body: UploadCompletionRequest,
): Promise<FileRecord> {
  return request<FileRecord>(`/api/tenders/${tenderId}/uploads/${fileId}/complete`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function triggerParsing(tenderId: string): Promise<TenderSessionResponse> {
  return request<TenderSessionResponse>(`/api/tenders/${tenderId}/process`, {
    method: 'POST',
  });
}

export interface SignedUploadInfo extends UploadInitResponse {
  requiredHeaders: Record<string, string>;
}

export async function uploadFileToSignedUrl(
  info: SignedUploadInfo,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', info.uploadUrl);
    Object.entries(info.requiredHeaders || {}).forEach(([key, value]) => {
      xhr.setRequestHeader(key, value);
    });

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        const percent = Math.round((event.loaded / event.total) * 100);
        onProgress(percent);
      }
    };

    xhr.onerror = () => reject(new Error('Upload failed'));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        resolve();
      } else {
        reject(new Error(`Upload failed with status ${xhr.status}`));
      }
    };

    xhr.send(file);
  });
}

export interface RagCitation {
  startIndex?: number | null;
  endIndex?: number | null;
  sources?: Array<Record<string, unknown>>;
}

export interface RagAnswer {
  text: string;
  citations: RagCitation[];
}

export interface RagDocumentSummary {
  id?: string | null;
  uri?: string | null;
  title?: string | null;
  snippet?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface RagQueryResponse {
  answers: RagAnswer[];
  documents: RagDocumentSummary[];
}

export interface RagQueryRequest {
  tenderId: string;
  question: string;
  conversationId?: string;
  topK?: number;
}

export async function queryRag(body: RagQueryRequest): Promise<RagQueryResponse> {
  return request<RagQueryResponse>('/api/rag/query', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export interface PlaybookResult {
  questionId: string;
  question: string;
  answers: RagAnswer[];
  documents: RagDocumentSummary[];
}

export interface PlaybookRun {
  tenderId: string;
  generatedAt: string;
  results: PlaybookResult[];
}

export async function getPlaybookResults(tenderId: string): Promise<PlaybookRun> {
  return request<PlaybookRun>(`/api/tenders/${tenderId}/playbook`, {
    method: 'GET',
    cache: 'no-store',
  });
}
