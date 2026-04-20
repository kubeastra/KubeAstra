"use client";

import { useState, useEffect } from "react";
import { AlertTriangle, Play, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { TabId } from "./Sidebar";

interface Props {
  tab: TabId;
  onResult: (r: Record<string, unknown>) => void;
  onLoading: (v: boolean) => void;
  onError: (e: string | null) => void;
}

// ── Shared primitives ─────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs font-medium text-gray-400 mb-1.5">{children}</label>;
}

function Input({
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors"
    />
  );
}

function TextArea({
  value,
  onChange,
  placeholder,
  rows = 8,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors resize-y"
    />
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <div
        onClick={() => onChange(!value)}
        className={`w-9 h-5 rounded-full transition-colors ${value ? "bg-blue-600" : "bg-gray-700"} relative`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${value ? "translate-x-4" : ""}`}
        />
      </div>
      <span className="text-xs text-gray-400">{label}</span>
    </label>
  );
}

function SubmitButton({
  loading,
  disabled,
  label = "Run",
}: {
  loading: boolean;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <button
      type="submit"
      disabled={loading || disabled}
      className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm font-medium text-white transition-colors"
    >
      {loading ? (
        <RefreshCw size={14} className="animate-spin" />
      ) : (
        <Play size={14} />
      )}
      {loading ? "Running..." : label}
    </button>
  );
}

// ── Tab forms ─────────────────────────────────────────────────────────────────

function AnalyzeTab({ onResult, onLoading, onError }: Props) {
  const [tool, setTool] = useState("analyze");
  const [errorText, setErrorText] = useState("");
  const [toolType, setToolType] = useState("kubernetes");
  const [env, setEnv] = useState("production");
  const [category, setCategory] = useState("");
  const [namespace, setNamespace] = useState("");
  const [resourceName, setResourceName] = useState("");
  const [eventsText, setEventsText] = useState("");
  const [errors, setErrors] = useState("");
  const [loading, setLoading] = useState(false);
  const [categories, setCategories] = useState<Record<string, string>>({});

  useEffect(() => {
    api.categories().then((d) => setCategories(d as Record<string, string>)).catch(() => {});
  }, []);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    onLoading(true);
    onError(null);
    try {
      let result: unknown;
      if (tool === "analyze") result = await api.analyze({ error_text: errorText, tool: toolType, environment: env });
      else if (tool === "fix") result = await api.fix({ error_text: errorText || undefined, category: category || undefined, tool: toolType, namespace: namespace || "<namespace>", resource_name: resourceName || "<name>" });
      else if (tool === "runbook") result = await api.runbook({ error_text: errorText || undefined, category: category || undefined, tool: toolType });
      else if (tool === "report") result = await api.report({ events_text: eventsText });
      else result = await api.summary({ errors: errors.split("\n").filter(Boolean), tool: toolType });
      onResult(result as Record<string, unknown>);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setLoading(false);
      onLoading(false);
    }
  };

  return (
    <form onSubmit={run} className="space-y-4">
      <div>
        <Label>Tool</Label>
        <Select
          value={tool}
          onChange={setTool}
          options={[
            { value: "analyze", label: "Analyze Error (Gemini + RAG)" },
            { value: "fix", label: "Get Fix Commands" },
            { value: "runbook", label: "Generate Runbook" },
            { value: "report", label: "Cluster Report (paste events)" },
            { value: "summary", label: "Error Summary (batch)" },
          ]}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Tool type</Label>
          <Select
            value={toolType}
            onChange={setToolType}
            options={[
              { value: "kubernetes", label: "Kubernetes" },
              { value: "ansible", label: "Ansible" },
              { value: "helm", label: "Helm" },
            ]}
          />
        </div>
        {tool === "analyze" && (
          <div>
            <Label>Environment</Label>
            <Select
              value={env}
              onChange={setEnv}
              options={[
                { value: "production", label: "Production" },
                { value: "staging", label: "Staging" },
                { value: "dev", label: "Dev" },
              ]}
            />
          </div>
        )}
      </div>

      {(tool === "fix" || tool === "runbook") && (
        <div>
          <Label>Category (or leave blank to auto-detect)</Label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">-- auto-detect from error text --</option>
            {Object.entries(categories).map(([k, v]) => (
              <option key={k} value={k}>{k} — {v}</option>
            ))}
          </select>
        </div>
      )}

      {tool === "fix" && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Namespace</Label>
            <Input value={namespace} onChange={setNamespace} placeholder="my-namespace" />
          </div>
          <div>
            <Label>Resource name</Label>
            <Input value={resourceName} onChange={setResourceName} placeholder="my-pod-xyz" />
          </div>
        </div>
      )}

      {tool === "report" ? (
        <div>
          <Label>Paste kubectl events output</Label>
          <TextArea
            value={eventsText}
            onChange={setEventsText}
            placeholder={"kubectl get events --all-namespaces --sort-by='.lastTimestamp'"}
            rows={10}
          />
        </div>
      ) : tool === "summary" ? (
        <div>
          <Label>Errors (one per line)</Label>
          <TextArea
            value={errors}
            onChange={setErrors}
            placeholder={"Error 1...\nError 2...\nError 3..."}
            rows={8}
          />
        </div>
      ) : (
        <div>
          <Label>Error text</Label>
          <TextArea
            value={errorText}
            onChange={setErrorText}
            placeholder="Paste your Kubernetes or Ansible error here..."
            rows={10}
          />
        </div>
      )}

      <SubmitButton loading={loading} disabled={!errorText && !eventsText && !errors && !category} />
    </form>
  );
}

function InvestigateTab({ onResult, onLoading, onError }: Props) {
  const [tool, setTool] = useState("investigate");
  const [namespace, setNamespace] = useState("");
  const [podName, setPodName] = useState("");
  const [labelSelector, setLabelSelector] = useState("");
  const [workloadName, setWorkloadName] = useState("");
  const [tail, setTail] = useState("200");
  const [previous, setPrevious] = useState(false);
  const [useAi, setUseAi] = useState(true);
  const [loading, setLoading] = useState(false);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    onLoading(true);
    onError(null);
    try {
      let result: unknown;
      if (tool === "investigate") result = await api.investigate({ namespace, pod_name: podName, tail: parseInt(tail), use_ai: useAi });
      else if (tool === "pods") result = await api.pods({ namespace, label_selector: labelSelector || undefined });
      else if (tool === "describe") result = await api.describe({ namespace, pod_name: podName });
      else if (tool === "logs") result = await api.logs({ namespace, pod_name: podName, previous, tail: parseInt(tail) });
      else if (tool === "events") result = await api.events({ namespace });
      else result = await api.find({ name: workloadName });
      onResult(result as Record<string, unknown>);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setLoading(false);
      onLoading(false);
    }
  };

  return (
    <form onSubmit={run} className="space-y-4">
      <div>
        <Label>Tool</Label>
        <Select
          value={tool}
          onChange={setTool}
          options={[
            { value: "investigate", label: "Investigate Pod (full triage + AI)" },
            { value: "pods", label: "List Pods" },
            { value: "describe", label: "Describe Pod" },
            { value: "logs", label: "Get Pod Logs" },
            { value: "events", label: "Get Events" },
            { value: "find", label: "Find Workload" },
          ]}
        />
      </div>

      {tool === "find" ? (
        <div>
          <Label>Workload name</Label>
          <Input value={workloadName} onChange={setWorkloadName} placeholder="my-service" />
        </div>
      ) : (
        <div>
          <Label>Namespace</Label>
          <Input value={namespace} onChange={setNamespace} placeholder="prod" />
        </div>
      )}

      {["investigate", "describe", "logs"].includes(tool) && (
        <div>
          <Label>Pod name</Label>
          <Input value={podName} onChange={setPodName} placeholder="my-app-7d4f9b-xyz" />
        </div>
      )}

      {tool === "pods" && (
        <div>
          <Label>Label selector (optional)</Label>
          <Input value={labelSelector} onChange={setLabelSelector} placeholder="app=my-app" />
        </div>
      )}

      {["investigate", "logs"].includes(tool) && (
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <Label>Tail lines</Label>
            <Input value={tail} onChange={setTail} placeholder="200" type="number" />
          </div>
          {tool === "logs" && (
            <div className="mt-5">
              <Toggle label="Previous container" value={previous} onChange={setPrevious} />
            </div>
          )}
          {tool === "investigate" && (
            <div className="mt-5">
              <Toggle label="AI analysis" value={useAi} onChange={setUseAi} />
            </div>
          )}
        </div>
      )}

      <SubmitButton loading={loading} disabled={!namespace && !workloadName} />
    </form>
  );
}

function ClusterTab({ onResult, onLoading, onError }: Props) {
  const [tool, setTool] = useState("deployment");
  const [namespace, setNamespace] = useState("");
  const [deploymentName, setDeploymentName] = useState("");
  const [serviceName, setServiceName] = useState("");
  const [loading, setLoading] = useState(false);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    onLoading(true);
    onError(null);
    try {
      let result: unknown;
      if (tool === "deployment") result = await api.deployment({ namespace, deployment_name: deploymentName });
      else if (tool === "service") result = await api.service({ namespace, service_name: serviceName });
      else if (tool === "endpoints") result = await api.endpoints({ namespace, service_name: serviceName });
      else result = await api.rolloutStatus({ namespace, deployment_name: deploymentName });
      onResult(result as Record<string, unknown>);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setLoading(false);
      onLoading(false);
    }
  };

  return (
    <form onSubmit={run} className="space-y-4">
      <div>
        <Label>Tool</Label>
        <Select
          value={tool}
          onChange={setTool}
          options={[
            { value: "deployment", label: "Get Deployment" },
            { value: "rollout", label: "Rollout Status" },
            { value: "service", label: "Get Service" },
            { value: "endpoints", label: "Get Endpoints" },
          ]}
        />
      </div>
      <div>
        <Label>Namespace</Label>
        <Input value={namespace} onChange={setNamespace} placeholder="prod" />
      </div>
      {["deployment", "rollout"].includes(tool) ? (
        <div>
          <Label>Deployment name</Label>
          <Input value={deploymentName} onChange={setDeploymentName} placeholder="my-deployment" />
        </div>
      ) : (
        <div>
          <Label>Service name</Label>
          <Input value={serviceName} onChange={setServiceName} placeholder="my-service" />
        </div>
      )}
      <SubmitButton loading={loading} disabled={!namespace} />
    </form>
  );
}

function MulticlusterTab({ onResult, onLoading, onError }: Props) {
  const [tool, setTool] = useState("list");
  const [contextName, setContextName] = useState("");
  const [sshConn, setSshConn] = useState("");
  const [sshPassword, setSshPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    onLoading(true);
    onError(null);
    try {
      let result: unknown;
      if (tool === "list") result = await api.contexts();
      else if (tool === "current") result = await api.currentContext();
      else if (tool === "switch") result = await api.switchContext(contextName);
      else result = await api.addContext({
        ssh_connection: sshConn,
        password: sshPassword || undefined,
        context_name: contextName || undefined,
      });
      onResult(result as Record<string, unknown>);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setLoading(false);
      onLoading(false);
    }
  };

  return (
    <form onSubmit={run} className="space-y-4">
      <div>
        <Label>Tool</Label>
        <Select
          value={tool}
          onChange={setTool}
          options={[
            { value: "list", label: "List Contexts" },
            { value: "current", label: "Current Context" },
            { value: "switch", label: "Switch Context" },
            { value: "add", label: "Add Context via SSH" },
          ]}
        />
      </div>
      {tool === "switch" && (
        <div>
          <Label>Context name</Label>
          <Input value={contextName} onChange={setContextName} placeholder="my-cluster" />
        </div>
      )}
      {tool === "add" && (
        <>
          <div>
            <Label>SSH connection (user@hostname)</Label>
            <Input value={sshConn} onChange={setSshConn} placeholder="ansible@k8s-master.example.com" />
          </div>
          <div>
            <Label>SSH password (optional, blank = key-based)</Label>
            <Input value={sshPassword} onChange={setSshPassword} type="password" placeholder="Leave blank for key-based auth" />
          </div>
        </>
      )}
      <SubmitButton loading={loading} />
    </form>
  );
}

function RecoveryTab({ onResult, onLoading, onError }: Props) {
  const [tool, setTool] = useState("restart");
  const [namespace, setNamespace] = useState("");
  const [podName, setPodName] = useState("");
  const [deploymentName, setDeploymentName] = useState("");
  const [command, setCommand] = useState("");
  const [replicas, setReplicas] = useState("1");
  const [patch, setPatch] = useState("");
  const [resourceType, setResourceType] = useState("deployment");
  const [resourceName, setResourceName] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [loading, setLoading] = useState(false);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    onLoading(true);
    onError(null);
    try {
      let result: unknown;
      if (tool === "restart") result = await api.restart({ namespace, deployment_name: deploymentName, confirm });
      else if (tool === "scale") result = await api.scale({ namespace, deployment_name: deploymentName, replicas: parseInt(replicas), confirm });
      else if (tool === "delete") result = await api.deletePod({ namespace, pod_name: podName, confirm });
      else if (tool === "exec") result = await api.exec({ namespace, pod_name: podName, command, confirm });
      else result = await api.patch({ namespace, resource_type: resourceType, resource_name: resourceName, patch, confirm });
      onResult(result as Record<string, unknown>);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setLoading(false);
      onLoading(false);
    }
  };

  return (
    <form onSubmit={run} className="space-y-4">
      {/* Warning banner */}
      <div className="flex items-start gap-3 rounded-lg border border-orange-800 bg-orange-950/40 px-4 py-3">
        <AlertTriangle size={16} className="text-orange-400 mt-0.5 shrink-0" />
        <div>
          <p className="text-xs font-medium text-orange-300">Write Operations</p>
          <p className="text-xs text-orange-400/80 mt-0.5">
            These tools modify cluster state. You must toggle Confirm before running.
            Requires <code className="font-mono">ENABLE_RECOVERY_OPERATIONS=true</code> in the backend .env.
          </p>
        </div>
      </div>

      <div>
        <Label>Operation</Label>
        <Select
          value={tool}
          onChange={setTool}
          options={[
            { value: "restart", label: "Rollout Restart (deployment)" },
            { value: "scale", label: "Scale Deployment" },
            { value: "delete", label: "Delete Pod" },
            { value: "exec", label: "Exec Command in Pod" },
            { value: "patch", label: "Apply JSON Patch" },
          ]}
        />
      </div>

      <div>
        <Label>Namespace</Label>
        <Input value={namespace} onChange={setNamespace} placeholder="prod" />
      </div>

      {["restart", "scale"].includes(tool) && (
        <div>
          <Label>Deployment name</Label>
          <Input value={deploymentName} onChange={setDeploymentName} placeholder="my-deployment" />
        </div>
      )}

      {["delete", "exec"].includes(tool) && (
        <div>
          <Label>Pod name</Label>
          <Input value={podName} onChange={setPodName} placeholder="my-pod-7d4f9b-xyz" />
        </div>
      )}

      {tool === "scale" && (
        <div>
          <Label>Replicas</Label>
          <Input value={replicas} onChange={setReplicas} type="number" placeholder="3" />
        </div>
      )}

      {tool === "exec" && (
        <div>
          <Label>Command</Label>
          <Input value={command} onChange={setCommand} placeholder="ls -lh /var/lib/postgresql/" />
        </div>
      )}

      {tool === "patch" && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Resource type</Label>
              <Select
                value={resourceType}
                onChange={setResourceType}
                options={[
                  { value: "deployment", label: "deployment" },
                  { value: "statefulset", label: "statefulset" },
                  { value: "pod", label: "pod" },
                  { value: "service", label: "service" },
                  { value: "configmap", label: "configmap" },
                ]}
              />
            </div>
            <div>
              <Label>Resource name</Label>
              <Input value={resourceName} onChange={setResourceName} placeholder="my-deployment" />
            </div>
          </div>
          <div>
            <Label>JSON patch</Label>
            <TextArea
              value={patch}
              onChange={setPatch}
              placeholder={'{"spec":{"template":{"spec":{"containers":[{"name":"app","resources":{"limits":{"memory":"1Gi"}}}]}}}}'}
              rows={5}
            />
          </div>
        </>
      )}

      <div className="flex items-center justify-between pt-2 border-t border-gray-800">
        <Toggle label="I confirm this write operation" value={confirm} onChange={setConfirm} />
        <SubmitButton
          loading={loading}
          disabled={!namespace || !confirm}
          label={confirm ? "Execute" : "Toggle confirm first"}
        />
      </div>
    </form>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function ToolForm(props: Props) {
  const { tab } = props;
  if (tab === "analyze") return <AnalyzeTab {...props} />;
  if (tab === "investigate") return <InvestigateTab {...props} />;
  if (tab === "cluster") return <ClusterTab {...props} />;
  if (tab === "multicluster") return <MulticlusterTab {...props} />;
  if (tab === "recovery") return <RecoveryTab {...props} />;
  return null;
}
