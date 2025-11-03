interface MetricBadgeProps {
  label: string;
  value: string | number;
  trend?: "up" | "down" | "neutral";
  helperText?: string;
  className?: string;
}

const trendMeta: Record<Exclude<MetricBadgeProps["trend"], undefined>, string> = {
  up: "text-success bg-success/10 border border-success/20",
  down: "text-warning bg-warning/10 border border-warning/20",
  neutral: "text-muted-foreground bg-muted",
};

export function MetricBadge({ label, value, trend = "neutral", helperText, className }: MetricBadgeProps) {
  const badgeClass = ["inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", trendMeta[trend], className]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="flex flex-col gap-1">
      <dd className="text-2xl font-semibold text-foreground">{value}</dd>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      {helperText ? <span className={badgeClass}>{helperText}</span> : null}
    </div>
  );
}
