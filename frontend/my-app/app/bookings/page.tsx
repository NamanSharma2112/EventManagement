"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Card, Field, inputClass } from "@/components/ui";

export default function BookingLookupPage() {
  const router = useRouter();
  const [reference, setReference] = useState("");

  return (
    <div className="mx-auto max-w-md space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Find your booking</h1>
        <p className="mt-1 text-sm text-muted">
          Enter the reference from your confirmation, e.g. BK-A1B2C3D4.
        </p>
      </header>

      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = reference.trim().toUpperCase();
            if (trimmed) router.push(`/bookings/${encodeURIComponent(trimmed)}`);
          }}
          className="space-y-4"
        >
          <Field label="Booking reference">
            <input
              className={`${inputClass} font-mono uppercase`}
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              placeholder="BK-XXXXXXXX"
              required
              autoFocus
            />
          </Field>
          <Button type="submit" className="w-full">
            Look up booking
          </Button>
        </form>
      </Card>
    </div>
  );
}
