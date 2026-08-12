import { notFound } from "next/navigation";

import { EventBooking } from "./EventBooking";

export default async function EventPage({ params }: PageProps<"/events/[eventId]">) {
  // params is a Promise in Next.js 16.
  const { eventId } = await params;
  const id = Number(eventId);
  if (!Number.isInteger(id) || id <= 0) notFound();

  return <EventBooking eventId={id} />;
}
