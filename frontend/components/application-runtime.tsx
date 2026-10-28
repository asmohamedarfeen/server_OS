"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, Copy, ExternalLink, Pause, Play, TerminalSquare, X } from "lucide-react";
import { api } from "@/lib/api";
import { applicationUrl } from "@/lib/application-url";
import { AppRecord } from "@/lib/types";

export function ApplicationEndpoint({ app, notify }: {
  app: AppRecord; notify: (message: string, kind?: "success" | "error") => void;
}) {
  const [hostname, setHostname] = useState("");
  useEffect(() => setHostname(window.location.hostname), []);
  const url = applicationUrl(app, hostname);
  async function copy() {
    if (!url) return;
    try { await navigator.clipboard.writeText(url); notify("Application URL copied"); }
    catch { notify("Could not copy URL. Select and copy the address instead.", "error"); }
  }
  return <div className="application-endpoint">
    <span className="application-endpoint-label">Application URL</span>
    <div className="app-card-url">
      {url ? <>
        <a href={url} target="_blank" rel="noreferrer" title={url}>{url}</a>
        <button className="icon-button" aria-label="Copy application URL" title="Copy application URL" onClick={copy}><Copy size={14} /></button>
        <a className="icon-button" href={url} target="_blank" rel="noreferrer" aria-label="Open application" title="Open application"><ExternalLink size={14} /></a>
      </> : <span>{app.host_port ? "Resolving application URL…" : "No application endpoint configured"}</span>}
    </div>
  </div>;
}

type RuntimeOutput = { logs: string; status: string; container_id: string };

export function ApplicationRuntime({ app, onClose }: { app: AppRecord; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const [output, setOutput] = useState<RuntimeOutput | null>(null);
  const [error, setError] = useState("");
  const [paused, setPaused] = useState(false);
  const [follow, setFollow] = useState(true);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [copyError, setCopyError] = useState("");
  const [copied, setCopied] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const lastScrollTop = useRef(0);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.showModal();
    setUrl(applicationUrl(app, window.location.hostname));
    return () => { document.body.style.overflow = overflow; previous?.focus(); };
  }, [app]);

  useEffect(() => {
    if (paused) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController;
    async function poll() {
      request = new AbortController();
      const timeout = setTimeout(() => request.abort(), 12000);
      try {
        const data = await api<RuntimeOutput>(`/apps/${app.id}/logs?tail=2000`, { signal: request.signal });
        if (stopped) return;
        setOutput(data); setUpdated(new Date()); setError("");
      } catch (e) {
        if (stopped) return;
        setError(e instanceof Error && e.name !== "AbortError" ? e.message : "Log request timed out");
      } finally {
        clearTimeout(timeout);
        if (!stopped) timer = setTimeout(poll, 2000);
      }
    }
    poll();
    return () => { stopped = true; clearTimeout(timer); request?.abort(); };
  }, [app.id, paused]);

  useEffect(() => {
    if (follow && scroll.current) {
      scroll.current.scrollTop = scroll.current.scrollHeight;
      lastScrollTop.current = scroll.current.scrollTop;
    }
  }, [output, follow]);

  async function copyLogs() {
    try { await navigator.clipboard.writeText(output?.logs || ""); setCopied(true); setCopyError(""); }
    catch { setCopyError("Could not copy logs. Use Download logs instead."); }
  }
  function download() {
    const blobUrl = URL.createObjectURL(new Blob([output?.logs || ""], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = blobUrl; link.download = `${app.name}-runtime.log`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
  }

  return <dialog ref={dialog} className="deployment-console runtime-console" aria-labelledby="runtime-title" onCancel={onClose}>
    <header className="deployment-console-heading">
      <div className="deployment-console-icon"><TerminalSquare size={21} /></div>
      <div className="deployment-console-title"><p>APPLICATION OUTPUT</p><h2 id="runtime-title">Application logs · {app.name}</h2></div>
      <button className="icon-button" aria-label="Close application logs" onClick={onClose}><X size={19} /></button>
    </header>
    <div className="runtime-details">
      <span>Container <strong>{output?.status || "Connecting…"}</strong></span>
      {url && <a href={url} target="_blank" rel="noreferrer">Open application <ExternalLink size={13} /></a>}
    </div>
    <div className="deployment-output runtime-output">
      <div className="deployment-output-toolbar">
        <span><i className={!paused && !error && updated ? "live" : ""} />{paused ? "UPDATES PAUSED" : error ? "RECONNECTING" : updated ? "LIVE · EVERY 2 SECONDS" : "CONNECTING"}</span>
        <div className="deployment-log-actions">
          <button className="deployment-latest" onClick={() => setPaused(!paused)}>{paused ? <Play size={12} /> : <Pause size={12} />}{paused ? "Resume updates" : "Pause updates"}</button>
          <label><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />Follow logs</label>
        </div>
      </div>
      {error && <div className="deployment-connection-warning" role="alert">{error}. {paused ? "Resume updates to retry." : "Retrying automatically. Previous output is retained."}</div>}
      {copyError && <div className="deployment-connection-warning" role="alert">{copyError}</div>}
      <div ref={scroll} className="deployment-log" role="log" aria-label="Application runtime output" aria-live="off" tabIndex={0}
        onWheel={(event) => { if (event.deltaY < 0) setFollow(false); }}
        onKeyDown={(event) => { if (["ArrowUp", "PageUp", "Home"].includes(event.key)) setFollow(false); }}
        onScroll={(event) => {
          const panel = event.currentTarget;
          if (panel.scrollTop < lastScrollTop.current) setFollow(false);
          lastScrollTop.current = panel.scrollTop;
        }}>
        <pre className="runtime-log-text">{output ? output.logs || "No application output yet. Logs appear when the app writes to stdout or stderr." : "Connecting to application logs…"}</pre>
      </div>
    </div>
    <footer className="deployment-console-footer">
      <span>Latest 2,000 lines · stdout + stderr{updated && ` · Updated ${updated.toLocaleTimeString()}`}</span>
      <div>
        <button className="button button-light" disabled={!output} onClick={copyLogs}><Copy size={14} />{copied ? "Copied" : "Copy logs"}</button>
        <button className="button button-light" disabled={!output} onClick={download}><ArrowDownToLine size={14} />Download logs</button>
        <button className="button button-primary" onClick={onClose}>Done</button>
      </div>
    </footer>
  </dialog>;
}
