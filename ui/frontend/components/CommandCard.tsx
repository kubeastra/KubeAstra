"use client";

import { useState } from "react";
import { Copy, Check, Terminal } from "lucide-react";

interface Command {
  cmd: string;
  description?: string;
}

interface Props {
  commands: Command[];
  title?: string;
}

export default function CommandCard({ commands, title = "Commands" }: Props) {
  if (!commands || commands.length === 0) return null;

  return (
    <div className="rounded-lg border border-gray-700 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 border-b border-gray-700">
        <Terminal size={14} className="text-gray-400" />
        <span className="text-xs font-medium text-gray-300">{title}</span>
      </div>
      <div className="divide-y divide-gray-800">
        {commands.map((c, i) => (
          <CommandRow key={i} cmd={c.cmd} description={c.description} />
        ))}
      </div>
    </div>
  );
}

function CommandRow({ cmd, description }: { cmd: string; description?: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(cmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="px-4 py-3 bg-gray-900 group">
      {description && (
        <p className="text-xs text-gray-500 mb-1.5">{description}</p>
      )}
      <div className="flex items-start justify-between gap-3">
        <code className="text-sm text-green-400 font-mono break-all leading-relaxed">
          {cmd}
        </code>
        <button
          onClick={handleCopy}
          className="shrink-0 mt-0.5 p-1 rounded text-gray-600 hover:text-gray-300 hover:bg-gray-700 transition-colors"
          title="Copy command"
        >
          {copied ? (
            <Check size={14} className="text-green-400" />
          ) : (
            <Copy size={14} />
          )}
        </button>
      </div>
    </div>
  );
}
