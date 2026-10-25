"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Download,
  Eraser,
  Loader2,
  MessageSquarePlus,
  Send,
  Settings2,
  Sparkles,
  Square,
  Trash2,
  Wrench,
  X,
} from "lucide-react";

import {
  type AgentChat,
  type AgentChatDetail,
  type AgentMessage,
  type AgentStatus,
  type AgentTask,
  ApiError,
  agentFileUrl,
  cancelAgentTask,
  clearAgentChat,
  createAgentChat,
  decideAgentTask,
  deleteAgentChat,
  getAgentChat,
  getAgentStatus,
  listAgentChats,
  sendAgentMessage,
  updateAgentChat,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const ACTIVE = new Set(["pending", "running", "waiting_approval"]);

const STATUS_LABEL: Record<string, string> = {
  pending: "Starting…",
  running: "Working…",
  waiting_approval: "Waiting for your approval",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Stopped",
};

const TOOL_LABEL: Record<string, string> = {
  web_search: "Searched the web",
  fetch_url: "Read a web page",
  read_spreadsheet: "Read a spreadsheet",
  check_backlinks: "Checked backlinks",
  search_leads: "Searched leads",
  platform_status: "Checked platforms",
  save_csv: "Saved a CSV file",
  update_lead_status: "Changed a lead's status",
};

// The project has no typography plugin, so agent replies (Markdown with
// lists and tables) are styled here.
const MARKDOWN = [
  "max-w-none text-sm leading-relaxed",
  "[&_p]:my-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5",
  "[&_h1]:mt-3 [&_h1]:font-semibold [&_h2]:mt-3 [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:font-medium",
  "[&_a]:underline [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground",
  "[&_table]:my-2 [&_table]:block [&_table]:overflow-x-auto [&_table]:text-xs",
  "[&_th]:border [&_th]:bg-muted [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_td]:border [&_td]:px-2 [&_td]:py-1 [&_td]:align-top",
].join(" ");

// Phrased as what the agent is asking permission to do.
const ACTION_LABEL: Record<string, string> = {
  update_lead_status: "change a lead's status",
};

function errorText(cause: unknown, fallback: string): string {
  return cause instanceof ApiError ? cause.message : fallback;
}

/**
 * AI agent chat.
 *
 * Describe a task in your own words; the agent plans it and uses the tools
 * the backend exposes (web search, pages, sheets, backlinks, leads, CSV
 * files). Anything that changes a record waits for an Approve click here.
 * The agent runs server-side, so closing the page does not stop it.
 */
export function AssistantView() {
  const [status, setStatus] = React.useState<AgentStatus | null>(null);
  const [chats, setChats] = React.useState<AgentChat[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const loadChats = React.useCallback(async () => {
    try {
      const [s, c] = await Promise.all([getAgentStatus(), listAgentChats()]);
      setStatus(s);
      setChats(c);
      setSelected((cur) => cur ?? c[0]?.id ?? null);
    } catch (cause) {
      setError(errorText(cause, "Could not load the agent."));
    }
  }, []);

  React.useEffect(() => {
    void loadChats();
  }, [loadChats]);

  async function newChat() {
    try {
      const chat = await createAgentChat();
      setChats((c) => [chat, ...c]);
      setSelected(chat.id);
    } catch (cause) {
      setError(errorText(cause, "Could not start a chat."));
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">AI Agent</h1>
          <p className="text-sm text-muted-foreground">
            Describe a task in your own words. The agent plans it, uses its tools,
            and asks before changing anything.
          </p>
          {status?.configured ? (
            <p className="mt-1 text-xs text-muted-foreground">
              {status.provider === "ollama"
                ? `Runs on your own server (local AI: ${status.model}). No usage limits; each step can take a minute, so give it time on bigger tasks.`
                : `Runs on Groq (${status.model}).`}
            </p>
          ) : null}
        </div>
        <Button onClick={newChat}>
          <MessageSquarePlus className="mr-2 h-4 w-4" /> New chat
        </Button>
      </header>

      {status && !status.configured ? (
        <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          The agent is not configured: set GROQ_API_KEY in the backend environment.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[240px_1fr]">
        <aside className="hidden min-h-0 space-y-1 overflow-y-auto rounded-lg border bg-card p-2 md:block">
          {chats.length === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">No chats yet.</p>
          ) : (
            chats.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelected(c.id)}
                className={`block w-full truncate rounded-md px-2 py-2 text-left text-sm transition-colors ${
                  c.id === selected ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                }`}
              >
                {c.title}
              </button>
            ))
          )}
        </aside>

        <section className="flex min-h-[420px] min-w-0 flex-col rounded-lg border bg-card">
          {selected ? (
            <ChatPanel
              key={selected}
              chatId={selected}
              status={status}
              onChanged={loadChats}
              onDeleted={() => {
                setSelected(null);
                void loadChats();
              }}
            />
          ) : (
            <EmptyState status={status} onStart={newChat} />
          )}
        </section>
      </div>
    </div>
  );
}

function EmptyState({ status, onStart }: { status: AgentStatus | null; onStart: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <Sparkles className="h-8 w-8 text-primary" />
      <div className="max-w-md space-y-1">
        <p className="font-medium">Start a chat and tell the agent what you need</p>
        <p className="text-sm text-muted-foreground">
          For example: “Check the first 100 URLs in my sheet for dofollow links
          and give me a CSV”, or “Find leads asking about free prediction games
          this week”.
        </p>
      </div>
      <Button onClick={onStart}>New chat</Button>
      {status ? <ToolList status={status} /> : null}
    </div>
  );
}

function ToolList({ status }: { status: AgentStatus }) {
  return (
    <div className="max-w-lg text-left text-xs text-muted-foreground">
      <p className="mb-1 font-medium text-foreground">What it can do</p>
      <ul className="space-y-0.5">
        {status.tools.map((t) => (
          <li key={t.name}>
            <span className="font-medium">{TOOL_LABEL[t.name] ?? t.name}</span>
            {t.requiresApproval ? " (asks first)" : ""}: {t.description}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChatPanel({
  chatId,
  status,
  onChanged,
  onDeleted,
}: {
  chatId: string;
  status: AgentStatus | null;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const [detail, setDetail] = React.useState<AgentChatDetail | null>(null);
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [showSettings, setShowSettings] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  const load = React.useCallback(async () => {
    try {
      setDetail(await getAgentChat(chatId));
    } catch (cause) {
      setError(errorText(cause, "Could not load the chat."));
    }
  }, [chatId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const tasks = detail?.tasks ?? [];
  const latest: AgentTask | undefined = tasks[tasks.length - 1];
  const active = latest && ACTIVE.has(latest.status) ? latest : undefined;
  const polling = active && active.status !== "waiting_approval";

  // Poll while the agent works; it runs on the server, not in this request.
  React.useEffect(() => {
    if (!polling) return;
    const timer = window.setInterval(() => void load(), 1500);
    return () => window.clearInterval(timer);
  }, [polling, load]);

  const messageCount = detail?.messages.length ?? 0;
  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messageCount, active?.status]);

  async function send() {
    const text = draft.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      await sendAgentMessage(chatId, text);
      setDraft("");
      await load();
      onChanged();
    } catch (cause) {
      setError(errorText(cause, "Could not send."));
    } finally {
      setBusy(false);
    }
  }

  async function act(fn: () => Promise<unknown>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (cause) {
      setError(errorText(cause, fallback));
    } finally {
      setBusy(false);
    }
  }

  if (!detail) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  // Tool results keyed by the call that produced them, to render each call
  // and its outcome as one activity row.
  const results = new Map<string, AgentMessage>();
  for (const m of detail.messages) if (m.role === "tool" && m.toolCallId) results.set(m.toolCallId, m);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2">
        <h2 className="min-w-0 truncate font-medium">{detail.chat.title}</h2>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setShowSettings((s) => !s)}>
            <Settings2 className="mr-1.5 h-4 w-4" /> Instructions
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Clear conversation"
            title="Clear conversation (keeps instructions)"
            disabled={busy || !!active}
            onClick={() => act(() => clearAgentChat(chatId), "Could not clear.")}
          >
            <Eraser className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Delete chat"
            disabled={busy}
            onClick={async () => {
              await deleteAgentChat(chatId);
              onDeleted();
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {showSettings ? (
        <InstructionsEditor
          chatId={chatId}
          initial={detail.chat.instructions}
          onSaved={() => {
            setShowSettings(false);
            void load();
          }}
        />
      ) : null}

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {detail.messages.length === 0 ? (
          <div className="space-y-3 text-sm text-muted-foreground">
            <p>Tell the agent what you need. It will ask if something is unclear.</p>
            {status ? <ToolList status={status} /> : null}
          </div>
        ) : null}

        {detail.messages.map((m) => {
          if (m.role === "user") {
            return (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
                  {m.content}
                </div>
              </div>
            );
          }
          if (m.role === "assistant") {
            return (
              <div key={m.id} className="space-y-2">
                {m.content ? (
                  <div
                    className={`${MARKDOWN} ${
                      m.status === "failed" || m.status === "cancelled" ? "text-destructive" : ""
                    }`}
                  >
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  </div>
                ) : null}
                {(m.toolCalls ?? []).map((call) => (
                  <ToolRow
                    key={call.id}
                    name={call.function.name}
                    args={call.function.arguments}
                    result={results.get(call.id)}
                    awaiting={active?.status === "waiting_approval" && active.pendingAction?.name === call.function.name && !results.has(call.id)}
                    stopped={!results.has(call.id) && !active}
                  />
                ))}
              </div>
            );
          }
          return null;
        })}

        {active?.status === "waiting_approval" && active.pendingAction ? (
          <div className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3">
            <p className="flex items-center gap-2 text-sm font-medium">
              <AlertTriangle className="h-4 w-4 text-amber-600" /> The agent wants to{" "}
              {ACTION_LABEL[active.pendingAction.name] ?? active.pendingAction.name}. Allow it?
            </p>
            <pre className="overflow-x-auto rounded bg-muted p-2 text-xs">
              {JSON.stringify(active.pendingAction.arguments, null, 2)}
            </pre>
            <div className="flex gap-2">
              <Button size="sm" disabled={busy} onClick={() => act(() => decideAgentTask(active.id, true), "Could not approve.")}>
                <Check className="mr-1.5 h-4 w-4" /> Approve
              </Button>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => decideAgentTask(active.id, false), "Could not decline.")}>
                <X className="mr-1.5 h-4 w-4" /> Decline
              </Button>
            </div>
          </div>
        ) : null}

        {detail.files.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {detail.files.map((f) => (
              <Button key={f.id} variant="outline" size="sm" asChild>
                <a href={agentFileUrl(f.id)} download>
                  <Download className="mr-1.5 h-4 w-4" /> {f.filename} ({f.rows} rows)
                </a>
              </Button>
            ))}
          </div>
        ) : null}

        <div ref={bottomRef} />
      </div>

      {error ? <p role="alert" className="px-4 pb-2 text-sm text-destructive">{error}</p> : null}

      <div className="border-t p-3">
        {latest ? (
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              {polling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {STATUS_LABEL[latest.status] ?? latest.status}
              {latest.toolCalls ? ` · ${latest.toolCalls} tool call${latest.toolCalls === 1 ? "" : "s"}` : ""}
              {latest.tokensUsed ? ` · ${latest.tokensUsed.toLocaleString()} tokens` : ""}
            </span>
            {active ? (
              <Button variant="outline" size="sm" disabled={busy} onClick={() => act(() => cancelAgentTask(active.id), "Could not stop.")}>
                <Square className="mr-1.5 h-3.5 w-3.5" /> Stop
              </Button>
            ) : null}
          </div>
        ) : null}
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={2}
            placeholder={active ? "The agent is working…" : "Describe the task. Shift+Enter for a new line."}
            disabled={busy || !!active || (status !== null && !status.configured)}
            className="min-h-[44px] resize-none"
          />
          <Button type="submit" size="icon" aria-label="Send" disabled={busy || !!active || !draft.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </div>
    </>
  );
}

function ToolRow({
  name,
  args,
  result,
  awaiting = false,
  stopped = false,
}: {
  name: string;
  args: string | Record<string, unknown>;
  result?: AgentMessage;
  awaiting?: boolean;
  stopped?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const state = result?.status ?? (awaiting ? "awaiting" : stopped ? "not run" : "running");
  const tone =
    state === "ok" || state === "cached"
      ? "text-primary"
      : state === "running" || state === "awaiting"
        ? "text-muted-foreground"
        : "text-destructive";
  const argText = typeof args === "string" ? args : JSON.stringify(args);

  return (
    <div className="rounded-md border bg-muted/30 text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left"
      >
        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-90" : ""}`} />
        <Wrench className="h-3.5 w-3.5" />
        <span className="font-medium">{TOOL_LABEL[name] ?? name}</span>
        <span className={`ml-auto ${tone}`}>
          {state === "running"
            ? "running…"
            : state === "cached"
              ? "reused"
              : state === "awaiting"
                ? "awaiting approval"
                : state}
        </span>
      </button>
      {open ? (
        <div className="space-y-2 border-t px-2.5 py-2">
          <pre className="overflow-x-auto whitespace-pre-wrap break-all text-muted-foreground">{argText}</pre>
          {result ? (
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all">{result.content.slice(0, 4000)}</pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function InstructionsEditor({
  chatId,
  initial,
  onSaved,
}: {
  chatId: string;
  initial: string;
  onSaved: () => void;
}) {
  const [value, setValue] = React.useState(initial);
  const [saving, setSaving] = React.useState(false);
  return (
    <div className="space-y-2 border-b bg-muted/20 p-4">
      <Label htmlFor={`instructions-${chatId}`}>Instructions for this chat</Label>
      <Textarea
        id={`instructions-${chatId}`}
        rows={4}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="e.g. Always answer in a table. Our target domain is all-bettors.com. Keep reports under 200 rows."
      />
      <p className="text-xs text-muted-foreground">
        Applied to every message in this chat: goals, output format, constraints.
        They cannot override the platform&apos;s safety rules.
      </p>
      <Button
        size="sm"
        disabled={saving}
        onClick={async () => {
          setSaving(true);
          try {
            await updateAgentChat(chatId, { instructions: value });
            onSaved();
          } finally {
            setSaving(false);
          }
        }}
      >
        Save instructions
      </Button>
    </div>
  );
}
