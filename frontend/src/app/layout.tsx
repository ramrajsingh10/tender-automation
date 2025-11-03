import type { Metadata } from "next";
import "./globals.css";
import { Work_Sans } from "next/font/google";
import { ToastProvider } from "@/components/ui/toast";
import { TopNav } from "@/components/top-nav";

export const metadata: Metadata = {
  title: "Tender Automation",
  description: "Internal tools for managing tender analysis and tracking.",
};

const workSans = Work_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={workSans.variable}>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <ToastProvider>
          <TopNav />
          <main className="min-h-[calc(100vh-4rem)] bg-transparent">{children}</main>
        </ToastProvider>
      </body>
    </html>
  );
}
