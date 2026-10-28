/** Apps currently use HTTP, independently of the dashboard's HTTPS termination. */
export function applicationUrl(app: { domain?: string | null; host_port?: number | null }, hostname: string): string | null {
  if (app.domain) return `http://${app.domain}`;
  if (!app.host_port || !hostname) return null;
  const host = hostname.includes(":") && !hostname.startsWith("[") ? `[${hostname}]` : hostname;
  return `http://${host}:${app.host_port}`;
}
