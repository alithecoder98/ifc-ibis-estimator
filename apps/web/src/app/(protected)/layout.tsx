"use client";

import { Building2, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/lib/auth/use-current-user";

// Client-side route protection: GET /auth/me decides whether to render. The real
// security boundary is the backend (401/403 on every protected endpoint) — this just
// avoids flashing protected UI before redirecting an unauthenticated visitor to /login.
export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: user, isLoading, isError } = useCurrentUser();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    if (isError) router.replace("/login");
  }, [isError, router]);

  // The fixed-width w-56 sidebar was permanently visible before, eating most
  // of a phone's viewport and pushing real content (and the Elements table's
  // own columns) off-screen with no way to reach it - confirmed live at
  // 375px: the Elements tab overflowed the page by 1000px+. Closing on route
  // change matches the usual mobile-drawer pattern (navigating implies the
  // user is done with the menu).
  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  if (isLoading || !user) {
    return (
      <div className="flex min-h-screen">
        <aside className="hidden w-56 shrink-0 border-r p-4 md:block">
          <Skeleton className="h-8 w-32" />
        </aside>
        <div className="min-w-0 flex-1 p-6">
          <Skeleton className="h-8 w-48" />
        </div>
      </div>
    );
  }

  const navLinkClass = (href: string) => {
    const active = pathname === href || pathname?.startsWith(`${href}/`);
    return active
      ? "bg-sidebar-accent text-sidebar-accent-foreground block rounded px-3 py-2 font-medium"
      : "text-sidebar-foreground hover:bg-sidebar-accent/60 block rounded px-3 py-2";
  };

  return (
    <div className="flex min-h-screen">
      {/* Backdrop - mobile only, closes the drawer on outside click */}
      {mobileNavOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        className={`bg-sidebar border-sidebar-border fixed inset-y-0 left-0 z-50 flex w-56 shrink-0 flex-col border-r p-4 transition-transform md:static md:translate-x-0 ${
          mobileNavOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-6 flex items-center justify-between gap-2 px-3">
          <div className="flex items-center gap-2">
            <div className="bg-primary text-primary-foreground flex h-8 w-8 items-center justify-center rounded-lg">
              <Building2 className="h-4.5 w-4.5" />
            </div>
            <span className="font-heading text-sidebar-foreground text-sm font-semibold tracking-tight">
              IBIS Estimator
            </span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setMobileNavOpen(false)}
            aria-label="Close navigation"
          >
            <X className="size-4" />
          </Button>
        </div>
        <nav className="space-y-1">
          <Link href="/projects" className={navLinkClass("/projects")}>
            Projects
          </Link>
          {user.role === "admin" && (
            <Link href="/admin" className={navLinkClass("/admin")}>
              Admin
            </Link>
          )}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="bg-background/80 flex items-center border-b p-4 backdrop-blur-sm">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="size-4" />
          </Button>
        </header>
        <main className="min-w-0 p-6">{children}</main>
      </div>
    </div>
  );
}
