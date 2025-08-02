"use client";
import { useState, useRef, useEffect } from "react";
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

type SimulationConfig = {
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
  scheduler_choice: "fifo" | "stf" | "rl";
  preemption_enabled: boolean;
};

export default function Home() {
  const [config, setConfig] = useState<SimulationConfig>({
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

  const [data, setData] = useState<any[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<any | null>(null);
  const [loadingResults, setLoadingResults] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  const startSimulation = async () => {
    setResults(null);
    setData([]);

    await fetch("http://localhost:8000/start-simulation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });

    setIsRunning(true);

    const socket = new WebSocket("ws://localhost:8000/ws/simulation");
    socketRef.current = socket;

    socket.onmessage = (event) => {
      const update = JSON.parse(event.data);
      setData((prev) => [...prev, update]);
    };

    socket.onclose = async () => {
      setIsRunning(false);
      setLoadingResults(true);
      try {
        const res = await fetch("http://localhost:8000/results");
        const finalResults = await res.json();
        setResults(finalResults);
      } catch (err) {
        console.error("Error fetching results:", err);
      } finally {
        setLoadingResults(false);
      }
    };
  };

  const stopSimulation = async () => {
    await fetch("http://localhost:8000/stop-simulation", { method: "POST" });
    socketRef.current?.close();
  };

  const clearResults = async () => {
  try {
    await fetch("http://localhost:8000/clear-results", { method: "POST" });
    setData([]);
    setResults(null);
  } catch (err) {
    console.error("Error clearing results:", err);
  }
};

  useEffect(() => {
    const fetchPersisted = async () => {
      try {
        const resResults = await fetch("http://localhost:8000/results");
        const persistedResults = await resResults.json();
        if (persistedResults.throughput) {
          setResults(persistedResults);
        }

        const resData = await fetch("http://localhost:8000/history");
        const persistedData = await resData.json();
        if (Array.isArray(persistedData)) {
          setData(persistedData);
        }
      } catch (err) {
        console.error("Error fetching persisted data:", err);
      }
    };

    fetchPersisted();
  }, []);

  return (
    <div className="app">
      <div className="form-panel">
        <h1>⚡ NeuroSched Config</h1>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            startSimulation();
          }}
        >
          <div className="form-grid">
            <label>Runtime (seconds)</label>
            <input
              type="number"
              value={config.runtime_seconds}
              onChange={(e) =>
                setConfig({ ...config, runtime_seconds: Number(e.target.value) })
              }
            />

            <label>Tenants</label>
            <input
              type="number"
              value={config.num_tenants}
              onChange={(e) =>
                setConfig({ ...config, num_tenants: Number(e.target.value) })
              }
            />

            <label>Arrival Rate</label>
            <input
              type="number"
              value={config.arrival_rate}
              onChange={(e) =>
                setConfig({ ...config, arrival_rate: Number(e.target.value) })
              }
            />

            <label>Duration Range (seconds)</label>
            <div className="range-inputs">
              <input
                type="number"
                value={config.duration_range[0]}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    duration_range: [
                      Number(e.target.value),
                      config.duration_range[1],
                    ],
                  })
                }
              />
              <span>-</span>
              <input
                type="number"
                value={config.duration_range[1]}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    duration_range: [
                      config.duration_range[0],
                      Number(e.target.value),
                    ],
                  })
                }
              />
            </div>

            {/* Scheduling Algorithm Dropdown */}
            <label>Scheduling Algorithm</label>
            <select
              value={config.scheduler_choice}
              onChange={(e) =>
                setConfig({
                  ...config,
                  scheduler_choice: e.target.value as
                    | "fifo"
                    | "stf"
                    | "rl",
                })
              }
            >
              <option value="fifo">First In First Out (FIFO)</option>
              {/* placeholders for future */}
              <option value="stf">
                Shortest Time First
              </option>
              <option value="rl" disabled>
                Reinforcement Learning (coming soon)
              </option>
            </select>
          </div>

          <div className="button-row">
            <button type="submit" disabled={isRunning}>
              {isRunning ? "Running..." : "Start Simulation"}
            </button>

            {isRunning && (
              <button
                type="button"
                className="stop-button"
                onClick={stopSimulation}
              >
                Stop Simulation
              </button>
            )}

            {!isRunning && data.length > 0 && (
              <button
                type="button"
                className="clear-button"
                onClick={clearResults}
              >
                Clear Results
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="chart-panel">
        <h1>📊 Live Metrics</h1>
        <section>
          <h2>Queue Length</h2>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="queue_len" stroke="#8884d8" />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section>
          <h2>Completed Jobs</h2>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="completed_jobs" stroke="#82ca9d" />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section>
          <h2>CPU Utilization (%)</h2>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="cpu_util" stroke="#ff7300" />
            </LineChart>
          </ResponsiveContainer>
        </section>
      </div>

      {loadingResults && (
        <div className="results-panel">
          <p>Fetching final results...</p>
        </div>
      )}

      {results && results.throughput && results.avg_wait && (
        <div className="results-panel">
          <h1>📈 Final Results</h1>
          <ul>
            {Object.entries(results.throughput).map(([tenant, val]) => (
              <li key={tenant}>
                {tenant}: {val} jobs (Avg Wait:{" "}
                {results.avg_wait[tenant]?.toFixed(2)}s)
              </li>
            ))}
          </ul>

          {results.fairness !== undefined && (
            <p>
              ⚖️ Jain's Fairness Index:{" "}
              <strong>{results.fairness.toFixed(3)}</strong>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
