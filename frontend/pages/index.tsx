"use client";
import { useState, useRef, useEffect, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";
import { BACKEND_BASE, WS_BASE } from "../config/config";
import { Play, StopCircle, Trash2, Zap, AlertCircle, BarChart3 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

// ---------- Types ----------
export type SimulationConfig = {
  runtime_seconds: number;
  num_tenants: number;
  cluster_nodes: number;
  per_node_cpu: number;
  per_node_ram: number;
  per_node_gpus: number;
  arrival_model: "poisson" | "fixed";
  arrival_rate: number;
  duration_range: [number, number];
  cpu_request_range: [number, number];
  ram_request_range: [number, number];
  gpu_request_range: [number, number];
  priority_distribution: { low: number; med: number; high: number };
  scheduler_choice: "fifo" | "stf"; // RL removed
  preemption_enabled: boolean;
};

type LiveUpdate = {
  time: number | string;
  queue_len: number;
  completed_jobs: number;
  cpu_util: number; // 0-100
};

// ---------- Component ----------
export default function Home() {
  // canonical defaults used when building the final config on submit
  const [configDefaults] = useState<SimulationConfig>({
    runtime_seconds: 300,
    num_tenants: 2,
    cluster_nodes: 1,
    per_node_cpu: 2,
    per_node_ram: 2048,
    per_node_gpus: 0,
    arrival_model: "poisson",
    arrival_rate: 6,
    duration_range: [20, 40],
    cpu_request_range: [1, 2],
    ram_request_range: [1024, 2048],
    gpu_request_range: [0, 0],
    priority_distribution: { low: 0.3, med: 0.5, high: 0.2 },
    scheduler_choice: "fifo",
    preemption_enabled: false,
  });

  // string-based form so backspacing doesn't snap to 0
  const [form, setForm] = useState({
    runtime_seconds: String(configDefaults.runtime_seconds),
    num_tenants: String(configDefaults.num_tenants),
    arrival_rate: String(configDefaults.arrival_rate),
    duration_lower: String(configDefaults.duration_range[0]),
    duration_upper: String(configDefaults.duration_range[1]),
    scheduler_choice: configDefaults.scheduler_choice as "fifo" | "stf",
  });

  const [data, setData] = useState<LiveUpdate[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<any | null>(null);
  const [loadingResults, setLoadingResults] = useState(false);
  const [showCharts, setShowCharts] = useState(false); // controls chart visibility + animation
  const [receivedTick, setReceivedTick] = useState(false); // first data point arrived
  const [hasEnded, setHasEnded] = useState(false); // sim ended
  const [restored, setRestored] = useState(false); // refreshed from persisted state
  const socketRef = useRef<WebSocket | null>(null);

  // ---------- Validation ----------
  type Errors = Partial<Record<keyof typeof form, string>> & { duration_pair?: string };

  const errors: Errors = useMemo(() => {
    const e: Errors = {};
    const toNum = (s: string) => (s.trim() === "" ? NaN : Number(s));

    const rt = toNum(form.runtime_seconds);
    if (isNaN(rt)) e.runtime_seconds = "Required";
    else if (rt <= 0) e.runtime_seconds = "Must be > 0";

    const ten = toNum(form.num_tenants);
    if (isNaN(ten)) e.num_tenants = "Required";
    else if (!Number.isInteger(ten) || ten <= 0) e.num_tenants = "Must be integer > 0";

    const ar = toNum(form.arrival_rate);
    if (isNaN(ar)) e.arrival_rate = "Required";
    else if (ar <= 0) e.arrival_rate = "Must be > 0";

    const dL = toNum(form.duration_lower);
    const dU = toNum(form.duration_upper);
    if (isNaN(dL) || isNaN(dU)) e.duration_pair = "Both durations required";
    else if (dL < 0 || dU < 0) e.duration_pair = "Must be ≥ 0";
    else if (dL > dU) e.duration_pair = "Lower must be ≤ upper";

    return e;
  }, [form]);

  const isValid = useMemo(() => Object.keys(errors).length === 0, [errors]);
  const timeTick = (t: any) => `${t}s`;
  const onField = (key: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [key]: v }));

  // derived UI flags
  const hasHistory = data.length > 0;
  const hasResults = !!(results && results.throughput && Object.keys(results.throughput || {}).length > 0);
  const canShowResults = !isRunning && hasResults && (hasEnded || restored);

  const startSimulation = async () => {
    if (!isValid) return; // double guard

    const n = (s: string) => Number(s.trim());
    const finalConfig: SimulationConfig = {
      ...configDefaults,
      runtime_seconds: n(form.runtime_seconds),
      num_tenants: n(form.num_tenants),
      arrival_rate: n(form.arrival_rate),
      duration_range: [n(form.duration_lower), n(form.duration_upper)],
      scheduler_choice: form.scheduler_choice,
    };

    setResults(null);
    setData([]);
    setShowCharts(true); // reveal charts smoothly
    setReceivedTick(false);
    setHasEnded(false);
    setRestored(false);

    await fetch(`${BACKEND_BASE}/start-simulation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(finalConfig),
    });

    setIsRunning(true);

    const socket = new WebSocket(`${WS_BASE}/ws/simulation`);
    socketRef.current = socket;

    socket.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data) as LiveUpdate;
        setReceivedTick(true); // mark as soon as first tick arrives
        setData((prev) => [...prev, update]);
      } catch (err) {
        console.error("Bad WS payload:", err);
      }
    };

    socket.onerror = (e) => console.error("WebSocket error:", e);

    socket.onclose = async () => {
      setIsRunning(false);
      setHasEnded(true);
      setLoadingResults(true);
      try {
        const res = await fetch(`${BACKEND_BASE}/results`);
        const finalResults = await res.json();
        setResults(finalResults && finalResults.throughput ? finalResults : null);
      } catch (err) {
        console.error("Error fetching results:", err);
      } finally {
        setLoadingResults(false);
      }
    };
  };

  const stopSimulation = async () => {
    try {
      await fetch(`${BACKEND_BASE}/stop-simulation`, { method: "POST" });
    } finally {
      socketRef.current?.close();
    }
  };

  const clearResults = async () => {
    try {
      await fetch(`${BACKEND_BASE}/clear-results`, { method: "POST" });
      setData([]);
      setResults(null);
      setShowCharts(false); // hide charts until next run
      setReceivedTick(false);
      setHasEnded(false);
      setRestored(false);
    } catch (err) {
      console.error("Error clearing results:", err);
    }
  };

  // Persisted state load: if server has history/results, restore graphs & results and hydrate flags
  useEffect(() => {
    const fetchPersisted = async () => {
      try {
        const resResults = await fetch(`${BACKEND_BASE}/results`);
        const persistedResults = await resResults.json();
        const hasRes = !!(persistedResults && persistedResults.throughput);

        const resData = await fetch(`${BACKEND_BASE}/history`);
        const persistedData = await resData.json();
        const hasHist = Array.isArray(persistedData) && persistedData.length > 0;

        if (hasHist) {
          setData(persistedData);
          setShowCharts(true);
          setReceivedTick(true); // we must have received ticks previously
        } else {
          setData([]);
          setShowCharts(false);
        }

        setResults(hasRes ? persistedResults : null);

        if (hasHist || hasRes) {
          setHasEnded(true); // last run already ended
          setRestored(true); // unlock results rendering after refresh
        }
      } catch (err) {
        console.error("Error fetching persisted data:", err);
      }
    };

    fetchPersisted();
    return () => {
      try {
        socketRef.current?.close();
      } catch {}
      socketRef.current = null;
    };
  }, []);

  // ---------- UI ----------
  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* Title */}
      <div className="flex items-center gap-2 mb-6">
        <Zap size={24} className="text-yellow-500" />
        <h1 className="text-3xl font-semibold tracking-tight">NeuroSched</h1>
      </div>

      {/* Main content: responsive grid. If charts hidden, we keep single column. */}
      <div className={`grid ${showCharts ? "xl:grid-cols-2" : "grid-cols-1"} gap-6`}>
        {/* ---- Form Card ---- */}
        <div className="rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm bg-white/60 dark:bg-zinc-900/50 backdrop-blur-sm p-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              startSimulation();
            }}
            className="space-y-6"
          >
            {/* Core Settings */}
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Core Settings</h2>
              <Field label="Runtime (seconds)" id="runtime_seconds" value={form.runtime_seconds} onChange={onField("runtime_seconds")} disabled={isRunning} error={errors.runtime_seconds} />
              <Field label="Tenants" id="num_tenants" value={form.num_tenants} onChange={onField("num_tenants")} disabled={isRunning} error={errors.num_tenants} />
              <Field label="Arrival Rate" id="arrival_rate" value={form.arrival_rate} onChange={onField("arrival_rate")} disabled={isRunning} error={errors.arrival_rate} />
            </div>

            {/* Durations */}
            <div className="space-y-3">
              <h2 className="text-lg font-semibold">Durations</h2>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Lower (s)" id="duration_lower" value={form.duration_lower} onChange={onField("duration_lower")} disabled={isRunning} />
                <Field label="Upper (s)" id="duration_upper" value={form.duration_upper} onChange={onField("duration_upper")} disabled={isRunning} />
              </div>
              {errors.duration_pair && <InlineError msg={errors.duration_pair} />}
            </div>

            {/* Scheduling */}
            <div className="space-y-3">
              <h2 className="text-lg font-semibold">Scheduling</h2>
              <label htmlFor="scheduler" className="text-sm font-medium">Algorithm</label>
              <select
                id="scheduler"
                value={form.scheduler_choice}
                disabled={isRunning}
                onChange={(e) => setForm((f) => ({ ...f, scheduler_choice: e.target.value as "fifo" | "stf" }))}
                className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 bg-white dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
              >
                <option value="fifo">First In First Out (FIFO)</option>
                <option value="stf">Shortest Time First</option>
              </select>
            </div>

            {/* Actions */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <button
                type="submit"
                disabled={isRunning || !isValid}
                className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-white shadow transition-colors ${
                  isRunning || !isValid ? "bg-gray-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
                }`}
                title={!isValid ? "Fix validation errors to start" : "Start simulation"}
              >
                <Play size={18} />
                {isRunning ? "Running..." : "Start Simulation"}
              </button>

              {isRunning && (
                <button type="button" className="inline-flex items-center gap-2 rounded-xl px-4 py-2 bg-red-600 hover:bg-red-700 text-white shadow" onClick={stopSimulation}>
                  <StopCircle size={18} /> Stop
                </button>
              )}

              {!isRunning && (hasHistory || hasResults) && (
                <button type="button" className="inline-flex items-center gap-2 rounded-xl px-4 py-2 bg-zinc-800 hover:bg-black text-white shadow" onClick={clearResults}>
                  <Trash2 size={18} /> Clear
                </button>
              )}

              {!isValid && (
                <div className="flex items-center gap-2 text-amber-600 text-sm"><AlertCircle size={16} /> Fix the highlighted fields.</div>
              )}
            </div>
          </form>
        </div>

        {/* ---- Charts Column (appears only when running/after start or when history exists) ---- */}
        <AnimatePresence>
          {showCharts && (
            <motion.div
              key="charts"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.25 }}
              className="space-y-6"
            >
              <div className="flex items-center gap-2">
                <BarChart3 size={20} className="text-blue-500" />
                <h2 className="text-xl font-semibold">Live Metrics</h2>
              </div>

              <ChartCard title="Queue Length">
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" tickFormatter={timeTick} />
                    <YAxis />
                    <Tooltip labelFormatter={(l) => `t=${l}s`} />
                    <Legend />
                    <Line type="monotone" dataKey="queue_len" stroke="#6366f1" dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Completed Jobs">
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" tickFormatter={timeTick} />
                    <YAxis />
                    <Tooltip labelFormatter={(l) => `t=${l}s`} />
                    <Legend />
                    <Line type="monotone" dataKey="completed_jobs" stroke="#22c55e" dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="CPU Utilization (%)">
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" tickFormatter={timeTick} />
                    <YAxis domain={[0, 100]} />
                    <Tooltip labelFormatter={(l) => `t=${l}s`} />
                    <Legend />
                    <Line type="monotone" dataKey="cpu_util" stroke="#f59e0b" dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Results */}
      <AnimatePresence>
        {loadingResults && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm p-4 mt-6">
            <p>Compiling final results…</p>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {canShowResults && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} className="rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm p-4 mt-6">
            <h2 className="text-xl font-semibold mb-2 flex items-center gap-2"><BarChart3 size={20} /> Final Results</h2>
            <ul className="list-disc pl-6 space-y-1">
              {Object.entries(results.throughput).map(([tenant, val]) => (
                <li key={tenant}>
                  {tenant}: {val as number} jobs (Avg Wait: {results.avg_wait[tenant]?.toFixed(2)}s)
                </li>
              ))}
            </ul>
            {results.fairness !== undefined && (
              <p className="mt-3">⚖️ Jain's Fairness Index: <strong>{Number(results.fairness).toFixed(3)}</strong></p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------- Reusable UI bits ----------
function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm p-4 bg-white/60 dark:bg-zinc-900/50 backdrop-blur-sm">
      <h3 className="font-medium mb-2">{title}</h3>
      {children}
    </section>
  );
}

function InlineError({ msg }: { msg?: string }) {
  if (!msg) return null;
  return (
    <div className="mt-2 flex items-center gap-2 text-amber-600 text-sm">
      <AlertCircle size={16} />
      <span>{msg}</span>
    </div>
  );
}

function Field({ label, id, value, onChange, disabled, error }: { label: string; id: string; value: string; onChange: (v: string) => void; disabled?: boolean; error?: string; }) {
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      <input
        id={id}
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={`mt-1 w-full rounded-lg border px-3 py-2 bg-white dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-blue-500/50 ${error ? "border-amber-500" : "border-gray-300 dark:border-gray-700"}`}
      />
      {error && <InlineError msg={error} />}
    </div>
  );
}
