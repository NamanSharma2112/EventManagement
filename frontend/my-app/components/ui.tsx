/** Small presentational building blocks shared by every page. */

import Link from "next/link";
import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-line bg-surface p-5 shadow-sm ${className}`}
    >
      {children}
    </div>
  );
}

export function StatTile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  tone?: "default" | "success" | "danger" | "accent";
}) {
  const toneClass = {
    default: "text-foreground",
    success: "text-success",
    danger: "text-danger",
    accent: "text-accent",
  }[tone];

  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${toneClass}`}>
        {value}
      </div>
    </div>
  );
}

export function Alert({
  tone,
  title,
  children,
}: {
  tone: "success" | "danger" | "warning" | "info";
  title?: string;
  children: ReactNode;
}) {
  const styles = {
    success: "border-success/40 bg-success-soft text-success",
    danger: "border-danger/40 bg-danger-soft text-danger",
    warning: "border-warning/40 bg-warning-soft text-warning",
    info: "border-accent/40 bg-accent-soft text-accent",
  }[tone];

  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${styles}`} role="status">
      {title && <p className="font-semibold">{title}</p>}
      <div className={title ? "mt-1" : ""}>{children}</div>
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  const variants = {
    primary:
      "bg-accent text-accent-contrast hover:opacity-90 disabled:opacity-40",
    secondary:
      "border border-line-strong bg-surface text-foreground hover:border-accent disabled:opacity-40",
    ghost: "text-muted hover:text-foreground disabled:opacity-40",
    danger:
      "border border-danger/40 bg-danger-soft text-danger hover:opacity-80 disabled:opacity-40",
  }[variant];

  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed ${variants} ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-foreground">{label}</span>
      {hint && <span className="ml-2 text-xs text-muted">{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-foreground " +
  "placeholder:text-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status">
      <span
        aria-hidden
        className="h-4 w-4 animate-spin rounded-full border-2 border-line-strong border-t-accent"
      />
      {label}
    </div>
  );
}

export function SeatSkeleton({ rows = 6, columns = 10 }) {
  return (
    <div className="space-y-2" aria-hidden>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-1.5">
          {Array.from({ length: columns }).map((__, c) => (
            <div
              key={c}
              className="h-7 w-7 animate-pulse rounded bg-surface-muted"
              style={{ animationDelay: `${(r * columns + c) * 12}ms` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: { href: string; label: string };
}) {
  return (
    <Card className="text-center">
      <p className="text-base font-semibold">{title}</p>
      {children && <p className="mt-1 text-sm text-muted">{children}</p>}
      {action && (
        <Link
          href={action.href}
          className="mt-4 inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-contrast"
        >
          {action.label}
        </Link>
      )}
    </Card>
  );
}

export function StatusPill({ status }: { status: "CONFIRMED" | "CANCELLED" }) {
  return status === "CONFIRMED" ? (
    <span className="inline-flex rounded-full border border-success/40 bg-success-soft px-2 py-0.5 text-xs font-medium text-success">
      Confirmed
    </span>
  ) : (
    <span className="inline-flex rounded-full border border-line-strong bg-surface-muted px-2 py-0.5 text-xs font-medium text-muted">
      Cancelled
    </span>
  );
}
