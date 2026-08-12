import { notFound } from "next/navigation";

import { AdminEventDashboard } from "./AdminEventDashboard";

export default async function AdminEventPage({
  params,
}: PageProps<"/admin/events/[eventId]">) {
  const { eventId } = await params;
  const id = Number(eventId);
  if (!Number.isInteger(id) || id <= 0) notFound();

  return <AdminEventDashboard eventId={id} />;
}
