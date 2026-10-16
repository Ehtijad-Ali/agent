"use client";

import * as React from "react";
import { Bot, Loader2, Plus, RefreshCw, Trash2 } from "lucide-react";

import {
  type Agent,
  type AgentOutput,
  ApiError,
  createAgent,
  deleteAgent,
  generateOutput,
  listAgentTypes,
  listAgents,
  listOutputs,
  markOutputPublished,
  remainingCities,
  updateAgent,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

type AgentTypeInfo = {
  type: "engagement" | "content";
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
  const [agentType, setAgentType] = React.useState<"engagement" | "content">(
    types[0]?.type ?? "content",
  );
  const [description, setDescription] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Rules are left at their defaults here; they are edited on the agent
      // itself, where the type-specific fields are known.
      const agent = await createAgent({ name, agentType, description, enabled: true });
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
            onChange={(e) => setAgentType(e.target.value as "engagement" | "content")}
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

      <div className="space-y-2">
        <Label htmlFor="agent-desc">What should this agent do?</Label>
        <Textarea
          id="agent-desc"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe the job in your own words."
          disabled={busy}
        />
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
      ) : (
        <p className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">
          This agent watches the connected platforms, scores what it finds and
          drafts replies. Its results appear in the Inbox, not here.
        </p>
      )}
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
