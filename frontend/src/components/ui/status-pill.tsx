type StatusVariant = "default" | "success" | "warning" | "accent" | "muted";

interface StatusPillProps {
  label: string;
  variant?: StatusVariant;
  icon?: React.ReactNode;
  className?: string;
}

const variantClasses: Record<StatusVariant, string> = {
  default: "bg-primary/10 text-primary border border-primary/20",
  success: "bg-success/10 text-success border border-success/20",
  warning: "bg-warning/10 text-warning border border-warning/30",
  accent: "bg-accent/10 text-accent border border-accent/20",
  muted: "bg-muted text-muted-foreground border border-muted",
};

export function StatusPill({ label, variant = "default", icon, className }: StatusPillProps) {
  const combined = [
    "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium",
    variantClasses[variant],
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span
      className={combined}
    >
      {icon ? <span aria-hidden className="grid h-3.5 w-3.5 place-items-center">{icon}</span> : null}
      {label}
    </span>
  );
}
