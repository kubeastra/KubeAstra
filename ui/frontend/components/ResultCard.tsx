"use client";

import { useState } from "react";
import ResourceGraph from "./ResourceGraph";

interface Props {
  tool: string;
  result: Record<string, unknown>;
}

/* ── shared sub-components ───────────────────────────────────── */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      className="text-xs px-2 py-0.5 rounded transition"
      style={{ background: "var(--bg-surface-3)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function Badge({ text, color }: { text: string; color: "orange" | "green" | "yellow" | "red" | "muted" }) {
  const styles: Record<string, React.CSSProperties> = {
    orange: { background: "var(--brand-dim)", color: "var(--brand)",  border: "1px solid var(--brand-border)" },
    green:  { background: "rgba(34,197,94,0.1)",   color: "var(--success)",     border: "1px solid rgba(34,197,94,0.25)" },
    yellow: { background: "rgba(245,158,11,0.1)",  color: "var(--warning)",     border: "1px solid rgba(245,158,11,0.25)" },
    red:    { background: "rgba(239,68,68,0.1)",   color: "var(--danger)",      border: "1px solid rgba(239,68,68,0.25)" },
    muted:  { background: "var(--bg-surface-3)",   color: "var(--text-muted)",  border: "1px solid var(--border)" },
  };
  return (
    <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold" style={styles[color]}>
      {text}
    </span>
  );
}

function severityBadgeColor(s: unknown): "orange" | "green" | "yellow" | "red" | "muted" {
  const v = String(s ?? "").toLowerCase();
  if (v === "critical" || v === "high") return "red";
  if (v === "medium") return "yellow";
  return "green";
}

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="relative group mt-1 mb-2">
      <pre
        className="rounded-lg p-3 text-xs overflow-x-auto whitespace-pre-wrap break-words"
        style={{ background: "var(--bg-base)", border: "1px solid var(--border)", color: "#4ADE80" /* terminal green */ }}
      >
        {code}
      </pre>
      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <CopyButton text={code} />
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-3">
      <p className="text-xs font-semibold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>{title}</p>
      {children}
    </div>
  );
}

function ResourceName({ children }: { children: React.ReactNode }) {
  return <span className="font-mono text-xs" style={{ color: "var(--brand)" }}>{children}</span>;
}

/* ── per-tool renderers ──────────────────────────────────────── */

function renderAnalyzeError(r: Record<string, unknown>) {
  return (
    <>
      {r.severity && (
        <div className="mb-2">
          <Badge text={String(r.severity)} color={severityBadgeColor(r.severity)} />
        </div>
      )}
      {r.error_type && (
        <Section title="Error type">
          <p className="text-sm" style={{ color: "var(--text-primary)" }}>{String(r.error_type)}</p>
        </Section>
      )}
      {r.root_cause && (
        <Section title="Root cause">
          <p className="text-sm" style={{ color: "var(--text-primary)" }}>{String(r.root_cause)}</p>
        </Section>
      )}
      {r.solution && (
        <Section title="Solution">
          <p className="text-sm" style={{ color: "var(--text-primary)" }}>{String(r.solution)}</p>
        </Section>
      )}
      {Array.isArray(r.steps) && r.steps.length > 0 && (
        <Section title="Steps">
          <ol className="list-decimal list-inside space-y-1">
            {(r.steps as string[]).map((s, i) => (
              <li key={i} className="text-sm" style={{ color: "var(--text-secondary)" }}>{s}</li>
            ))}
          </ol>
        </Section>
      )}
      {Array.isArray(r.commands) && r.commands.length > 0 && (
        <Section title="Commands">
          {(r.commands as Array<{ command?: string; cmd?: string; description?: string } | string>).map((c, i) => {
            // support both "command" (analyze_error) and "cmd" (analyze_live_investigation)
            const cmd = typeof c === "string" ? c : (c.command ?? c.cmd ?? "");
            const desc = typeof c === "string" ? "" : c.description ?? "";
            return (
              <div key={i}>
                {desc && <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{desc}</p>}
                {cmd && <CodeBlock code={cmd} />}
              </div>
            );
          })}
        </Section>
      )}
      {r.prevention && (
        <Section title="Prevention">
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{String(r.prevention)}</p>
        </Section>
      )}
      {r.corrected_snippet && (
        <Section title="Corrected code">
          <CodeBlock code={String(r.corrected_snippet)} />
        </Section>
      )}
      {r.corrected_file && (
        <Section title="">
          <details>
            <summary
              className="text-xs font-medium cursor-pointer select-none py-1"
              style={{ color: "var(--brand)", listStyle: "none" }}
            >
              <span className="flex items-center gap-1.5">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                Full corrected file
              </span>
            </summary>
            <div className="mt-2 max-h-96 overflow-y-auto rounded-lg" style={{ border: "1px solid var(--border)" }}>
              <CodeBlock code={String(r.corrected_file)} />
            </div>
          </details>
        </Section>
      )}
    </>
  );
}

