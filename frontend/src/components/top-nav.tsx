"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navLinks = [
  { href: "/", label: "Home" },
  { href: "/tender", label: "Tender Intake" },
  { href: "/dashboard", label: "Dashboard" },
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/70 bg-surface/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-6 py-4">
        <Link href="/" className="flex items-center gap-2 text-lg font-semibold text-foreground">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-sm font-bold text-primary-foreground shadow-subtle">
            TA
          </span>
          <span className="hidden sm:inline">Tender Automation Studio</span>
        </Link>
        <nav className="flex items-center gap-4 text-sm font-medium">
          {navLinks.map(({ href, label }) => {
            const isActive = pathname === href || (href !== "/" && pathname?.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                className={[
                  "rounded-lg px-3 py-2 transition",
                  isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground hover:bg-muted",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {label}
              </Link>
            );
          })}
        </nav>
        <Link
          href="/tender"
          className="hidden rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-card transition hover:bg-primary/90 sm:inline-flex"
        >
          Start a tender
        </Link>
      </div>
    </header>
  );
}
