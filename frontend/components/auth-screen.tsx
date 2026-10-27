"use client";
import { FormEvent, useEffect, useState } from "react";
import { Cloud, LockKeyhole, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";

export default function AuthScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [setupKey, setSetupKey] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ configured: boolean }>("/auth/status")
      .then((x) => setConfigured(x.configured))
      .catch(() => setConfigured(false));
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (configured)
        await api("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
      else
        await api("/auth/setup", {
          method: "POST",
          body: JSON.stringify({ username, password, setup_key: setupKey }),
        });
      onAuthenticated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <div className="auth-visual">
        <div className="auth-mark">
          <Cloud size={25} strokeWidth={1.7} />
          <span>
            ARFEEN <b>CLOUD</b>
          </span>
        </div>
        <div className="auth-visual-copy">
          <div className="live-indicator">
            <i /> PRIVATE INFRASTRUCTURE
          </div>
          <h1>
            Your server,
            <br />
            <em>in your hands.</em>
          </h1>
          <p>A single, secure control plane for the infrastructure you own.</p>
        </div>
        <div className="auth-visual-foot">
          <span>SELF-HOSTED BY DESIGN</span>
          <span>BUILD 01 · LOCAL NETWORK</span>
        </div>
      </div>
      <section className="auth-panel">
        <div className="auth-form-wrap">
          <div className="auth-small-brand">
            <Cloud size={22} />
            <span>ARFEEN CLOUD</span>
          </div>
          <div className="auth-icon">
            <LockKeyhole size={19} />
          </div>
          <span className="eyebrow">{configured === false ? "FIRST RUN" : "ADMINISTRATOR ACCESS"}</span>
          <h2>{configured === false ? "Set up your account" : "Welcome back"}</h2>
          <p className="auth-copy">
            {configured === false
              ? "Create the single administrator account for this server."
              : "Sign in to manage your private cloud."}
          </p>
          <form onSubmit={submit} className="auth-form">
            {configured === false && (
              <label>
                One-time setup key
                <input
                  value={setupKey}
                  onChange={(e) => setSetupKey(e.target.value)}
                  autoComplete="off"
                  required
                  minLength={16}
                  placeholder="From your installer output"
                />
              </label>
            )}
            <label>
              Administrator name
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                minLength={3}
                placeholder="Your username"
              />
            </label>
            <label>
              Password
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                autoComplete={configured ? "current-password" : "new-password"}
                required
                minLength={12}
                placeholder="At least 12 characters"
              />
            </label>
            {error && (
              <div className="form-error" role="alert">
                {error}
              </div>
            )}
            <button className="button button-primary auth-submit" disabled={busy || configured === null}>
              {busy ? "Please wait…" : configured === false ? "Create administrator" : "Sign in"}
              <span>↗</span>
            </button>
          </form>
          <div className="auth-assurance">
            <ShieldCheck size={15} />
            <span>Protected with an encrypted, HTTP-only session</span>
          </div>
          <div className="auth-footer">
            ARFEEN CLOUD <span>·</span> PRIVATE BY DEFAULT
          </div>
        </div>
      </section>
    </main>
  );
}
