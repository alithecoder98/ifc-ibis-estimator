"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCurrentUser } from "@/lib/auth/use-current-user";
import { useLogout } from "@/lib/auth/use-logout";

// Client-side route protection: GET /auth/me decides whether to render. The real
// security boundary is the backend (401/403 on every protected endpoint) — this just
// avoids flashing protected UI before redirecting an unauthenticated visitor to /login.
export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { data: user, isLoading, isError } = useCurrentUser();
  const logout = useLogout();

  useEffect(() => {
    if (isError) router.replace("/login");
  }, [isError, router]);

  if (isLoading || !user) {
    return (
      <div className="text-muted-foreground flex min-h-screen items-center justify-center">
        Loading...
      </div>
    );
  }

  function handleLogout() {
    logout.mutate(undefined, { onSuccess: () => router.push("/login") });
  }

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r p-4">
        <nav className="space-y-1">
          <Link
            href="/projects"
            className="hover:bg-muted block rounded px-3 py-2"
          >
            Projects
          </Link>
          {user.role === "admin" && (
            <Link
              href="/admin"
              className="hover:bg-muted block rounded px-3 py-2"
            >
              Admin
            </Link>
          )}
        </nav>
      </aside>
      <div className="flex-1">
        <header className="flex items-center justify-end border-b p-4">
          <DropdownMenu>
            {/* Base UI (not Radix) under this shadcn version: composition is via
                `render`, not `asChild`. */}
            <DropdownMenuTrigger
              render={
                <Button variant="ghost" className="flex items-center gap-2">
                  <Avatar className="h-6 w-6">
                    <AvatarFallback>
                      {user.email[0]?.toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  {user.email}
                </Button>
              }
            />
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={handleLogout}>
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}
