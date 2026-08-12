# Frontend — Event Seat Booking

Next.js 16 (App Router, Tailwind v4). Talks to the FastAPI backend in
[`../../backend`](../../backend).

```bash
npm install
cp .env.example .env.local     # NEXT_PUBLIC_API_BASE_URL -> the API
npm run dev                    # http://localhost:3000
```

| Script | |
|---|---|
| `npm run dev` | dev server |
| `npm run build` | production build |
| `npm run start` | serve the build |
| `npm run lint` | ESLint |
| `npx next typegen` | regenerate `PageProps`/`LayoutProps` route types |

| Path | |
|---|---|
| `app/` | routes — `/`, `/events/[id]`, `/bookings`, `/admin` |
| `components/` | `SeatMap` and shared UI primitives |
| `hooks/` | `usePolledResource`, `useSeatMap` |
| `lib/api.ts` | typed API client and `ApiError` |
| `DESIGN.md` | the design system this UI is styled to |

Design tokens live as CSS custom properties in `app/globals.css` and are exposed
to Tailwind through `@theme inline` — change a token there, not a hex in a
component.

`NEXT_PUBLIC_API_BASE_URL` is inlined into the client bundle at build time, so
changing it needs a rebuild.

Full setup, schema and concurrency notes: [the root README](../../README.md).
