"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";

const linkClass =
  "rounded-full px-2 py-2 text-[13px] font-semibold transition hover:bg-surface-soft " +
  "sm:px-4 sm:py-2.5 sm:text-base";

export function NavAuth() {
  const { user, loading, isAdmin, signOut } = useAuth();
  const pathname = usePathname();

  return (
    <div className="flex items-center gap-0.5 sm:gap-1">
      <Link href="/" className={`${linkClass} text-ink`}>
        Events
      </Link>

      {/* Reserve the slot while the session resolves, so the nav does not jump. */}
      {loading ? (
        <span
          aria-hidden
          className="ml-1 h-9 w-24 animate-pulse rounded-full bg-surface-strong sm:h-11 sm:w-32"
        />
      ) : user ? (
        <>
          {isAdmin && (
            <Link href="/admin" className={`${linkClass} text-muted hover:text-ink`}>
              Admin
            </Link>
          )}
          <Link href="/account" className={`${linkClass} text-muted hover:text-ink`}>
            <span className="sm:hidden">Account</span>
            <span className="hidden sm:inline">
              {user.full_name.split(" ")[0] || "Account"}
            </span>
          </Link>
          <button
            type="button"
            onClick={signOut}
            className="ml-0.5 rounded-full border border-hairline px-2 py-2 text-[13px] font-semibold text-ink transition hover:shadow-tier sm:ml-1 sm:px-4 sm:py-2.5 sm:text-base"
          >
            Sign out
          </button>
        </>
      ) : (
        <>
          <Link href="/bookings" className={`${linkClass} text-muted hover:text-ink`}>
            <span className="sm:hidden">Booking</span>
            <span className="hidden sm:inline">My booking</span>
          </Link>
          <Link
            href={`/login?next=${encodeURIComponent(pathname)}`}
            className="ml-0.5 rounded-full border border-hairline px-2 py-2 text-[13px] font-semibold text-ink transition hover:shadow-tier sm:ml-1 sm:px-4 sm:py-2.5 sm:text-base"
          >
            Sign in
          </Link>
        </>
      )}
    </div>
  );
}
