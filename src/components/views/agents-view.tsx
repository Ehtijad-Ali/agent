"use client";

import * as React from "react";
import { Bot, Download, Loader2, Play, Plus, RefreshCw, Trash2 } from "lucide-react";

import {
  type Agent,
  type AgentOutput,
  type AgentType,
  type BacklinkAudit,
  type BacklinkResult,
  ApiError,
  auditCsvUrl,
  createAgent,
  deleteAgent,
  generateOutput,
  getAudit,
  listAgentTypes,
  listAgents,
  listOutputs,
  markOutputPublished,
  remainingCities,
  startAudit,
  updateAgent,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

type AgentTypeInfo = {
  type: AgentType;
  label: string;
  description: string;
};

/**
 * Agents (brief §2, §3).
 *
 * Create as many agents as you like, each with its own rules. A content agent
 * generates one ad per US city and never repeats a city -- that is enforced by
 * the database, so this screen can simply ask for "the next one" and trust it.
 *
 * Nothing here posts anything. Generated content is copied out by a person,
 * who then records where they published it.
 */
export function AgentsView() {
  const [types, setTypes] = React.useState<AgentTypeInfo[]>([]);
  const [agents, setAgents] = React.useState<Agent[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      const [t, a] = await Promise.all([listAgentTypes(), listAgents()]);
      setTypes(t.types as AgentTypeInfo[]);
      setAgents(a);
      setSelected((cur) => cur ?? a[0]?.id ?? null);
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load agents.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const current = agents.find((a) => a.id === selected) ?? null;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading agents…
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">AI agents</h1>
          <p className="text-sm text-muted-foreground">
            Create agents that monitor platforms or generate content. Each runs
            under its own rules, and nothing is published without you.
          </p>
        </div>
        <Button onClick={() => setCreating(true)} disabled={creating}>
          <Plus className="mr-2 h-4 w-4" /> New agent
        </Button>
      </header>

      {error ? (
        <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {creating ? (
        <CreateAgent
          types={types}
          onCancel={() => setCreating(false)}
          onCreated={async (agent) => {
            setCreating(false);
            await refresh();
            setSelected(agent.id);
          }}
        />
      ) : null}

      <div className="grid flex-1 gap-4 md:grid-cols-[260px_1fr]">
        <aside className="space-y-1 rounded-lg border bg-card p-2">
          {agents.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">
              No agents yet. Create one to get started.
            </p>
          ) : (
            agents.map((a) => (
              <button
                key={a.id}
                onClick={() => setSelected(a.id)}
                className={`flex w-full items-start gap-2 rounded-md p-2 text-left text-sm transition-colors ${
                  a.id === selected ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                }`}
              >
                <Bot className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{a.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {a.agentType} · {a.enabled ? "enabled" : "disabled"}
                  </span>
                </span>
              </button>
            ))
          )}
        </aside>

        <section className="min-w-0 rounded-lg border bg-card p-4">
          {current ? (
            <AgentDetail key={current.id} agent={current} onChanged={refresh} />
          ) : (
            <p className="text-sm text-muted-foreground">
              Select an agent, or create one.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

function CreateAgent({
  types,
  onCancel,
  onCreated,
}: {
  types: AgentTypeInfo[];
  onCancel: () => void;
  onCreated: (agent: Agent) => void;
}) {
  const [name, setName] = React.useState("");
  const [agentType, setAgentType] = React.useState<AgentType>(
    types[0]?.type ?? "content",
  );
  const [description, setDescription] = React.useState("");
  const [sheetUrl, setSheetUrl] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Rules are left at their defaults here, except the sheet a backlink
      // audit reads -- without it the new agent could not do anything.
      const rules =
        agentType === "backlink_audit" && sheetUrl.trim()
          ? { sheetUrl: sheetUrl.trim() }
          : undefined;
      const agent = await createAgent({ name, agentType, description, enabled: true, rules });
      onCreated(agent);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not create the agent.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-lg border bg-card p-4">
      <h2 className="font-medium">New agent</h2>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="agent-name">Name</Label>
          <Input
            id="agent-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="US classifieds — East Coast"
            disabled={busy}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="agent-type">Type</Label>
          <select
            id="agent-type"
            value={agentType}
            onChange={(e) => setAgentType(e.target.value as AgentType)}
            disabled={busy}
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
          >
            {types.map((t) => (
              <option key={t.type} value={t.type}>
                {t.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-muted-foreground">
            {types.find((t) => t.type === agentType)?.description}
          </p>
        </div>
      </div>

      {agentType === "backlink_audit" ? (
        <div className="space-y-2">
          <Label htmlFor="agent-sheet">Google Sheet link</Label>
          <Input
            id="agent-sheet"
            value={sheetUrl}
            onChange={(e) => setSheetUrl(e.target.value)}
            placeholder="https://docs.google.com/spreadsheets/d/…/edit"
            disabled={busy}
          />
          <p className="text-xs text-muted-foreground">
            Page URLs are read from column A. The sheet must be shared as
            “Anyone with the link can view”.
          </p>
        </div>
      ) : null}

      <div className="space-y-2">
        <Label htmlFor="agent-desc">Notes (optional)</Label>
        <Textarea
          id="agent-desc"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="For your own reference."
          disabled={busy}
        />
        <p className="text-xs text-muted-foreground">
          The agent does the job of its type above. Notes are not instructions
          it follows.
        </p>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button type="submit" disabled={busy || !name.trim()}>
          {busy ? "Creating…" : "Create agent"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function AgentDetail({ agent, onChanged }: { agent: Agent; onChanged: () => void }) {
  const [outputs, setOutputs] = React.useState<AgentOutput[]>([]);
  const [remaining, setRemaining] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const isContent = agent.agentType === "content";

  const load = React.useCallback(async () => {
    if (!isContent) return;
    try {
      const [o, c] = await Promise.all([listOutputs(agent.id), remainingCities(agent.id)]);
      setOutputs(o);
      setRemaining(c.remaining);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load output.");
    }
  }, [agent.id, isContent]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      await generateOutput(agent.id);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not generate.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-medium">{agent.name}</h2>
          <p className="text-sm text-muted-foreground">
            {agent.description || <span className="italic">No description</span>}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Switch
              id={`enabled-${agent.id}`}
              checked={agent.enabled}
              onCheckedChange={async (enabled) => {
                await updateAgent(agent.id, { enabled });
                onChanged();
              }}
            />
            <Label htmlFor={`enabled-${agent.id}`} className="text-sm">
              Enabled
            </Label>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Delete agent"
            onClick={async () => {
              await deleteAgent(agent.id);
              onChanged();
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {isContent ? (
        <>
          <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/30 p-3">
            <Button onClick={generate} disabled={busy || !agent.enabled || remaining === 0}>
              {busy ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              Generate next city
            </Button>
            <span className="text-sm text-muted-foreground">
              {remaining === null
                ? "…"
                : remaining === 0
                  ? "Every city has been used."
                  : `${remaining} cities remaining`}
            </span>
            {!agent.enabled ? (
              <span className="text-sm text-amber-600">Enable the agent to generate.</span>
            ) : null}
          </div>

          <div className="space-y-3">
            <h3 className="text-sm font-medium">
              Generated content ({outputs.length})
            </h3>
            {outputs.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing generated yet.
              </p>
            ) : (
              outputs.map((o) => <OutputCard key={o.id} output={o} onChanged={load} />)
            )}
          </div>
        </>
      ) : agent.agentType === "backlink_audit" ? (
        <BacklinkAuditPanel agent={agent} onChanged={onChanged} />
      ) : (
        <p className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">
          This agent watches the connected platforms, scores what it finds and
          drafts replies. Its results appear in the Inbox, not here.
        </p>
      )}
    </div>
  );
}

const RESULT_LABEL: Record<BacklinkResult, string> = {
  dofollow: "Dofollow",
  nofollow: "Nofollow",
  not_found: "No link",
  error: "Error",
};

const RESULT_CLASS: Record<BacklinkResult, string> = {
  dofollow: "bg-primary/10 text-primary",
  nofollow: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  not_found: "bg-muted text-muted-foreground",
  error: "bg-destructive/10 text-destructive",
};

/**
 * Backlink audit: read page URLs from a Google Sheet, check each page for a
 * link to our domain and whether it is dofollow. Runs on the server; this
 * polls while it does, and the CSV lines up with the sheet for pasting back.
 */
function BacklinkAuditPanel({ agent, onChanged }: { agent: Agent; onChanged: () => void }) {
  const savedSheet = String(agent.rules.sheetUrl ?? "");
  const [sheet, setSheet] = React.useState(savedSheet);
  const [audit, setAudit] = React.useState<BacklinkAudit | null>(null);
  const [filter, setFilter] = React.useState<"all" | BacklinkResult>("all");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      setAudit(await getAudit(agent.id));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load results.");
    }
  }, [agent.id]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const running = audit?.status === "running";

  React.useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(timer);
  }, [running, load]);

  async function saveSheet() {
    setBusy(true);
    setError(null);
    try {
      await updateAgent(agent.id, { rules: { ...agent.rules, sheetUrl: sheet.trim() } });
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not save the sheet link.");
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setAudit(await startAudit(agent.id));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not start the audit.");
    } finally {
      setBusy(false);
    }
  }

  const rows = (audit?.items ?? []).filter((r) => filter === "all" || r.result === filter);
  const dirty = sheet.trim() !== savedSheet;

  return (
    <div className="space-y-4">
      <div className="space-y-2 rounded-md border bg-muted/30 p-3">
        <Label htmlFor={`sheet-${agent.id}`}>Google Sheet link</Label>
        <div className="flex flex-wrap gap-2">
          <Input
            id={`sheet-${agent.id}`}
            value={sheet}
            onChange={(e) => setSheet(e.target.value)}
            placeholder="https://docs.google.com/spreadsheets/d/…/edit"
            className="min-w-[240px] flex-1"
            disabled={busy || running}
          />
          {dirty ? (
            <Button variant="secondary" onClick={saveSheet} disabled={busy}>
              Save
            </Button>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">
          Checks every URL in column A for a link to{" "}
          {String(agent.rules.targetDomain ?? "all-bettors.com")} and whether it is
          dofollow. Share the sheet as “Anyone with the link can view”.
        </p>
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button
            onClick={run}
            disabled={busy || running || !agent.enabled || !savedSheet || dirty}
          >
            {running ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            {running ? "Checking…" : "Run audit"}
          </Button>
          {running && audit ? (
            <span className="text-sm text-muted-foreground">
              {audit.total ? `${audit.done} of ${audit.total} pages checked` : "Reading the sheet…"}
            </span>
          ) : null}
          {audit && audit.items.length > 0 && !running ? (
            <Button variant="outline" asChild>
              <a href={auditCsvUrl(agent.id)} download>
                <Download className="mr-2 h-4 w-4" /> Download CSV
              </a>
            </Button>
          ) : null}
          {!agent.enabled ? (
            <span className="text-sm text-amber-600">Enable the agent to run it.</span>
          ) : null}
        </div>
      </div>

      {error || audit?.error ? (
        <p role="alert" className="text-sm text-destructive">
          {error ?? audit?.error}
        </p>
      ) : null}

      {audit && audit.items.length > 0 ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {(["all", "dofollow", "nofollow", "not_found", "error"] as const).map((key) => {
              const count = key === "all" ? audit.items.length : (audit.counts[key] ?? 0);
              return (
                <button
                  key={key}
                  onClick={() => setFilter(key)}
                  className={`rounded-md border px-2.5 py-1 text-xs ${
                    filter === key ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                  }`}
                >
                  {key === "all" ? "All" : RESULT_LABEL[key]} ({count})
                </button>
              );
            })}
          </div>
          <div className="max-h-[480px] overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-card text-left text-xs text-muted-foreground">
                <tr>
                  <th className="p-2 font-medium">Row</th>
                  <th className="p-2 font-medium">Page</th>
                  <th className="p-2 font-medium">Result</th>
                  <th className="hidden p-2 font-medium md:table-cell">Detail</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 500).map((r) => (
                  <tr key={r.row} className="border-t align-top">
                    <td className="p-2 tabular-nums text-muted-foreground">{r.row}</td>
                    <td className="max-w-[320px] p-2">
                      <a href={r.pageUrl} target="_blank" rel="noreferrer" className="block truncate underline">
                        {r.pageUrl}
                      </a>
                    </td>
                    <td className="p-2">
                      <span className={`whitespace-nowrap rounded px-2 py-0.5 text-xs ${RESULT_CLASS[r.result]}`}>
                        {RESULT_LABEL[r.result]}
                      </span>
                    </td>
                    <td className="hidden p-2 text-xs text-muted-foreground md:table-cell">{r.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > 500 ? (
            <p className="text-xs text-muted-foreground">
              Showing the first 500 of {rows.length}. Download the CSV for all of them.
            </p>
          ) : null}
        </div>
      ) : audit && !running ? (
        <p className="text-sm text-muted-foreground">No audit has been run yet.</p>
      ) : null}
    </div>
  );
}

function OutputCard({ output, onChanged }: { output: AgentOutput; onChanged: () => void }) {
  const [url, setUrl] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  return (
    <article className="space-y-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">
          {output.city}, {output.state} {output.zipcode}
        </span>
        <span
          className={`rounded px-2 py-0.5 text-xs ${
            output.status === "published"
              ? "bg-primary/10 text-primary"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {output.status}
        </span>
      </div>

      <p className="text-sm font-medium">{output.title}</p>
      <p className="whitespace-pre-wrap text-sm text-muted-foreground">{output.body}</p>
      <p className="text-xs text-muted-foreground">Contact: {output.contactEmail}</p>

      {output.publishedUrl ? (
        <p className="text-xs">
          Published:{" "}
          <a href={output.publishedUrl} className="underline" target="_blank" rel="noreferrer">
            {output.publishedUrl}
          </a>
        </p>
      ) : (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              await markOutputPublished(output.id, url);
              await onChanged();
            } finally {
              setBusy(false);
            }
          }}
        >
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste the URL where you posted this"
            className="min-w-[240px] flex-1"
            disabled={busy}
          />
          <Button type="submit" variant="secondary" disabled={busy || !url.trim()}>
            Record URL
          </Button>
        </form>
      )}
    </article>
  );
}
