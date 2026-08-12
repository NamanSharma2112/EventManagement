import { Suspense } from "react";

import { AuthForm } from "@/components/AuthForm";
import { Spinner } from "@/components/ui";

// useSearchParams needs a Suspense boundary so the page can still prerender.
export default function LoginPage() {
  return (
    <Suspense fallback={<Spinner label="Loading" />}>
      <AuthForm mode="login" />
    </Suspense>
  );
}