function renderPodList(r: Record<string, unknown>) {
  const pods = Array.isArray(r.pods) ? r.pods as Record<string, unknown>[] : [];
  if (!pods.length) return <p className="text-sm italic" style={{ color: "var(--text-muted)" }}>{String(r.error ?? "No pods found")}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs mt-2 border-collapse">
        <thead>
          <tr className="text-left" style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
            <th className="pb-1 pr-4">Name</th>
            <th className="pb-1 pr-4">Status</th>
            <th className="pb-1 pr-4">Ready</th>
            <th className="pb-1">Restarts</th>
          </tr>
        </thead>
        <tbody>
          {pods.map((p, i) => {
            const status = String(p.status ?? "");
            const isOk = status === "Running";
            return (
              <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="py-1 pr-4"><ResourceName>{String(p.name ?? "")}</ResourceName></td>
                <td className="py-1 pr-4 font-semibold text-xs" style={{ color: isOk ? "var(--success)" : "var(--danger)" }}>{status}</td>
                <td className="py-1 pr-4 text-xs" style={{ color: "var(--text-secondary)" }}>{String(p.ready ?? "")}</td>
                <td className="py-1 text-xs" style={{ color: "var(--text-secondary)" }}>{String(p.restarts ?? "0")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function renderLogs(r: Record<string, unknown>) {
  return <CodeBlock code={String(r.logs ?? r.output ?? "No logs")} />;
}

function renderEvents(r: Record<string, unknown>) {
  const events = Array.isArray(r.events) ? r.events as Record<string, unknown>[] : [];
  if (!events.length) return <p className="text-sm italic" style={{ color: "var(--text-muted)" }}>No events found.</p>;
  return (
    <div className="space-y-2 mt-1">
      {events.map((e, i) => {
        const isWarn = String(e.type ?? "").toLowerCase() === "warning";
        return (
          <div
            key={i}
            className="p-2 rounded text-xs"
            style={{
              borderLeft: `2px solid ${isWarn ? "var(--warning)" : "var(--brand)"}`,
              background: isWarn ? "rgba(245,158,11,0.06)" : "var(--brand-dim)",
            }}
          >
            <div className="flex items-center gap-2 mb-0.5">
              <span className="font-semibold" style={{ color: isWarn ? "var(--warning)" : "var(--brand)" }}>
                {String(e.type ?? "Normal")}
              </span>
              <span style={{ color: "var(--text-muted)" }}>{String(e.reason ?? "")}</span>
              <span className="ml-auto" style={{ color: "var(--text-muted)" }}>{String(e.age ?? e.first_time ?? "")}</span>
            </div>
            <p style={{ color: "var(--text-secondary)" }}>{String(e.message ?? "")}</p>
          </div>
        );
      })}
    </div>
  );
}

function renderInvestigate(r: Record<string, unknown>) {
  return (
    <>
      {Array.isArray(r.steps_run) && (
        <Section title="Steps completed">
          <div className="flex flex-wrap gap-1">
            {(r.steps_run as string[]).map((s, i) => (
              <span key={i} className="px-2 py-0.5 rounded text-xs" style={{ background: "var(--brand-dim)", color: "var(--brand)", border: "1px solid var(--brand-border)" }}>{s}</span>
            ))}
          </div>
        </Section>
      )}
      {r.pod_info && typeof r.pod_info === "object" && (
        <Section title="Pod info">
          <div className="grid grid-cols-2 gap-x-4 text-xs mt-1">
            {Object.entries(r.pod_info as Record<string, unknown>).slice(0, 8).map(([k, v]) => (
              <div key={k} className="flex gap-1 py-0.5">
                <span className="min-w-[90px]" style={{ color: "var(--text-muted)" }}>{k}:</span>
                <span style={{ color: "var(--text-primary)" }}>{String(v)}</span>
              </div>
            ))}
          </div>
        </Section>
      )}
      {r.logs && typeof r.logs === "object" && (
        <Section title="Logs">
          {Object.entries(r.logs as Record<string, unknown>).map(([container, lines]) => (
            <div key={container}>
              <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Container: {container}</p>
              <CodeBlock code={String(lines)} />
            </div>
          ))}
        </Section>
      )}
      {r.ai && typeof r.ai === "object" && (() => {
        const aiObj = r.ai as Record<string, unknown>;
        // ai_enabled=false means no API key configured
        if (!aiObj.ai_enabled) {
          return (
            <Section title="AI Analysis">
              <p className="text-xs italic" style={{ color: "var(--text-muted)" }}>
                {String(aiObj.message ?? "AI analysis not available — set GEMINI_API_KEY in backend/.env")}
              </p>
            </Section>
          );
        }
        // ai_analysis may be null if Gemini call failed
        const analysis = aiObj.ai_analysis as Record<string, unknown> | null;
        if (!analysis) {
          return (
            <Section title="AI Analysis">
              <p className="text-xs italic" style={{ color: "var(--text-muted)" }}>
                {String(aiObj.error ?? "AI analysis failed — check backend logs")}
              </p>
            </Section>
          );
        }
        return (
          <Section title="AI Analysis">
            {renderAnalyzeError(analysis)}
          </Section>
        );
      })()}
    </>
  );
}

function renderContextList(r: Record<string, unknown>) {
  const contexts = Array.isArray(r.contexts) ? r.contexts as Record<string, unknown>[] : [];
  const current = String(r.current_context ?? "");
  return (
    <div className="space-y-1 mt-1">
      {contexts.map((c, i) => {
        const name = String(c.name ?? c);
        const isActive = name === current;
        return (
          <div
            key={i}
            className="flex items-center gap-2 p-2 rounded text-sm"
            style={{
              background: isActive ? "var(--brand-dim)" : "var(--bg-surface-3)",
              border: `1px solid ${isActive ? "var(--brand-border)" : "var(--border)"}`,
            }}
          >
            <span className="w-2 h-2 rounded-full inline-block" style={{ background: isActive ? "var(--success)" : "var(--border)" }} />
            <span className="font-mono" style={{ color: "var(--text-primary)" }}>{name}</span>
            {isActive && <Badge text="active" color="green" />}
          </div>
        );
      })}
    </div>
  );
}

function renderListServices(r: Record<string, unknown>) {
  const services = Array.isArray(r.services) ? r.services as Record<string, unknown>[] : [];
  if (!services.length) return <p className="text-sm italic" style={{ color: "var(--text-muted)" }}>No services found in this namespace.</p>;
  return (
    <div className="overflow-x-auto mt-1">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="text-left" style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
            <th className="pb-1 pr-4">Name</th>
            <th className="pb-1 pr-4">Type</th>
            <th className="pb-1 pr-4">Cluster IP</th>
            <th className="pb-1">Ports</th>
          </tr>
        </thead>
        <tbody>
          {services.map((s, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
              <td className="py-1.5 pr-4"><ResourceName>{String(s.name ?? "")}</ResourceName></td>
              <td className="py-1.5 pr-4 text-xs" style={{ color: "var(--text-secondary)" }}>{String(s.type ?? "")}</td>
              <td className="py-1.5 pr-4 font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>{String(s.cluster_ip ?? "")}</td>
              <td className="py-1.5 text-xs" style={{ color: "var(--text-muted)" }}>{Array.isArray(s.ports) ? (s.ports as string[]).join(", ") : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>{services.length} services in namespace {String(r.namespace ?? "")}</p>
    </div>
  );
}

function renderNamespaceResources(r: Record<string, unknown>) {
  const summary = r.summary as Record<string, number> | undefined;
  const pods = Array.isArray(r.pods) ? r.pods as Record<string, unknown>[] : [];
  const services = Array.isArray(r.services) ? r.services as Record<string, unknown>[] : [];
  const deployments = Array.isArray(r.deployments) ? r.deployments as Record<string, unknown>[] : [];
  const statefulsets = Array.isArray(r.statefulsets) ? r.statefulsets as Record<string, unknown>[] : [];
  const daemonsets = Array.isArray(r.daemonsets) ? r.daemonsets as Record<string, unknown>[] : [];
  const configmaps = Array.isArray(r.configmaps) ? r.configmaps as string[] : [];
  const ingresses = Array.isArray(r.ingresses) ? r.ingresses as Record<string, unknown>[] : [];

  const SectionHeader = ({ title, count }: { title: string; count: number }) => (
    <div className="flex items-center gap-2 mt-4 mb-1">
      <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{title}</p>
      <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: "var(--bg-surface-3)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>{count}</span>
    </div>
  );

  return (
    <>
      {summary && (
        <div className="flex flex-wrap gap-2 mb-3">
          {Object.entries(summary).filter(([, v]) => v > 0).map(([k, v]) => (
            <span key={k} className="text-xs px-2 py-0.5 rounded-lg" style={{ background: "var(--bg-surface-3)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
              {v} {k}
            </span>
          ))}
        </div>
      )}

      {deployments.length > 0 && (
        <>
          <SectionHeader title="Deployments" count={deployments.length} />
          <table className="w-full text-xs border-collapse">
            <thead><tr className="text-left" style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
              <th className="pb-1 pr-4">Name</th><th className="pb-1 pr-4">Replicas</th><th className="pb-1">Ready</th>
            </tr></thead>
            <tbody>{deployments.map((d, i) => {
              const ready = Number(d.ready ?? 0);
              const total = Number(d.replicas ?? 0);
              return (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td className="py-1 pr-4"><ResourceName>{String(d.name ?? "")}</ResourceName></td>
                  <td className="py-1 pr-4 text-xs" style={{ color: "var(--text-secondary)" }}>{total}</td>
                  <td className="py-1 font-semibold text-xs" style={{ color: ready === total ? "var(--success)" : "var(--warning)" }}>{ready}/{total}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </>
      )}

      {pods.length > 0 && (
        <>
          <SectionHeader title="Pods" count={pods.length} />
          <table className="w-full text-xs border-collapse">
            <thead><tr className="text-left" style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
              <th className="pb-1 pr-4">Name</th><th className="pb-1 pr-4">Status</th><th className="pb-1">Restarts</th>
            </tr></thead>
            <tbody>{pods.map((p, i) => {
              const status = String(p.status ?? "");
              const isOk = status === "Running" && p.ready;
              return (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td className="py-1 pr-4 text-[11px] truncate max-w-[200px]"><ResourceName>{String(p.name ?? "")}</ResourceName></td>
                  <td className="py-1 pr-4 font-semibold text-xs" style={{ color: isOk ? "var(--success)" : "var(--warning)" }}>{status}</td>
                  <td className="py-1 text-xs" style={{ color: "var(--text-muted)" }}>{String(p.restarts ?? 0)}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </>
      )}

      {services.length > 0 && (
        <>
          <SectionHeader title="Services" count={services.length} />
          <table className="w-full text-xs border-collapse">
            <thead><tr className="text-left" style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
              <th className="pb-1 pr-4">Name</th><th className="pb-1 pr-4">Type</th><th className="pb-1">Ports</th>
            </tr></thead>
            <tbody>{services.map((s, i) => (
              <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="py-1 pr-4"><ResourceName>{String(s.name ?? "")}</ResourceName></td>
                <td className="py-1 pr-4 text-xs" style={{ color: "var(--text-secondary)" }}>{String(s.type ?? "")}</td>
                <td className="py-1 text-xs" style={{ color: "var(--text-muted)" }}>{Array.isArray(s.ports) ? (s.ports as string[]).join(", ") : ""}</td>
              </tr>
            ))}</tbody>
          </table>
        </>
      )}

      {statefulsets.length > 0 && (
        <>
          <SectionHeader title="StatefulSets" count={statefulsets.length} />
          {statefulsets.map((s, i) => (
            <div key={i} className="text-xs py-0.5 font-mono" style={{ color: "var(--text-secondary)" }}>
              {String(s.name ?? "")} <span style={{ color: "var(--text-muted)" }}>({String(s.ready ?? 0)}/{String(s.replicas ?? 0)} ready)</span>
            </div>
          ))}
        </>
      )}

      {daemonsets.length > 0 && (
        <>
          <SectionHeader title="DaemonSets" count={daemonsets.length} />
          {daemonsets.map((d, i) => (
            <div key={i} className="text-xs py-0.5 font-mono" style={{ color: "var(--text-secondary)" }}>
              {String(d.name ?? "")} <span style={{ color: "var(--text-muted)" }}>({String(d.ready ?? 0)}/{String(d.desired ?? 0)} ready)</span>
            </div>
          ))}
        </>
      )}

      {ingresses.length > 0 && (
        <>
          <SectionHeader title="Ingresses" count={ingresses.length} />
          {ingresses.map((ing, i) => (
            <div key={i} className="text-xs py-0.5">
              <ResourceName>{String(ing.name ?? "")}</ResourceName>
              {Array.isArray(ing.hosts) && ing.hosts.length > 0 && (
                <span className="ml-2" style={{ color: "var(--text-muted)" }}>{(ing.hosts as string[]).join(", ")}</span>
              )}
            </div>
          ))}
        </>
      )}

      {configmaps.length > 0 && (
        <>
          <SectionHeader title="ConfigMaps" count={configmaps.length} />
          <div className="flex flex-wrap gap-1">
            {configmaps.map((cm, i) => (
              <span key={i} className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: "var(--bg-surface-3)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>{cm}</span>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function renderNamespaces(r: Record<string, unknown>) {
  const namespaces = Array.isArray(r.namespaces) ? r.namespaces as Record<string, unknown>[] : [];
  if (!namespaces.length) return <p className="text-sm italic" style={{ color: "var(--text-muted)" }}>No namespaces found.</p>;
  return (
    <div className="overflow-x-auto mt-1">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="text-left" style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
            <th className="pb-1 pr-4">Namespace</th>
            <th className="pb-1">Status</th>
          </tr>
        </thead>
        <tbody>
          {namespaces.map((ns, i) => {
            const name = String(ns.name ?? "");
            const status = String(ns.status ?? "");
            const isActive = status === "Active";
            const isSystem = name.startsWith("kube-");
            return (
              <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="py-1.5 pr-4">
                  <span className="font-mono" style={{ color: isSystem ? "var(--text-muted)" : "var(--brand)" }}>{name}</span>
                  {isSystem && <span className="ml-2 text-[10px] px-1 rounded" style={{ color: "var(--text-muted)", background: "var(--bg-surface-3)" }}>system</span>}
                </td>
                <td className="py-1.5 font-semibold text-xs" style={{ color: isActive ? "var(--success)" : "var(--warning)" }}>{status}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>{namespaces.length} namespaces total</p>
    </div>
  );
}

function renderFindWorkload(r: Record<string, unknown>) {
  const deployments = Array.isArray(r.deployments) ? r.deployments as Record<string, unknown>[] : [];
  const pods = Array.isArray(r.pods) ? r.pods as Record<string, unknown>[] : [];
  const services = Array.isArray(r.services) ? r.services as Record<string, unknown>[] : [];
  const total = deployments.length + pods.length + services.length;

  if (total === 0) {
    return (
      <p className="text-sm italic" style={{ color: "var(--text-muted)" }}>
        No workloads found matching &quot;{String(r.query ?? "")}&quot;.
      </p>
    );
  }

  const Row = ({ name, ns, extra, badge }: { name: string; ns: string; extra?: string; badge?: string }) => (
    <div className="flex items-center gap-3 py-1.5 text-sm" style={{ borderBottom: "1px solid var(--border)" }}>
      <ResourceName>{name}</ResourceName>
      <span className="text-xs px-1.5 py-0.5 rounded flex-shrink-0" style={{ color: "var(--text-muted)", background: "var(--bg-surface-3)" }}>{ns}</span>
      {badge && <span className="text-xs" style={{ color: "var(--success)" }}>{badge}</span>}
      {extra && <span className="text-xs ml-auto" style={{ color: "var(--text-muted)" }}>{extra}</span>}
    </div>
  );

  return (
    <>
      {deployments.length > 0 && (
        <Section title={`Deployments (${deployments.length})`}>
          {deployments.map((d, i) => {
            const ready = d.ready !== undefined ? String(d.ready) : null;
            const replicas = d.replicas !== undefined ? String(d.replicas) : null;
            const badge = ready !== null && replicas !== null ? `${ready}/${replicas} ready` : undefined;
            return <Row key={i} name={String(d.name ?? "")} ns={String(d.namespace ?? "")} badge={badge} />;
          })}
        </Section>
      )}
      {pods.length > 0 && (
        <Section title={`Pods (${pods.length})`}>
          {pods.map((p, i) => (
            <Row key={i} name={String(p.name ?? "")} ns={String(p.namespace ?? "")} extra={String(p.phase ?? "")} />
          ))}
        </Section>
      )}
      {services.length > 0 && (
        <Section title={`Services (${services.length})`}>
          {services.map((s, i) => (
            <Row key={i} name={String(s.name ?? "")} ns={String(s.namespace ?? "")} extra={String(s.type ?? "")} />
          ))}
        </Section>
      )}
    </>
  );
}

function renderGeneric(r: Record<string, unknown>) {
  const textFields = ["message", "output", "description", "result", "summary", "runbook", "report"];
  for (const f of textFields) {
    if (r[f] && typeof r[f] === "string") {
      return (
        <>
          <p className="text-sm whitespace-pre-wrap" style={{ color: "var(--text-primary)" }}>{String(r[f])}</p>
          {Object.keys(r).filter(k => k !== f && typeof r[k] !== "object").length > 0 && (
            <div className="mt-2 grid grid-cols-2 gap-x-4 text-xs">
              {Object.entries(r)
                .filter(([k, v]) => k !== f && typeof v !== "object")
                .map(([k, v]) => (
                  <div key={k} className="flex gap-1 py-0.5">
                    <span className="min-w-[80px]" style={{ color: "var(--text-muted)" }}>{k}:</span>
                    <span style={{ color: "var(--text-secondary)" }}>{String(v)}</span>
                  </div>
                ))}
            </div>
          )}
        </>
      );
    }
  }
  return <CodeBlock code={JSON.stringify(r, null, 2)} />;
}

/* ── main export ─────────────────────────────────────────────── */

const ANALYZE_TOOLS = ["analyze_error", "get_fix_commands", "generate_runbook", "cluster_report", "error_summary"];

export default function ResultCard({ tool, result }: Props) {
  const [showRaw, setShowRaw] = useState(false);

  let body: React.ReactNode;
  if (ANALYZE_TOOLS.includes(tool))         body = renderAnalyzeError(result);
  else if (tool === "investigate_pod")       body = renderInvestigate(result);
  else if (tool === "get_pods")             body = renderPodList(result);
  else if (tool === "get_pod_logs")         body = renderLogs(result);
  else if (tool === "get_events")           body = renderEvents(result);
  else if (tool === "list_contexts")        body = renderContextList(result);
  else if (tool === "get_namespaces")       body = renderNamespaces(result);
  else if (tool === "list_namespace_resources") body = renderNamespaceResources(result);
  else if (tool === "list_services")        body = renderListServices(result);
  else if (tool === "find_workload")        body = renderFindWorkload(result);
  else if (tool === "get_resource_graph")   body = <ResourceGraph data={result as Parameters<typeof ResourceGraph>[0]["data"]} />;
  else                                      body = renderGeneric(result);

  return (
    <div
      className="rounded-xl p-4 text-sm"
      style={{ background: "var(--bg-surface-2)", border: "1px solid var(--border)" }}
    >
      {body}
      <div className="mt-3 flex justify-between items-center" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.5rem" }}>
        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>tool: {tool}</span>
        <button
          onClick={() => setShowRaw(!showRaw)}
          className="text-xs underline transition"
          style={{ color: "var(--text-muted)" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "var(--brand)")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
        >
          {showRaw ? "Hide raw" : "Show raw JSON"}
        </button>
      </div>
      {showRaw && <CodeBlock code={JSON.stringify(result, null, 2)} />}
    </div>
  );
}
