import { Suspense } from "react";

import { AuthForm } from "@/components/AuthForm";
import { Spinner } from "@/components/ui";

export default function RegisterPage() {
  return (
    <Suspense fallback={<Spinner label="Loading" />}>
      <AuthForm mode="register" />
    </Suspense>
  );
}
