"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MarkerType,
  Position,
  type Edge,
  type Node,
} from "@xyflow/react";
import dagre from "dagre";

import "@xyflow/react/dist/style.css";

type GraphNode = {
  id: string;
  label: string;
  type: "ingress" | "service" | "deployment" | "pod";
  status: "healthy" | "degraded" | "unknown";
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

const NODE_WIDTH = 200;
const NODE_HEIGHT = 70;

const TYPE_STYLES: Record<GraphNode["type"], { accent: string; tag: string }> = {
  ingress:    { accent: "#a855f7", tag: "Ingress" },
  service:    { accent: "#38bdf8", tag: "Service" },
  deployment: { accent: "#f59e0b", tag: "Deployment" },
  pod:        { accent: "#4ade80", tag: "Pod" },
};

const STATUS_BORDER: Record<GraphNode["status"], string> = {
  healthy:  "#22c55e",
  degraded: "#ef4444",
  unknown:  "#6b7280",
};

function layout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 80 });

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    };
  });
}

function GraphCanvas({ data }: Props) {
  const { nodes, edges, stats } = useMemo(() => {
    const rawNodes = data?.nodes ?? [];
    const rawEdges = data?.edges ?? [];

    const rfNodes: Node[] = rawNodes.map((n) => {
      const style = TYPE_STYLES[n.type] ?? TYPE_STYLES.pod;
      const border = STATUS_BORDER[n.status] ?? STATUS_BORDER.unknown;
      return {
        id: n.id,
        data: {
          label: (
            <div style={{ textAlign: "left" }}>
              <div style={{
                fontSize: 10,
                textTransform: "uppercase",
                letterSpacing: 0.5,
                color: style.accent,
                marginBottom: 2,
                fontWeight: 600,
              }}>
                {style.tag}
              </div>
              <div style={{
                fontSize: 12,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                color: "#e5e7eb",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}>
                {n.label}
              </div>
              {n.type === "pod" && n.meta && typeof n.meta.phase === "string" ? (
                <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 2 }}>
                  {String(n.meta.phase)}
                  {typeof n.meta.restarts === "number" && n.meta.restarts > 0
                    ? ` · ${n.meta.restarts} restarts`
                    : ""}
                </div>
              ) : null}
            </div>
          ),
        },
        position: { x: 0, y: 0 },
        style: {
          background: "#111827",
          border: `2px solid ${border}`,
          borderLeft: `4px solid ${style.accent}`,
          borderRadius: 8,
          padding: 10,
          width: NODE_WIDTH,
          color: "#e5e7eb",
        },
      };
    });

    const rfEdges: Edge[] = rawEdges.map((e, i) => ({
      id: `e${i}-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      animated: e.kind === "ingress->service",
      markerEnd: { type: MarkerType.ArrowClosed, color: "#64748b" },
      style: { stroke: "#475569", strokeWidth: 1.5 },
    }));

    const laidOut = layout(rfNodes, rfEdges);

    const counts = rawNodes.reduce<Record<string, number>>((acc, n) => {
      acc[n.type] = (acc[n.type] ?? 0) + 1;
      return acc;
    }, {});

    return { nodes: laidOut, edges: rfEdges, stats: counts };
  }, [data]);

  if (!data?.nodes || data.nodes.length === 0) {
    return (
      <div className="rounded-lg p-6 text-center text-sm"
        style={{ background: "var(--bg-surface-2)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
        No resources found in this namespace.
      </div>
    );
  }

  return (
    <div className="rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)" }}>
      <div className="px-3 py-2 flex items-center justify-between text-xs"
        style={{ background: "var(--bg-surface-3)", borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}>
        <span className="font-mono">
          namespace: {data.namespace ?? "-"}
        </span>
        <span className="flex gap-3 text-[10px] uppercase tracking-wider">
          {(["ingress", "service", "deployment", "pod"] as const).map((t) => (
            <span key={t} style={{ color: TYPE_STYLES[t].accent }}>
              {TYPE_STYLES[t].tag}: {stats[t] ?? 0}
            </span>
          ))}
        </span>
      </div>
      <div style={{ height: 520, background: "#0b1220" }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          proOptions={{ hideAttribution: true }}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          defaultEdgeOptions={{ type: "smoothstep" }}
        >
          <Background color="#1f2937" gap={20} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}

export default function ResourceGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <GraphCanvas {...props} />
    </ReactFlowProvider>
  );
}
