import Link from "next/link";
import type { LucideIcon } from "lucide-react";

interface PageStubProps {
  title: string;
  description: string;
  phase: string;
  icon: LucideIcon;
}

/** Shared shell for routes that light up in later phases. */
export function PageStub({ title, description, phase, icon: Icon }: PageStubProps) {
  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <div className="w-full max-w-lg rounded-lg border border-terminal-border bg-terminal-panel p-8 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-md bg-terminal-surface text-terminal-accent">
          <Icon className="h-6 w-6" strokeWidth={1.5} />
        </div>
        <h1 className="mt-4 font-display text-xl font-semibold text-terminal-text">{title}</h1>
        <p className="mt-2 text-sm text-terminal-muted">{description}</p>
        <p className="mt-4 text-[11px] uppercase tracking-[0.18em] text-terminal-accent">{phase}</p>
        <Link
          href="/dashboard"
          className="mt-6 inline-block text-sm text-terminal-accent hover:underline"
        >
          Back to Overview
        </Link>
      </div>
    </div>
  );
}
