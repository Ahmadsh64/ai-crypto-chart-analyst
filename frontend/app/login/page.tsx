"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/providers/auth-provider";

function LoginForm() {
  const { configured, loading, session, signIn } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/dashboard";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && session) {
      router.replace(next.startsWith("/") ? next : "/dashboard");
    }
  }, [loading, session, router, next]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const result = await signIn(email.trim(), password);
    setSubmitting(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    router.replace(next.startsWith("/") ? next : "/dashboard");
  }

  if (!configured) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-terminal-bg px-4">
        <div className="max-w-md text-center text-sm text-terminal-muted">
          Supabase Auth is not configured. Set{" "}
          <code className="text-terminal-text">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code className="text-terminal-text">NEXT_PUBLIC_SUPABASE_ANON_KEY</code>{" "}
          for production login.
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-terminal-bg px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 border border-terminal-border bg-terminal-panel p-6"
      >
        <div>
          <h1 className="font-display text-lg font-semibold text-terminal-text">
            Sign in
          </h1>
          <p className="mt-1 text-xs text-terminal-muted">
            Personal access — authorized email only.
          </p>
        </div>
        <label className="block space-y-1 text-xs text-terminal-muted">
          Email
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border border-terminal-border bg-terminal-bg px-3 py-2 text-sm text-terminal-text outline-none focus:border-terminal-accent"
          />
        </label>
        <label className="block space-y-1 text-xs text-terminal-muted">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border border-terminal-border bg-terminal-bg px-3 py-2 text-sm text-terminal-text outline-none focus:border-terminal-accent"
          />
        </label>
        {error ? (
          <p className="text-xs text-red-400" role="alert">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={submitting || loading}
          className="w-full bg-terminal-accent px-3 py-2 text-sm font-medium text-terminal-bg disabled:opacity-60"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-dvh items-center justify-center bg-terminal-bg text-sm text-terminal-muted">
          Loading…
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
