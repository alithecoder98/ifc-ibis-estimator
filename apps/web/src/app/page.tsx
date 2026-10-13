import { redirect } from "next/navigation";

// Always send "/" into the protected area - its layout checks auth itself (GET
// /auth/me) and redirects to /login on a 401. Going here instead of straight to
// /login means an already-authenticated visit (or AUTH_DISABLED dev mode, see
// apps/api/app/core/deps.py) never sees a login screen at all.
export default function Home() {
  redirect("/projects");
}
