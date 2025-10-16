'use client';

import { useState, ChangeEvent, FormEvent } from 'react';
import Link from 'next/link';

const inputClasses =
  'block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm';
const labelClasses = 'block text-sm font-medium text-gray-700';
const buttonClasses =
  'rounded-md bg-slate-900 px-5 py-3 text-center text-sm font-medium text-white transition hover:bg-slate-700 disabled:bg-slate-400';

export default function TenderUploadPage() {
  const [files, setFiles] = useState<FileList | null>(null);
  const [platform, setPlatform] = useState('P1');
  const [tenderNo, setTenderNo] = useState('T1');
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState('');

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    setFiles(e.target.files);
    setStatus(''); // Clear status on new file selection
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!files || files.length === 0) {
      setStatus('Please select at least one file to upload.');
      return;
    }

    setIsLoading(true);
    setStatus(`Starting upload of ${files.length} file(s)...`);

    for (const file of Array.from(files)) {
      try {
        // 1. Get a signed URL from our backend
        setStatus(`Requesting upload URL for ${file.name}...`);
        const signedUrlResponse = await fetch('/api/poc/generate-upload-url', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_name: file.name,
            platform: platform,
            tender_no: tenderNo,
          }),
        });

        if (!signedUrlResponse.ok) {
          throw new Error(await signedUrlResponse.text());
        }

        const { url } = await signedUrlResponse.json();

        // 2. Upload the file directly to GCS using the signed URL
        setStatus(`Uploading ${file.name}...`);
        const uploadResponse = await fetch(url, {
          method: 'PUT',
          body: file,
          headers: {
            'Content-Type': file.type, // Use the actual file type
          },
        });

        if (!uploadResponse.ok) {
          throw new Error(`Upload failed for ${file.name}.`);
        }

        setStatus(`Successfully uploaded ${file.name}.`);
      } catch (error) {
        console.error(error);
        const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
        setStatus(`Error: ${errorMessage}`);
        setIsLoading(false);
        return; // Stop on first error
      }
    }

    setStatus('All files uploaded successfully!');
    setIsLoading(false);
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-8 px-4 py-16">
      <section>
        <Link href="/" className="text-sm text-muted-foreground hover:underline">
          &larr; Back to Home
        </Link>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight">
          Upload New Tender Documents
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          Upload PDF or DOCS files for a specific platform and tender number.
        </p>
      </section>

      <form className="space-y-6" onSubmit={handleSubmit}>
        <div>
          <label htmlFor="platform" className={labelClasses}>
            Platform
          </label>
          <select
            id="platform"
            name="platform"
            className={`mt-1 ${inputClasses}`}
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}>
            <option>P1</option>
            <option>P2</option>
            <option>P3</option>
            <option>P4</option>
            <option>P5</option>
          </select>
        </div>

        <div>
          <label htmlFor="tenderNo" className={labelClasses}>
            Tender No.
          </label>
          <select
            id="tenderNo"
            name="tenderNo"
            className={`mt-1 ${inputClasses}`}
            value={tenderNo}
            onChange={(e) => setTenderNo(e.target.value)}>
            <option>T1</option>
            <option>T2</option>
            <option>T3</option>
          </select>
        </div>

        <div>
          <label htmlFor="file-upload" className={labelClasses}>
            Documents
          </label>
          <input
            id="file-upload"
            name="file-upload"
            type="file"
            className="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:rounded-md file:border-0 file:bg-slate-100 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-slate-700 hover:file:bg-slate-200"
            multiple
            accept=".pdf,.doc,.docx"
            onChange={handleFileChange}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            You can select multiple files. Max file size: 5MB per file.
          </p>
        </div>

        <div className="flex flex-col gap-4">
          <button type="submit" className={buttonClasses} disabled={isLoading}>
            {isLoading ? 'Uploading...' : 'Upload'}
          </button>
          {status && <p className="text-sm text-muted-foreground">{status}</p>}
        </div>
      </form>
    </main>
  );
}