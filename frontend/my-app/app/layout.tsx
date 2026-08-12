import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col font-sans">
        <header className="sticky top-0 z-10 border-b border-line bg-surface/80 backdrop-blur">
          <nav className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span
                aria-hidden
                className="grid h-7 w-7 place-items-center rounded-md bg-accent text-xs text-accent-contrast"
              >
                ST
              </span>
              Seat Booking
            </Link>
            <div className="flex items-center gap-1 text-sm">
              <Link
                href="/"
                className="rounded-lg px-3 py-1.5 text-muted transition hover:bg-surface-muted hover:text-foreground"
              >
                Events
              </Link>
              <Link
                href="/bookings"
                className="rounded-lg px-3 py-1.5 text-muted transition hover:bg-surface-muted hover:text-foreground"
              >
                My booking
              </Link>
              <Link
                href="/admin"
                className="rounded-lg border border-line px-3 py-1.5 font-medium transition hover:border-accent hover:text-accent"
              >
                Admin
              </Link>
            </div>
          </nav>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
          {children}
        </main>

        <footer className="border-t border-line px-4 py-5 text-center text-xs text-muted sm:px-6">
          Next.js + FastAPI + MySQL. Double-booking is prevented by a unique
          index on the active (event, seat) pair.
        </footer>
      </body>
    </html>
  );
}
