export type ServerMetrics = {
  hostname: string;
  platform: string;
  uptime_seconds: number;
  timestamp: string;
  cpu_percent: number;
  cpu_count: number;
  memory: { total: number; used: number; percent: number };
  disk: { total: number; used: number; free: number; percent: number };
  network: { rx_bytes_sec: number; tx_bytes_sec: number };
  temperature_c: number | null;
  process_count: number;
  load_average: number[];
  docker: { available: boolean; version?: string; containers?: number; error?: string };
};
export type Container = {
  id: string;
  full_id: string;
  name: string;
  image: string;
  status: string;
  system?: boolean;
  ports: { container: string; host: string }[];
};
export type AppRecord = {
  id: string;
  name: string;
  source: string;
  source_type?: "github" | "github-private" | "zip";
  source_ref?: string;
  framework: string;
  port: number;
  host_port: number | null;
  status: string;
  container_id: string;
  image: string;
  domain: string | null;
  created_at: string;
};
export type DatabaseRecord = {
  id: string;
  name: string;
  engine: string;
  status: string;
  username: string;
  port: number;
  connection_host: string;
  created_at: string;
};
