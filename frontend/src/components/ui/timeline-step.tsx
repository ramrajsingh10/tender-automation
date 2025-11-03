import { StatusPill } from "./status-pill";

type TimelineState = "pending" | "active" | "completed" | "failed";

interface TimelineStepProps {
  step: number;
  label: string;
  description?: string | null;
  state: TimelineState;
}

const stateMeta: Record<
  TimelineState,
  { variant: "default" | "success" | "warning" | "accent" | "muted"; connector: string }
> = {
  pending: { variant: "muted", connector: "bg-muted" },
  active: { variant: "accent", connector: "bg-accent/40" },
  completed: { variant: "success", connector: "bg-success/50" },
  failed: { variant: "warning", connector: "bg-warning/30" },
};

export function TimelineStep({ step, label, description, state }: TimelineStepProps) {
  const meta = stateMeta[state];

  return (
    <div className="flex min-w-[200px] flex-col items-start gap-3">
      <div className="flex items-center gap-3">
        <div
          className={[
            "flex h-9 w-9 items-center justify-center rounded-full border-2 font-semibold",
            state === "completed"
              ? "border-success text-success"
              : state === "active"
                ? "border-accent text-accent"
                : state === "failed"
                  ? "border-warning text-warning"
                  : "border-muted text-muted-foreground",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {step}
        </div>
        <div className="flex flex-col gap-1">
          <p className="text-sm font-semibold text-foreground">{label}</p>
          {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
        </div>
      </div>
      <StatusPill label={state === "active" ? "In progress" : state === "pending" ? "Waiting" : state === "failed" ? "Action needed" : "Complete"} variant={meta.variant} />
      <div className="h-1 w-full rounded-full bg-muted">
        <div
          className={["h-full rounded-full transition-all", meta.connector]
            .filter(Boolean)
            .join(" ")}
          style={{
            width:
              state === "completed" ? "100%" : state === "active" ? "60%" : state === "failed" ? "35%" : "18%",
          }}
        />
      </div>
    </div>
  );
}
