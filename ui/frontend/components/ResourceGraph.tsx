"use client";

/**
 * Visual debugging canvas — the Kubeastra resource graph.
 *
 * Renders Ingress → Service → Deployment → Pod topology with:
 * - Custom node components with icons, health indicators, and metadata
 * - Click-to-inspect detail panel
 * - Hover tooltips showing resource metadata
 * - Health-aware glow effects (red pulse for degraded, green for healthy)
 * - MiniMap for navigation in large graphs
 * - Edge labels showing relationship type
 */

import { useCallback, useMemo, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  Position,
  Handle,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import dagre from "dagre";

import "@xyflow/react/dist/style.css";

/* ── Types ─────────────────────────────────────────────────────── */

type ResourceType = "ingress" | "service" | "deployment" | "pod";
type HealthStatus = "healthy" | "degraded" | "unknown";

type GraphNode = {
  id: string;
  label: string;
  type: ResourceType;
  status: HealthStatus;
  meta?: Record<string, unknown>;
};

type GraphEdge = {
  source: string;
  target: string;
  kind: string;
};

interface Props {
  data: {
    namespace?: string;
    nodes?: GraphNode[];
    edges?: GraphEdge[];
    summary?: Record<string, number>;
  };
}

/* ── Design tokens ─────────────────────────────────────────────── */

const NODE_WIDTH = 220;
const NODE_HEIGHT = 80;

const TYPE_CONFIG: Record<ResourceType, { color: string; bg: string; icon: string; tag: string }> = {
  ingress:    { color: "#c084fc", bg: "rgba(192, 132, 252, 0.08)", icon: "🌐", tag: "Ingress" },
  service:    { color: "#38bdf8", bg: "rgba(56, 189, 248, 0.08)",  icon: "🔗", tag: "Service" },
  deployment: { color: "#fbbf24", bg: "rgba(251, 191, 36, 0.08)",  icon: "📦", tag: "Deployment" },
  pod:        { color: "#4ade80", bg: "rgba(74, 222, 128, 0.08)",  icon: "⬡",  tag: "Pod" },
};

const STATUS_CONFIG: Record<HealthStatus, { border: string; glow: string; dot: string; pulse: boolean }> = {
  healthy:  { border: "#22c55e", glow: "0 0 12px rgba(34, 197, 94, 0.3)",  dot: "#22c55e", pulse: false },
  degraded: { border: "#ef4444", glow: "0 0 16px rgba(239, 68, 68, 0.4)",  dot: "#ef4444", pulse: true },
  unknown:  { border: "#6b7280", glow: "none",                              dot: "#6b7280", pulse: false },
};

const EDGE_LABELS: Record<string, string> = {
  "ingress->service": "routes →",
  "service->pod": "selects →",
  "deployment->pod": "manages →",
};

/* ── CSS keyframes (injected once) ─────────────────────────────── */

const STYLE_ID = "kubeastra-graph-styles";

function ensureStyles() {
  if (typeof document === "undefined") return;
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    @keyframes ka-pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(1.8); }
    }
    @keyframes ka-glow-pulse {
      0%, 100% { box-shadow: 0 0 12px rgba(239, 68, 68, 0.3); }
      50% { box-shadow: 0 0 24px rgba(239, 68, 68, 0.6); }
    }
    .ka-node {
      transition: transform 0.15s ease, box-shadow 0.15s ease;
      cursor: pointer;
    }
    .ka-node:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3) !important;
    }
    .ka-tooltip {
      position: absolute;
      top: -8px;
      left: 50%;
      transform: translate(-50%, -100%);
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 11px;
      color: #e2e8f0;
      white-space: nowrap;
      z-index: 50;
      pointer-events: none;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    }
    .ka-tooltip::after {
      content: '';
      position: absolute;
      bottom: -5px;
      left: 50%;
      transform: translateX(-50%) rotate(45deg);
      width: 10px;
      height: 10px;
      background: #1e293b;
      border-right: 1px solid #334155;
      border-bottom: 1px solid #334155;
    }
    .ka-detail-panel {
      position: absolute;
      right: 12px;
      top: 12px;
      width: 280px;
      max-height: calc(100% - 24px);
      overflow-y: auto;
      background: rgba(15, 23, 42, 0.95);
      backdrop-filter: blur(12px);
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 16px;
      z-index: 40;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
      color: #e2e8f0;
      font-size: 12px;
    }
    .ka-minimap {
      border-radius: 8px !important;
      border: 1px solid #334155 !important;
      overflow: hidden !important;
    }
  `;
  document.head.appendChild(style);
}

/* ── Custom node component ─────────────────────────────────────── */

function KubeNode({ data }: NodeProps) {
  const [hovered, setHovered] = useState(false);
  const d = data as {
    resourceType: ResourceType;
    status: HealthStatus;
    label: string;
    meta: Record<string, unknown>;
  };

  const typeConf = TYPE_CONFIG[d.resourceType] ?? TYPE_CONFIG.pod;
  const statusConf = STATUS_CONFIG[d.status] ?? STATUS_CONFIG.unknown;

  const metaLines: string[] = [];
  if (d.meta) {
    if (d.resourceType === "pod") {
      if (d.meta.phase) metaLines.push(`Phase: ${d.meta.phase}`);
      if (typeof d.meta.restarts === "number") metaLines.push(`Restarts: ${d.meta.restarts}`);
      if (d.meta.node) metaLines.push(`Node: ${String(d.meta.node).slice(0, 20)}`);
      if (d.meta.ip) metaLines.push(`IP: ${d.meta.ip}`);
    } else if (d.resourceType === "deployment") {
      if (d.meta.ready_replicas !== undefined) metaLines.push(`Ready: ${d.meta.ready_replicas}/${d.meta.replicas}`);
      if (d.meta.strategy) metaLines.push(`Strategy: ${d.meta.strategy}`);
    } else if (d.resourceType === "service") {
      if (d.meta.type) metaLines.push(`Type: ${d.meta.type}`);
      if (d.meta.cluster_ip) metaLines.push(`ClusterIP: ${d.meta.cluster_ip}`);
      if (d.meta.ports) metaLines.push(`Ports: ${d.meta.ports}`);
    } else if (d.resourceType === "ingress") {
      if (d.meta.host) metaLines.push(`Host: ${d.meta.host}`);
      if (d.meta.class) metaLines.push(`Class: ${d.meta.class}`);
    }
  }

  return (
    <div
      className="ka-node"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: "relative",
        width: NODE_WIDTH,
        background: `linear-gradient(135deg, #0f172a 0%, ${typeConf.bg.replace("0.08", "0.15")} 100%)`,
        border: `1.5px solid ${statusConf.border}40`,
        borderLeft: `4px solid ${typeConf.color}`,
        borderRadius: 10,
        padding: "10px 12px",
        boxShadow: d.status === "degraded"
          ? statusConf.glow
          : "0 2px 8px rgba(0, 0, 0, 0.2)",
        animation: d.status === "degraded" ? "ka-glow-pulse 2s ease-in-out infinite" : "none",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0, width: 8, height: 8 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, width: 8, height: 8 }} />

      {/* Header row: icon + type tag + health dot */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <span style={{ fontSize: 13 }}>{typeConf.icon}</span>
        <span style={{
          fontSize: 9,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: typeConf.color,
          background: `${typeConf.color}18`,
          padding: "1px 6px",
          borderRadius: 4,
        }}>
          {typeConf.tag}
        </span>
        <div style={{ flex: 1 }} />
        <div style={{ position: "relative" }}>
          <div style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: statusConf.dot,
          }} />
          {statusConf.pulse && (
            <div style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: statusConf.dot,
              animation: "ka-pulse 2s ease-in-out infinite",
            }} />
          )}
        </div>
      </div>

      {/* Resource name */}
      <div style={{
        fontSize: 12,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        color: "#f1f5f9",
        fontWeight: 500,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        lineHeight: 1.3,
      }}>
        {d.label}
      </div>

      {/* Status line */}
      {d.resourceType === "pod" && !!d.meta?.phase && (
        <div style={{
          fontSize: 10,
          color: d.status === "degraded" ? "#fca5a5" : "#94a3b8",
          marginTop: 3,
          display: "flex",
          alignItems: "center",
          gap: 4,
        }}>
          <span>{String(d.meta.phase)}</span>
          {typeof d.meta.restarts === "number" && d.meta.restarts > 0 && (
            <span style={{
              background: Number(d.meta.restarts) > 5 ? "#7f1d1d" : "#1e293b",
              color: Number(d.meta.restarts) > 5 ? "#fca5a5" : "#94a3b8",
              padding: "0 4px",
              borderRadius: 3,
              fontSize: 9,
              fontWeight: 600,
            }}>
              {String(d.meta.restarts)} restarts
            </span>
          )}
        </div>
      )}

      {d.resourceType === "deployment" && d.meta?.ready_replicas != null && (
        <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 3 }}>
          {String(d.meta.ready_replicas)}/{String(d.meta.replicas)} ready
        </div>
      )}

      {d.resourceType === "service" && !!d.meta?.type && (
        <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 3 }}>
          {String(d.meta.type)}{d.meta.ports ? ` · ${String(d.meta.ports).slice(0, 30)}` : ""}
        </div>
      )}

      {/* Hover tooltip */}
      {hovered && metaLines.length > 0 && (
        <div className="ka-tooltip">
          {metaLines.map((line, i) => (
            <div key={i} style={{ marginBottom: i < metaLines.length - 1 ? 3 : 0 }}>
              <span style={{ color: "#94a3b8" }}>{line.split(":")[0]}:</span>
              <span style={{ color: "#f1f5f9", fontWeight: 500 }}> {line.split(":").slice(1).join(":")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const nodeTypes = { kubeNode: KubeNode };

/* ── Detail panel (shown on node click) ────────────────────────── */

function DetailPanel({ node, onClose }: { node: GraphNode; onClose: () => void }) {
  const typeConf = TYPE_CONFIG[node.type] ?? TYPE_CONFIG.pod;
  const statusConf = STATUS_CONFIG[node.status] ?? STATUS_CONFIG.unknown;

  return (
    <div className="ka-detail-panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 16 }}>{typeConf.icon}</span>
          <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: typeConf.color }}>{typeConf.tag}</span>
        </div>
        <button onClick={onClose} style={{
          background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: 18,
          padding: "2px 6px", borderRadius: 4, lineHeight: 1,
        }}>
          &times;
        </button>
      </div>

      <div style={{
        fontSize: 14,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        color: "#f1f5f9",
        fontWeight: 600,
        marginBottom: 12,
        wordBreak: "break-all",
      }}>
        {node.label}
      </div>

      <div style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        background: `${statusConf.border}15`,
        border: `1px solid ${statusConf.border}40`,
        borderRadius: 6,
        padding: "4px 10px",
        marginBottom: 14,
      }}>
        <div style={{ width: 7, height: 7, borderRadius: "50%", background: statusConf.dot }} />
        <span style={{ fontSize: 11, fontWeight: 600, color: statusConf.border, textTransform: "capitalize" }}>
          {node.status}
        </span>
      </div>

      {node.meta && Object.keys(node.meta).length > 0 && (
        <div style={{ marginTop: 4 }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
            Metadata
          </div>
          <div style={{
            background: "#0f172a",
            borderRadius: 8,
            padding: 10,
            border: "1px solid #1e293b",
          }}>
            {Object.entries(node.meta).map(([key, val]) => (
              <div key={key} style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 11 }}>
                <span style={{ color: "#94a3b8" }}>{key}</span>
                <span style={{ color: "#e2e8f0", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontWeight: 500 }}>
                  {String(val).slice(0, 30)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Dagre layout ──────────────────────────────────────────────── */

function layoutGraph(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 50, ranksep: 100, marginx: 30, marginy: 30 });

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
    };
  });
}

/* ── Main graph canvas ─────────────────────────────────────────── */

function GraphCanvas({ data }: Props) {
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  // Build a lookup for raw nodes so we can get the original data on click
  const rawNodeMap = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const n of data?.nodes ?? []) map.set(n.id, n);
    return map;
  }, [data]);

  const { nodes, edges, stats } = useMemo(() => {
    ensureStyles();
    const rawNodes = data?.nodes ?? [];
    const rawEdges = data?.edges ?? [];

    const rfNodes: Node[] = rawNodes.map((n) => ({
      id: n.id,
      type: "kubeNode",
      data: {
        resourceType: n.type,
        status: n.status,
        label: n.label,
        meta: n.meta ?? {},
      },
      position: { x: 0, y: 0 },
    }));

    const rfEdges: Edge[] = rawEdges.map((e, i) => ({
      id: `e${i}-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      animated: e.kind === "ingress->service",
      label: EDGE_LABELS[e.kind] || "",
      labelStyle: { fontSize: 9, fill: "#64748b", fontWeight: 500 },
      labelBgStyle: { fill: "#0f172a", fillOpacity: 0.9 },
      labelBgPadding: [4, 6] as [number, number],
      labelBgBorderRadius: 4,
      markerEnd: { type: MarkerType.ArrowClosed, color: "#475569", width: 16, height: 16 },
      style: {
        stroke: e.kind === "ingress->service" ? "#c084fc50" : "#47556950",
        strokeWidth: 1.5,
      },
    }));

    const laidOut = layoutGraph(rfNodes, rfEdges);

    const counts = rawNodes.reduce<Record<string, number>>((acc, n) => {
      acc[n.type] = (acc[n.type] ?? 0) + 1;
      return acc;
    }, {});

    return { nodes: laidOut, edges: rfEdges, stats: counts };
  }, [data]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    const raw = rawNodeMap.get(node.id);
    if (raw) setSelectedNode(raw);
  }, [rawNodeMap]);

  if (!data?.nodes || data.nodes.length === 0) {
    return (
      <div style={{
        borderRadius: 12,
        padding: 32,
        textAlign: "center",
        fontSize: 13,
        background: "#0f172a",
        border: "1px solid #1e293b",
        color: "#64748b",
      }}>
        No resources found in this namespace.
      </div>
    );
  }

  const totalNodes = data.nodes.length;
  const degradedCount = data.nodes.filter(n => n.status === "degraded").length;

  return (
    <div style={{ borderRadius: 12, overflow: "hidden", border: "1px solid #1e293b" }}>
      {/* Header bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 14px",
        background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
        borderBottom: "1px solid #1e293b",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12 }}>🗺️</span>
          <span style={{
            fontSize: 11,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            color: "#94a3b8",
            fontWeight: 500,
          }}>
            {data.namespace ?? "—"}
          </span>
          {degradedCount > 0 && (
            <span style={{
              fontSize: 9,
              fontWeight: 700,
              color: "#fca5a5",
              background: "#7f1d1d",
              padding: "2px 7px",
              borderRadius: 4,
              letterSpacing: "0.04em",
            }}>
              {degradedCount} DEGRADED
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          {(["ingress", "service", "deployment", "pod"] as const).map((t) => {
            const count = stats[t] ?? 0;
            if (count === 0) return null;
            return (
              <span key={t} style={{
                fontSize: 10,
                fontWeight: 600,
                color: TYPE_CONFIG[t].color,
                letterSpacing: "0.04em",
              }}>
                {count} {TYPE_CONFIG[t].tag}{count > 1 ? "s" : ""}
              </span>
            );
          })}
        </div>
      </div>

      {/* Canvas */}
      <div style={{ height: Math.min(640, Math.max(400, totalNodes * 50 + 200)), background: "#080e1a", position: "relative" }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          minZoom={0.3}
          maxZoom={2}
          defaultEdgeOptions={{ type: "smoothstep" }}
        >
          <Background color="#1e293b" gap={24} size={1} />
          <Controls
            showInteractive={false}
            style={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 8,
            }}
          />
          <MiniMap
            className="ka-minimap"
            nodeColor={(n) => {
              const d = n.data as { status?: string; resourceType?: string };
              if (d?.status === "degraded") return "#ef4444";
              if (d?.status === "healthy") return "#22c55e";
              return "#6b7280";
            }}
            maskColor="rgba(0, 0, 0, 0.6)"
            style={{ background: "#0f172a" }}
          />
        </ReactFlow>

        {/* Detail panel overlay */}
        {selectedNode && (
          <DetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
        )}
      </div>
    </div>
  );
}

/* ── Export ─────────────────────────────────────────────────────── */

export default function ResourceGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <GraphCanvas {...props} />
    </ReactFlowProvider>
  );
}
