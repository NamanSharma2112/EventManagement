"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Alert, Spinner } from "@/components/ui";

/**
 * Client-side gate for account and admin pages.
 *
 * This is a convenience, not a security boundary -- it hides UI the user
 * cannot act on and sends them somewhere useful. The real check is on the API,
 * which re-validates the token and the role on every admin request, so editing
 * this component in devtools gets an attacker a rendered page and a wall of
 * 401s and 403s.
 */
export function RequireAuth({
  children,
  adminOnly = false,
  redirectTo,
}: {
  children: React.ReactNode;
  adminOnly?: boolean;
  redirectTo: string;
}) {
  const { user, loading, isAdmin } = useAuth();
  const router = useRouter();

  const allowed = user !== null && (!adminOnly || isAdmin);
  const mustSignIn = !loading && user === null;

  useEffect(() => {
    if (mustSignIn) {
      router.replace(`/login?next=${encodeURIComponent(redirectTo)}`);
    }
  }, [mustSignIn, redirectTo, router]);

  if (loading) return <Spinner label="Checking your session" />;
  if (mustSignIn) return <Spinner label="Redirecting to sign in" />;

  if (!allowed) {
    return (
      <Alert tone="danger" title="Admins only">
        You are signed in as {user?.email}, which is not an admin account. Sign
        in with an admin account to manage events.
      </Alert>
    );
  }

  return <>{children}</>;
}
