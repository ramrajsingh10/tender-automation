"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

type ToastVariant = "info" | "success" | "warning" | "error";

export interface ToastOptions {
  id?: string;
  title?: string;
  description: string;
  variant?: ToastVariant;
  duration?: number;
}

interface ToastContextValue {
  pushToast: (options: ToastOptions) => void;
  dismissToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const variantClasses: Record<ToastVariant, string> = {
  info: "border border-primary/20 bg-primary/10 text-primary",
  success: "border border-success/20 bg-success/10 text-success",
  warning: "border border-warning/30 bg-warning/10 text-warning",
  error: "border border-red-400/30 bg-red-50 text-red-600",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastOptions[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback(
    (options: ToastOptions) => {
      const id = options.id ?? (typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2));
      const toast = { ...options, id, variant: options.variant ?? "info", duration: options.duration ?? 4200 };
      setToasts((prev) => [...prev.filter((item) => item.id !== id), toast]);
      if (toast.duration! > 0) {
        window.setTimeout(() => dismissToast(id), toast.duration);
      }
    },
    [dismissToast],
  );

  const value = useMemo(() => ({ pushToast, dismissToast }), [pushToast, dismissToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-6 top-6 z-50 flex w-80 flex-col gap-3">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={[
              "pointer-events-auto overflow-hidden rounded-xl px-4 py-3 shadow-card backdrop-blur",
              variantClasses[toast.variant ?? "info"],
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                {toast.title ? <p className="text-sm font-semibold leading-none">{toast.title}</p> : null}
                <p className="text-sm leading-snug text-foreground/80">{toast.description}</p>
              </div>
              <button
                type="button"
                onClick={() => toast.id && dismissToast(toast.id)}
                className="text-xs font-semibold text-foreground/70 transition hover:text-foreground"
              >
                Close
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
