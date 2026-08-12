import { notFound } from "next/navigation";

import { AdminEventDashboard } from "./AdminEventDashboard";
import { RequireAuth } from "@/components/RequireAuth";

export default async function AdminEventPage({
  params,
}: PageProps<"/admin/events/[eventId]">) {
  const { eventId } = await params;
  const id = Number(eventId);
  if (!Number.isInteger(id) || id <= 0) notFound();

  return (
    <RequireAuth adminOnly redirectTo={`/admin/events/${id}`}>
      <AdminEventDashboard eventId={id} />
    </RequireAuth>
  );
}
