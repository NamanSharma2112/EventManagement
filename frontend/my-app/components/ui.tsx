/**
 * Presentational building blocks, styled to DESIGN.md (Airbnb-design-analysis).
 *
 * Shape scale: buttons 8px (rounded-sm), cards 14px (rounded-md), badges full.
 * Elevation is a single tier (`shadow-tier`) applied on hover-float and nowhere
 * else. Rausch is the only accent and is reserved for primary CTAs.
 */

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
      className={`rounded-md border border-hairline bg-canvas p-6 ${className}`}
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
    default: "text-ink",
    success: "text-success",
    danger: "text-error",
    accent: "text-primary",
  }[tone];

  return (
    <div className="rounded-md border border-hairline bg-canvas px-5 py-4">
      <div className="uppercase-tag text-muted">{label}</div>
      <div className={`mt-1.5 text-[26px] font-bold leading-tight tabular-nums ${toneClass}`}>
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
    success: "border-success/25 bg-success-soft text-success",
    danger: "border-error/25 bg-error-soft text-error",
    warning: "border-warning/25 bg-warning-soft text-warning",
    info: "border-primary/25 bg-canvas text-primary",
  }[tone];

  return (
    <div className={`rounded-sm border px-4 py-3.5 text-sm ${styles}`} role="status">
      {title && <p className="title-md">{title}</p>}
      <div className={title ? "mt-1 leading-relaxed" : "leading-relaxed"}>{children}</div>
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
  // 48px tall, 8px radius, weight 500 -- button-primary in DESIGN.md.
  const base =
    "inline-flex h-12 items-center justify-center gap-2 rounded-sm px-6 text-base " +
    "font-medium transition disabled:cursor-not-allowed";

  const variants = {
    primary:
      "bg-primary text-on-primary hover:bg-primary-active " +
      "disabled:bg-primary-disabled disabled:text-on-primary",
    secondary:
      "border border-ink bg-canvas text-ink hover:bg-surface-soft " +
      "disabled:border-border-strong disabled:text-muted-soft disabled:hover:bg-canvas",
    ghost:
      "px-2 text-ink underline-offset-4 hover:underline disabled:text-muted-soft " +
      "disabled:hover:no-underline",
    danger:
      "border border-error bg-canvas text-error hover:bg-error-soft " +
      "disabled:border-border-strong disabled:text-muted-soft",
  }[variant];

  return (
    <button {...props} className={`${base} ${variants} ${className}`}>
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
      <span className="text-sm font-medium text-ink">{label}</span>
      {hint && <span className="ml-2 text-[13px] text-muted">{hint}</span>}
      <div className="mt-2">{children}</div>
    </label>
  );
}

/**
 * text-input: 56px tall, 8px radius, hairline outline. On focus the border
 * thickens to 2px ink -- no glow, no ring (DESIGN.md, Forms).
 */
export const inputClass =
  "h-14 w-full rounded-sm border border-hairline bg-canvas px-3.5 text-base text-ink " +
  "placeholder:text-muted-soft focus:border-2 focus:border-ink focus:px-[13px] " +
  "focus:outline-none";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 text-sm text-muted" role="status">
      <span
        aria-hidden
        className="h-4 w-4 animate-spin rounded-full border-2 border-hairline border-t-primary"
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
              className="h-7 w-7 animate-pulse rounded-xs bg-surface-strong"
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
      <p className="display-sm">{title}</p>
      {children && <p className="mt-2 text-sm text-muted">{children}</p>}
      {action && (
        <Link
          href={action.href}
          className="mt-5 inline-flex h-12 items-center rounded-sm bg-primary px-6 text-base font-medium text-on-primary transition hover:bg-primary-active"
        >
          {action.label}
        </Link>
      )}
    </Card>
  );
}

export function StatusPill({ status }: { status: "CONFIRMED" | "CANCELLED" }) {
  return status === "CONFIRMED" ? (
    <span className="inline-flex rounded-full border border-success/25 bg-success-soft px-2.5 py-1 text-[11px] font-semibold text-success">
      Confirmed
    </span>
  ) : (
    <span className="inline-flex rounded-full border border-hairline bg-surface-strong px-2.5 py-1 text-[11px] font-semibold text-muted">
      Cancelled
    </span>
  );
}
