"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Alert, Button, Card, Field, inputClass } from "@/components/ui";
import { ApiError } from "@/lib/api";

/** Only allow same-site relative paths back, so ?next= cannot be an open redirect. */
function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  return value;
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { signIn, signUp } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isRegister = mode === "register";
  const next = safeNext(searchParams.get("next"));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (isRegister) {
        await signUp(email.trim(), password, fullName.trim());
      } else {
        await signIn(email.trim(), password);
      }
      router.replace(next);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : isRegister
            ? "Could not create that account."
            : "Could not sign you in.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-md space-y-5">
      <header>
        <h1 className="display-xl text-ink">
          {isRegister ? "Create an account" : "Sign in"}
        </h1>
        <p className="mt-1 text-base text-muted">
          {isRegister
            ? "An account keeps your bookings together and lets only you cancel them."
            : "Bookings you make while signed in show up under your account."}
        </p>
      </header>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <Alert tone="danger">{error}</Alert>}

          {isRegister && (
            <Field label="Full name">
              <input
                className={inputClass}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Ada Lovelace"
                required
                maxLength={120}
                autoComplete="name"
              />
            </Field>
          )}

          <Field label="Email">
            <input
              className={inputClass}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
            />
          </Field>

          <Field label="Password" hint={isRegister ? "at least 8 characters" : undefined}>
            <input
              className={inputClass}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={isRegister ? 8 : 1}
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
          </Field>

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting
              ? isRegister
                ? "Creating account..."
                : "Signing in..."
              : isRegister
                ? "Create account"
                : "Sign in"}
          </Button>
        </form>
      </Card>

      <p className="text-center text-sm text-muted">
        {isRegister ? "Already have an account? " : "No account yet? "}
        <Link
          href={
            isRegister
              ? `/login?next=${encodeURIComponent(next)}`
              : `/register?next=${encodeURIComponent(next)}`
          }
          className="font-medium text-ink underline underline-offset-4"
        >
          {isRegister ? "Sign in" : "Create one"}
        </Link>
      </p>

      {!isRegister && (
        <Card className="bg-surface-soft">
          <p className="text-sm font-medium text-ink">Demo accounts</p>
          <dl className="mt-2 space-y-1 text-sm text-muted">
            <div className="flex justify-between gap-4">
              <dt>Admin</dt>
              <dd className="font-mono text-[13px]">admin@seatbook.dev / admin12345</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>User</dt>
              <dd className="font-mono text-[13px]">user@seatbook.dev / user12345</dd>
            </div>
          </dl>
          <p className="mt-2 text-[13px] text-muted">
            Created by <code>scripts/seed.py</code>. Booking a seat never requires
            signing in.
          </p>
        </Card>
      )}
    </div>
  );
}
