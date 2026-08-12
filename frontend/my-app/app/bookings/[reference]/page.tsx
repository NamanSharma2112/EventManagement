import { BookingDetail } from "./BookingDetail";

export default async function BookingPage({
  params,
}: PageProps<"/bookings/[reference]">) {
  const { reference } = await params;
  return <BookingDetail reference={decodeURIComponent(reference)} />;
}
