"use client";
import { useEffect, useRef, useState } from "react";
import { CircleHelp, Maximize2, RefreshCw, TerminalSquare } from "lucide-react";
import "@xterm/xterm/css/xterm.css";

export default function TerminalPanel({ target }: { target: { id: string; name: string } | null }) {
  const host = useRef<HTMLDivElement>(null);
  const term = useRef<any>(null);
  const socket = useRef<WebSocket | null>(null);
  const [state, setState] = useState("connecting");
  const [connectionKey, setConnectionKey] = useState(0);
  useEffect(() => {
    let alive = true;
    let fit: any;
    (async () => {
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");
      if (!alive || !host.current) return;
      const terminal = new Terminal({
        cursorBlink: true,
        fontFamily: "'SFMono-Regular', Consolas, monospace",
        fontSize: 13,
        theme: {
          background: "#0e1724",
          foreground: "#dce6f2",
          cursor: "#a9d469",
          selectionBackground: "#29415b",
          black: "#152131",
          green: "#80c99a",
          blue: "#82aaff",
          cyan: "#7cc9ce",
        },
        convertEol: true,
      });
      fit = new FitAddon();
      terminal.loadAddon(fit);
      terminal.open(host.current);
      fit.fit();
      term.current = terminal;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const suffix = target ? `?container_id=${encodeURIComponent(target.id)}` : "";
      const url = `${protocol}//${window.location.host}/api/terminal${suffix}`;
      const ws = new WebSocket(url);
      socket.current = ws;
      ws.onopen = () => {
        setState("connected");
        terminal.write(
          `\x1b[1;32mArfeen Cloud ${target ? "container" : "host"} terminal\x1b[0m\r\n${target ? `Container ${target.name} · /bin/sh` : "Authenticated Ubuntu host shell. Use with care."}\r\n\r\n`,
        );
        ws.send(`\u0000resize:${terminal.rows},${terminal.cols}`);
      };
      ws.onmessage = (e) => terminal.write(String(e.data));
      ws.onclose = () => setState("disconnected");
      ws.onerror = () => setState("connection error");
      terminal.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(data);
      });
      const resize = () => {
        fit.fit();
        if (ws.readyState === WebSocket.OPEN) ws.send(`\u0000resize:${terminal.rows},${terminal.cols}`);
      };
      window.addEventListener("resize", resize);
      (terminal as any).__cleanup = () => window.removeEventListener("resize", resize);
    })();
    return () => {
      alive = false;
      socket.current?.close();
      term.current?.__cleanup?.();
      term.current?.dispose();
    };
  }, [target?.id, target?.name, connectionKey]);
  return (
    <div className="page-body terminal-page">
      <div className="welcome-row">
        <div>
          <p className="page-kicker">SYSTEM / TERMINAL</p>
          <h1>{target ? target.name : "Host terminal"}</h1>
          <p className="muted">
            {target
              ? "Authenticated shell access to this Docker container."
              : "Authenticated shell access to your Ubuntu server."}
          </p>
        </div>
        <button
          className="button button-light"
          onClick={() => {
            socket.current?.close();
            setState("connecting");
            setConnectionKey((x) => x + 1);
          }}
        >
          <RefreshCw size={15} /> Reconnect
        </button>
      </div>
      <div className="terminal-notice">
        <CircleHelp size={15} />
        <span>
          {target
            ? "This shell runs inside the selected container."
            : "This is a root-level server shell. Commands run directly on the Ubuntu host."}
        </span>
      </div>
      <section className="terminal-frame">
        <header>
          <div className="terminal-window-dots">
            <i />
            <i />
            <i />
          </div>
          <span>
            <TerminalSquare size={14} />{" "}
            {state === "connected"
              ? target
                ? `${target.name}: /bin/sh`
                : "root@ubuntu-server: ~"
              : `Terminal ${state}`}
          </span>
          <Maximize2 size={14} />
        </header>
        <div className="terminal-screen" ref={host} />
      </section>
      <p className="terminal-foot">
        Session protected by your administrator login. Disconnect when you’re finished.
      </p>
    </div>
  );
}
