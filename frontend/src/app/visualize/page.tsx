'use client';

import { useState, FormEvent, useRef, useEffect } from 'react';
import Link from 'next/link';

const inputClasses =
  'block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm';
const labelClasses = 'block text-sm font-medium text-gray-700';
const buttonClasses =
  'rounded-md bg-slate-900 px-5 py-3 text-center text-sm font-medium text-white transition hover:bg-slate-700 disabled:bg-slate-400';

interface Message {
  text: string;
  sender: 'user' | 'agent';
}

export default function VisualizePage() {
  const [platform, setPlatform] = useState('P1');
  const [tenderNo, setTenderNo] = useState('T1');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Scroll to the bottom of the chat container when new messages are added
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages]);

  const handleChatSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { text: input, sender: 'user' };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch('/api/poc/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: input,
          tender_no: tenderNo,
          platform: platform,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'An error occurred');
      }

      const { answer } = await response.json();
      const agentMessage: Message = { text: answer, sender: 'agent' };
      setMessages((prev) => [...prev, agentMessage]);

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to get a response.';
      const agentMessage: Message = { text: `Error: ${errorMessage}`, sender: 'agent' };
      setMessages((prev) => [...prev, agentMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="mx-auto flex h-screen max-w-4xl flex-col gap-8 px-4 py-16">
      <section>
        <Link href="/" className="text-sm text-muted-foreground hover:underline">
          &larr; Back to Home
        </Link>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight">Visualize and Chat</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          Select a tender and platform to start a conversation with the RAG agent.
        </p>
      </section>

      <div className="space-y-4">
        <div className="flex gap-4">
          <div>
            <label htmlFor="platform" className={labelClasses}>
              Platform
            </label>
            <select
              id="platform"
              name="platform"
              className={`mt-1 ${inputClasses}`}
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
            >
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
              onChange={(e) => setTenderNo(e.target.value)}
            >
              <option>T1</option>
              <option>T2</option>
              <option>T3</option>
            </select>
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-col rounded-md border bg-slate-50 p-4">
        <div ref={chatContainerRef} className="flex-1 space-y-4 overflow-y-auto p-2">
          {messages.map((msg, index) => (
            <div
              key={index}
              className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-lg rounded-lg px-4 py-2 text-white ${msg.sender === 'user' ? 'bg-blue-600' : 'bg-slate-600'}`}>
                <p style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</p>
              </div>
            </div>
          ))}
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center text-center text-muted-foreground">
              No messages yet. Upload a document and ask a question!
            </div>
          )}
        </div>
        <form onSubmit={handleChatSubmit} className="mt-4 flex gap-2">
          <input
            type="text"
            className={inputClasses}
            placeholder="Ask a question about the tender..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
          />
          <button type="submit" className={buttonClasses} disabled={isLoading}>
            {isLoading ? '...' : 'Send'}
          </button>
        </form>
      </div>
    </main>
  );
}