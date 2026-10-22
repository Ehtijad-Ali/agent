"use client";

import * as React from "react";
import { Loader2, RefreshCw, UserPlus } from "lucide-react";

import {
  type DiscordOverview,
  type DiscoveryPlatform,
  type DiscoverySource,
  type PlatformStatus,
  ApiError,
  getDiscordOverview,
  getPlatformStatus,
  getSourceStatus,
  getSources,
  updateSources,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/**
 * Platforms — where the bots can read, and what discovery searches for.
 *
 * Discord and Telegram bots only see communities they were added to, so this
 * screen hands out the invite and shows which channels are actually readable.
 * Reddit, YouTube and the Telegram account search public content by keyword;
 * their search terms are edited here, their credentials live on the server.
 */
export function PlatformsView() {
  const [discord, setDiscord] = React.useState<DiscordOverview | null>(null);
  const [statuses, setStatuses] = React.useState<PlatformStatus[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      const [d, s] = await Promise.all([getDiscordOverview(), getPlatformStatus()]);
      setDiscord(d);
      setStatuses(s);
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load platforms.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const telegram = statuses.find((p) => p.platform === "telegram");
  const botHandle = telegram?.detail?.match(/@\w+/)?.[0];

  return (
    <div className="flex h-full flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Platforms</h1>
          <p className="text-sm text-muted-foreground">
            Bots only read communities they have been added to. Add them here,
            then check which channels they can see.
          </p>
        </div>
        <Button variant="outline" onClick={refresh} disabled={loading}>
          {loading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          Refresh
        </Button>
      </header>

      {error ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}

      <section className="space-y-4 rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-medium">Discord</h2>
            <p className="text-sm text-muted-foreground">
              An admin of each server opens the link and picks the server. The
              bot then reads every channel its role can view.
            </p>
          </div>
          {discord?.inviteUrl ? (
            <Button asChild>
              <a href={discord.inviteUrl} target="_blank" rel="noreferrer">
                <UserPlus className="mr-2 h-4 w-4" /> Add bot to a server
              </a>
            </Button>
          ) : null}
        </div>

        {discord?.inviteUrl ? (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">
              Not an admin of the server? Send this link to someone who is:
            </p>
            <code className="block break-all rounded-md bg-muted p-2 text-xs">
              {discord.inviteUrl}
            </code>
          </div>
        ) : null}

        {discord?.error ? <p className="text-sm text-destructive">{discord.error}</p> : null}

        {discord?.connected ? (
          discord.servers.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              The bot is not in any server yet. Use the button above to add it.
            </p>
          ) : (
            <div className="space-y-3">
              {discord.servers.map((server) => {
                const readable = server.channels.filter((c) => c.readable).length;
                return (
                  <div key={server.id} className="rounded-md border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">{server.name}</span>
                      <span className="text-xs text-muted-foreground">
                        {readable} of {server.channels.length} text channel
                        {server.channels.length === 1 ? "" : "s"} readable
                      </span>
                    </div>
                    {server.error ? (
                      <p className="mt-1 text-sm text-destructive">{server.error}</p>
                    ) : (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {server.channels.map((channel) => (
                          <span
                            key={channel.id}
                            title={
                              channel.readable
                                ? "Readable"
                                : "Blocked: give the bot's role View Channel and Read Message History here"
                            }
                            className={`rounded px-2 py-0.5 text-xs ${
                              channel.readable
                                ? "bg-primary/10 text-primary"
                                : "bg-destructive/10 text-destructive line-through"
                            }`}
                          >
                            #{channel.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
              <p className="text-xs text-muted-foreground">
                Crossed-out channels are blocked: give the bot&apos;s role View
                Channel and Read Message History there.
              </p>
            </div>
          )
        ) : null}
      </section>

      <section className="space-y-2 rounded-lg border bg-card p-4">
        <h2 className="font-medium">Telegram</h2>
        <p className="text-sm text-muted-foreground">{telegram?.detail ?? "Status unavailable."}</p>
        {telegram?.error ? <p className="text-sm text-destructive">{telegram.error}</p> : null}
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          <li>Open the group in Telegram → group name → Add members.</li>
          <li>Search for {botHandle ?? "the bot"} and add it. You need to be a group admin.</li>
          <li>Post a message in the group, then press Run scan. It appears in the Inbox.</li>
        </ol>
        <p className="text-xs text-muted-foreground">
          Telegram bots cannot search or join public groups on their own. To
          read public groups by keyword, use the Telegram account below.
        </p>
      </section>

      <h2 className="pt-2 text-lg font-semibold tracking-tight">Discovery: find people anywhere</h2>
      <p className="-mt-2 text-sm text-muted-foreground">
        These search public posts and comments by keyword, so they find people
        who are not in your communities. They only read; you reply on the
        platform yourself.
      </p>

      {SOURCES.map((source) => (
        <DiscoverySourceCard key={source.platform} source={source} />
      ))}
    </div>
  );
}

type SourceDef = {
  platform: DiscoveryPlatform;
  title: string;
  description: string;
  setup: string[];
  fields: { key: string; label: string; hint: string }[];
};

const SOURCES: SourceDef[] = [
  {
    platform: "reddit",
    title: "Reddit",
    description:
      "Searches all of Reddit for new posts matching your terms, and reads new posts and comments in the subreddits you list.",
    setup: [
      "Sign in to Reddit and open reddit.com/prefs/apps.",
      "Click “create another app”, choose type “script”, any name, and http://localhost as the redirect URL.",
      "Send the app id (under the app name) and the secret to your developer to add on the server.",
    ],
    fields: [
      { key: "queries", label: "Search terms", hint: "One per line, e.g. free prediction game" },
      { key: "subreddits", label: "Subreddits to watch (optional)", hint: "One per line, e.g. soccer or r/nba" },
    ],
  },
  {
    platform: "youtube",
    title: "YouTube comments",
    description:
      "Finds recent videos matching your terms and reads their comments, where many people discuss picks and prediction apps.",
    setup: [
      "Open console.cloud.google.com and create a project.",
      "Enable “YouTube Data API v3” for it, then create an API key under Credentials.",
      "Send the key to your developer to add on the server.",
    ],
    fields: [
      {
        key: "queries",
        label: "Search terms",
        hint: "One per line. Each costs 100 of the 10,000 daily quota units per scan.",
      },
      { key: "channel_ids", label: "Channels to watch (optional)", hint: "One channel id per line, e.g. UC..." },
    ],
  },
  {
    platform: "telegram_account",
    title: "Telegram account (public groups)",
    description:
      "A dedicated Telegram account searches public groups and channels by keyword and reads their messages. It never joins, posts, or messages anyone.",
    setup: [
      "Get a spare phone number and create a Telegram account with it.",
      "On my.telegram.org → API development tools, create an app and note the API id and hash.",
      "Your developer signs the account in once on the server; you will be asked for the login code Telegram sends.",
    ],
    fields: [
      { key: "queries", label: "Search terms", hint: "One per line, e.g. football predictions" },
      {
        key: "chats",
        label: "Public groups/channels to watch (optional)",
        hint: "One per line, e.g. @groupname or https://t.me/groupname",
      },
    ],
  },
];

function DiscoverySourceCard({ source }: { source: SourceDef }) {
  const [data, setData] = React.useState<DiscoverySource | null>(null);
  const [status, setStatus] = React.useState<{
    status: PlatformStatus["status"];
    detail: string | null;
    error: string | null;
  } | null>(null);
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const all = await getSources();
        if (!alive) return;
        const mine = all[source.platform];
        setData(mine);
        setValues(
          Object.fromEntries(
            source.fields.map((f) => [f.key, (mine.settings[f.key] ?? []).join("\n")]),
          ),
        );
        if (mine.configured) setStatus(await getSourceStatus(source.platform));
      } catch (cause) {
        if (alive) setMessage(cause instanceof ApiError ? cause.message : "Could not load.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [source]);

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      const settings = Object.fromEntries(
        source.fields.map((f) => [
          f.key,
          (values[f.key] ?? "")
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean),
        ]),
      );
      setData(await updateSources(source.platform, settings));
      setMessage("Saved. The next scan uses these.");
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  const connected = status?.status === "connected";

  return (
    <section className="space-y-3 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="max-w-2xl">
          <h3 className="font-medium">{source.title}</h3>
          <p className="text-sm text-muted-foreground">{source.description}</p>
        </div>
        <span
          className={`rounded px-2 py-0.5 text-xs ${
            connected
              ? "bg-primary/10 text-primary"
              : status?.status === "error"
                ? "bg-destructive/10 text-destructive"
                : "bg-muted text-muted-foreground"
          }`}
        >
          {data === null ? "…" : connected ? "Connected" : status?.status === "error" ? "Error" : "Not set up"}
        </span>
      </div>

      {status?.detail ? <p className="text-sm">{status.detail}</p> : null}
      {status?.error ? <p className="text-sm text-destructive">{status.error}</p> : null}

      {data && !data.configured ? (
        <div className="rounded-md bg-muted/40 p-3 text-sm">
          <p className="mb-1 font-medium">To connect</p>
          <ol className="list-decimal space-y-0.5 pl-5">
            {source.setup.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        {source.fields.map((field) => (
          <div key={field.key} className="space-y-1">
            <Label htmlFor={`${source.platform}-${field.key}`}>{field.label}</Label>
            <Textarea
              id={`${source.platform}-${field.key}`}
              rows={4}
              value={values[field.key] ?? ""}
              onChange={(e) => setValues((cur) => ({ ...cur, [field.key]: e.target.value }))}
              disabled={saving || data === null}
            />
            <p className="text-xs text-muted-foreground">{field.hint}</p>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <Button size="sm" onClick={save} disabled={saving || data === null}>
          {saving ? "Saving…" : "Save"}
        </Button>
        {message ? <span className="text-sm text-muted-foreground">{message}</span> : null}
      </div>
    </section>
  );
}
