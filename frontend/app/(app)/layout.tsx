import { Suspense, type ReactNode } from "react";
import { AppShell } from "@/components/layout/app-shell";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex h-dvh items-center justify-center bg-terminal-bg text-sm text-terminal-muted">
          Loading terminal...
        </div>
      }
    >
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
