"use client";

import {
  Brain,
  Search,
  Server,
  Layers,
  AlertTriangle,
  Activity,
} from "lucide-react";

export type TabId =
  | "analyze"
  | "investigate"
  | "cluster"
  | "multicluster"
  | "recovery";

const TABS: { id: TabId; label: string; icon: React.ReactNode; description: string }[] = [
  {
    id: "analyze",
    label: "AI Analysis",
    icon: <Brain size={18} />,
    description: "Paste errors, get Gemini AI fix",
  },
  {
    id: "investigate",
    label: "Investigate",
    icon: <Search size={18} />,
    description: "Live pod triage & logs",
  },
  {
    id: "cluster",
    label: "Cluster Info",
    icon: <Server size={18} />,
    description: "Deployments, services, events",
  },
  {
    id: "multicluster",
    label: "Multi-cluster",
    icon: <Layers size={18} />,
    description: "Manage kubeconfig contexts",
  },
  {
    id: "recovery",
    label: "Recovery",
    icon: <AlertTriangle size={18} />,
    description: "Scale, restart, patch (write ops)",
  },
];

interface Props {
  active: TabId;
  onChange: (id: TabId) => void;
  health: { kubectl_available: boolean; ai_enabled: boolean; kubectl_context: string | null } | null;
}

export default function Sidebar({ active, onChange, health }: Props) {
  return (
    <aside className="w-64 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Header */}
      <div className="px-5 py-5 border-b border-gray-800">
        <div className="flex items-center gap-2 mb-1">
          <Activity size={20} className="text-blue-400" />
          <span className="font-bold text-white text-sm tracking-wide">K8s DevOps</span>
        </div>
        <p className="text-gray-500 text-xs">Team Self-Service Portal</p>
      </div>

      {/* Status badges */}
      {health && (
        <div className="px-5 py-3 border-b border-gray-800 space-y-1.5">
          <StatusBadge ok={health.ai_enabled} label="Gemini AI" />
          <StatusBadge ok={health.kubectl_available} label={health.kubectl_context ?? "kubectl"} />
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className={`w-full text-left px-3 py-3 rounded-lg transition-colors flex items-start gap-3 group ${
              active === t.id
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:bg-gray-800 hover:text-white"
            }`}
          >
            <span className="mt-0.5 shrink-0">{t.icon}</span>
            <div>
              <div className="text-sm font-medium leading-tight">{t.label}</div>
              <div
                className={`text-xs leading-tight mt-0.5 ${
                  active === t.id ? "text-blue-200" : "text-gray-500 group-hover:text-gray-400"
                }`}
              >
                {t.description}
              </div>
            </div>
          </button>
        ))}
      </nav>

      <div className="px-5 py-4 border-t border-gray-800">
        <p className="text-gray-600 text-xs">mcp v1.0</p>
      </div>
    </aside>
  );
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`w-2 h-2 rounded-full shrink-0 ${ok ? "bg-green-400" : "bg-red-400"}`}
      />
      <span className="text-xs text-gray-400 truncate">{label}</span>
    </div>
  );
}
