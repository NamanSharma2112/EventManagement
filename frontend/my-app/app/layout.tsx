import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import Link from "next/link";

import "./globals.css";

// DESIGN.md runs Airbnb Cereal VF and names Inter as the closest open-source
// substitute; the proportions transfer cleanly.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Seat Booking",
  description:
    "Browse events, pick your seats and book them - with double-booking prevented in the database.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col font-sans">
        {/* top-nav: white surface, 80px tall, single bottom hairline. */}
        <header className="sticky top-0 z-10 border-b border-hairline bg-canvas">
          {/* 80px at desktop, tightened to 64px on mobile. DESIGN.md's nav
              collapses to a hamburger sheet below 744px; with three links a
              sheet is overkill, so the labels shrink and "My booking" drops to
              "Booking" instead. */}
          <nav className="mx-auto flex h-16 w-full max-w-[1280px] items-center justify-between gap-2 px-4 sm:h-20 sm:gap-4 sm:px-6 lg:px-10">
            <Link
              href="/"
              className="flex shrink-0 items-center gap-2 text-primary"
              aria-label="Seat Booking home"
            >
              <svg
                aria-hidden
                viewBox="0 0 24 24"
                className="h-6 w-6 sm:h-7 sm:w-7"
                fill="currentColor"
              >
                <path d="M5 11V8a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v3a2 2 0 0 1 2 2v4a1 1 0 0 1-1 1h-1v1a1 1 0 1 1-2 0v-1H7v1a1 1 0 1 1-2 0v-1H4a1 1 0 0 1-1-1v-4a2 2 0 0 1 2-2Zm2 0h10V8a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v3Z" />
              </svg>
              <span className="text-base font-bold tracking-tight text-ink sm:text-lg">
                seatbook
              </span>
            </Link>

            <div className="flex items-center gap-0.5 sm:gap-1">
              <Link
                href="/"
                className="rounded-full px-2 py-2 text-[13px] font-semibold text-ink transition hover:bg-surface-soft sm:px-4 sm:py-2.5 sm:text-base"
              >
                Events
              </Link>
              <Link
                href="/bookings"
                className="rounded-full px-2 py-2 text-[13px] font-semibold text-muted transition hover:bg-surface-soft hover:text-ink sm:px-4 sm:py-2.5 sm:text-base"
              >
                <span className="sm:hidden">Booking</span>
                <span className="hidden sm:inline">My booking</span>
              </Link>
              <Link
                href="/admin"
                className="ml-0.5 rounded-full border border-hairline px-2 py-2 text-[13px] font-semibold text-ink transition hover:shadow-tier sm:ml-1 sm:px-4 sm:py-2.5 sm:text-base"
              >
                Admin
              </Link>
            </div>
          </nav>
        </header>

        <main className="mx-auto w-full max-w-[1280px] flex-1 px-6 py-10 lg:px-10 lg:py-14">
          {children}
        </main>

        <footer className="border-t border-hairline px-6 py-8 lg:px-10">
          <p className="mx-auto max-w-[1280px] text-[13px] text-muted">
            Next.js + FastAPI + MySQL. Double-booking is prevented by a unique
            index on the active (event, seat) pair.
          </p>
        </footer>
      </body>
    </html>
  );
}
