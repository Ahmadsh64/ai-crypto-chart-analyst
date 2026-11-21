"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/auth-provider";

/** Gate app routes when Supabase Auth is configured. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { configured, loading, session } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!configured || loading) return;
    if (!session) {
      const next = encodeURIComponent(pathname || "/dashboard");
      router.replace(`/login?next=${next}`);
    }
  }, [configured, loading, session, router, pathname]);

  if (!configured) {
    return <>{children}</>;
  }

  if (loading || !session) {
    return (
      <div className="flex h-dvh items-center justify-center bg-terminal-bg text-sm text-terminal-muted">
        Checking session…
      </div>
    );
  }

  return <>{children}</>;
}
