"use client";

import type {
  ActivityEntry,
  Conversation,
  Status,
  TuningConfig,
} from "./types";

/* ============================================================
   api.ts — the real backend client.

   Replaces mockApi for everything the Inbox, Triage, Insights and
   Activity screens read. The backend serialises camelCase, so the
   Zod types in types.ts describe these responses unchanged.
   ============================================================ */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      // The session is an httpOnly cookie, so it has to be sent explicitly:
      // fetch omits credentials on cross-origin requests, which is exactly the
      // development setup (page on :3000, API on :8000).
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (cause) {
    // A dead backend is the common case in development, and "Failed to fetch"
    // does not tell anyone which process is missing.
    throw new ApiError(
      `Cannot reach the Signal API at ${API_BASE}. Is the backend running?`,
      0,
    );
  }

  if (response.status === 401 && typeof window !== "undefined") {
    // The session is gone or expired. Bounce to the sign-in screen rather than
    // letting every panel render its own "unauthorised" error. `next` brings
    // the user back where they were once they sign in.
    const here = window.location.pathname + window.location.search;
    if (!here.startsWith("/login")) {
      window.location.href = `/login?next=${encodeURIComponent(here)}`;
    }
  }

  if (!response.ok) {
    // Spec §32: errors arrive as {success:false, error:{code,message}}.
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.error?.message) message = body.error.message;
    } catch {
      // Non-JSON error body; the status line is all we have.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/* ---------------- conversations ---------------- */

interface Page<T> {
  items: T[];
  total: number;
  page: number;
  perPage: number;
}

const PAGE_SIZE = 200;

/**
 * Every conversation, following pagination to the end.
 *
 * Insights and the KPI strip fold over the whole array client-side, so handing
 * them page 1 would silently turn every stat into "stats for the first 200
 * rows" (docs/frontend-api-mapping.md finding b). The server-side aggregates at
 * /api/insights/* are the answer once this stops being a local-scale app; until
 * then, fetching every page keeps those screens correct without rewriting them.
 */
export async function listConversations(): Promise<Conversation[]> {
  const first = await request<Page<Conversation>>(
    `/conversations?page=1&perPage=${PAGE_SIZE}`,
  );
  const items = [...first.items];
  const pages = Math.ceil(first.total / PAGE_SIZE);

  for (let page = 2; page <= pages; page++) {
    const next = await request<Page<Conversation>>(
      `/conversations?page=${page}&perPage=${PAGE_SIZE}`,
    );
    items.push(...next.items);
  }
  return items;
}

/**
 * The five §18 verbs, plus the two the undo path needs.
 *
 * "sent" is absent on purpose: it is not something you may set, it is what
 * sending produces. Only POST /replies/{id}/send can put a row there.
 */
export const STATUS_TO_ACTION: Partial<Record<Status, string>> = {
  approved: "approve",
  rejected: "reject",
  snoozed: "snooze",
  manually_posted: "mark-posted",
  blocked: "block",
  new: "reset",
  awaiting: "mark-awaiting",
};

export function setStatus(id: string, status: Status): Promise<Conversation> {
  const action = STATUS_TO_ACTION[status];
  if (!action) {
    return Promise.reject(
      new ApiError(
        `"${status}" cannot be set directly. Use the send endpoint instead.`,
        400,
      ),
    );
  }
  return request<Conversation>(`/conversations/${id}/${action}`, {
    method: "POST",
  });
}

export function editReply(
  id: string,
  patch: { editedReply?: string | null; selectedVariant?: number },
): Promise<Conversation> {
  return request<Conversation>(`/conversations/${id}/edit`, {
    method: "POST",
    body: JSON.stringify(patch),
  });
}

/**
 * Rewrite the summary and the three reply drafts with the AI model.
 * Replaces any manual edit. Can take a minute on a CPU-only server.
 */
export function aiRedraft(id: string): Promise<Conversation> {
  return request<Conversation>(`/conversations/${id}/ai-draft`, { method: "POST" });
}

/* ---------------- tuning ---------------- */

export function getConfig(): Promise<TuningConfig> {
  return request<TuningConfig>("/tuning");
}

export function saveConfig(config: TuningConfig): Promise<TuningConfig> {
  return request<TuningConfig>("/tuning", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

/* ---------------- activity ---------------- */

export async function listActivity(): Promise<ActivityEntry[]> {
  const page = await request<Page<ActivityEntry>>("/activity?page=1&perPage=500");
  return page.items;
}

/* ---------------- scans ---------------- */

export interface ScanResult {
  scanId: string;
  status: string;
  discovered: number;
  examined: number;
  error?: string | null;
  platforms: {
    platform: string;
    examined: number;
    discovered: number;
    error?: string | null;
  }[];
}

export function startScan(): Promise<ScanResult> {
  return request<ScanResult>("/scans/run", { method: "POST" });
}

export function getScan(id: string): Promise<ScanResult> {
  return request<ScanResult>(`/scans/${id}`);
}

/** Start a scan and wait for it to finish, so the caller can report what it found. */
export async function runScan(timeoutMs = 60_000): Promise<ScanResult> {
  const started = await startScan();
  const deadline = Date.now() + timeoutMs;

  let latest = started;
  while (latest.status === "running" && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    latest = await getScan(started.scanId);
  }
  return latest;
}

/* ---------------- health ---------------- */

export interface PlatformStatus {
  platform: string;
  status: "connected" | "not_connected" | "error" | "not_implemented";
  lastChecked: string | null;
  error: string | null;
  detail: string | null;
}

export async function getPlatformStatus(): Promise<PlatformStatus[]> {
  const body = await request<{ platforms: PlatformStatus[] }>("/health/platforms");
  return body.platforms;
}

export interface DiscordServer {
  id: string;
  name: string;
  channels: { id: string; name: string; readable: boolean }[];
  error: string | null;
}

export interface DiscordOverview {
  connected: boolean;
  /** Link a server admin opens to add the bot to their server. */
  inviteUrl: string | null;
  servers: DiscordServer[];
  error: string | null;
}

export function getDiscordOverview(): Promise<DiscordOverview> {
  return request<DiscordOverview>("/platforms/discord");
}

export type SourcePlatform = "reddit" | "youtube" | "telegram_account";

export interface SourceSettings {
  queries: string[];
  subreddits?: string[];
  channel_ids?: string[];
  chats?: string[];
}

export interface SourceInfo {
  configured: boolean;
  settings: SourceSettings;
}

export function getSources(): Promise<Record<SourcePlatform, SourceInfo>> {
  return request<Record<SourcePlatform, SourceInfo>>("/platforms/sources");
}

export function updateSources(platform: SourcePlatform, settings: SourceSettings): Promise<SourceInfo> {
  return request<SourceInfo>(`/platforms/sources/${platform}`, {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

export function getSourceStatus(
  platform: SourcePlatform,
): Promise<{ status: string; detail: string | null; error: string | null }> {
  return request(`/platforms/status/${platform}`);
}

/* ---------------- AI agent chat ---------------- */

export type AgentTaskStatus =
  | "pending"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export interface AgentChat {
  id: string;
  title: string;
  instructions: string;
  createdAt: string;
  updatedAt: string;
}

export interface AgentToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string | Record<string, unknown> };
}

export interface AgentMessage {
  id: string;
  seq: number;
  role: "user" | "assistant" | "tool";
  content: string;
  toolCalls: AgentToolCall[] | null;
  toolCallId: string | null;
  name: string | null;
  status: string | null;
  taskId: string | null;
  createdAt: string;
}

export interface AgentTask {
  id: string;
  status: AgentTaskStatus;
  iterations: number;
  toolCalls: number;
  tokensUsed: number;
  error: string | null;
  pendingAction: { name: string; arguments: Record<string, unknown> } | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface AgentFile {
  id: string;
  taskId: string;
  filename: string;
  rows: number;
  createdAt: string;
}

export interface AgentChatDetail {
  chat: AgentChat;
  messages: AgentMessage[];
  tasks: AgentTask[];
  files: AgentFile[];
  configured: boolean;
}

export interface AgentStatus {
  configured: boolean;
  provider: "ollama" | "groq";
  model: string;
  tools: { name: string; description: string; requiresApproval: boolean }[];
}

export function getAgentStatus(): Promise<AgentStatus> {
  return request<AgentStatus>("/assistant/status");
}

export function listAgentChats(): Promise<AgentChat[]> {
  return request<AgentChat[]>("/assistant/chats");
}

export function createAgentChat(body: { title?: string; instructions?: string } = {}): Promise<AgentChat> {
  return request<AgentChat>("/assistant/chats", { method: "POST", body: JSON.stringify(body) });
}

export function getAgentChat(id: string): Promise<AgentChatDetail> {
  return request<AgentChatDetail>(`/assistant/chats/${id}`);
}

export function updateAgentChat(
  id: string,
  patch: { title?: string; instructions?: string },
): Promise<AgentChat> {
  return request<AgentChat>(`/assistant/chats/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteAgentChat(id: string): Promise<void> {
  return request<void>(`/assistant/chats/${id}`, { method: "DELETE" });
}

export function clearAgentChat(id: string): Promise<void> {
  return request<void>(`/assistant/chats/${id}/clear`, { method: "POST" });
}

/** Starts a task; the agent runs in the background. Poll getAgentChat. */
export function sendAgentMessage(chatId: string, content: string): Promise<AgentTask> {
  return request<AgentTask>(`/assistant/chats/${chatId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function cancelAgentTask(taskId: string): Promise<AgentTask> {
  return request<AgentTask>(`/assistant/tasks/${taskId}/cancel`, { method: "POST" });
}

export function decideAgentTask(taskId: string, approve: boolean): Promise<AgentTask> {
  return request<AgentTask>(`/assistant/tasks/${taskId}/decision`, {
    method: "POST",
    body: JSON.stringify({ approve }),
  });
}

export function agentFileUrl(fileId: string): string {
  return `${API_BASE}/assistant/files/${fileId}`;
}

/* ---------------- playground ---------------- */

/**
 * Shape of POST /api/playground/analyze.
 *
 * Identical to the old mockApi AnalyseResult, so the Playground components are
 * unchanged — the difference is that the Python engine produces it, the same
 * one ingestion uses (spec §22). There is no separate simplified path.
 */
export interface AnalyseResult {
  score: number;
  intent: "high" | "medium" | "low" | "not_relevant";
  confidence: "low" | "medium" | "high";
  matchedKeywords: string[];
  contributions: { ruleId: string; label: string; points: number }[];
  riskFlags: string[];
  language: string;
  reply: string;
  replyVariants: { tone: string; text: string }[];
  summary: string;
}

export function analyseMessage(
  message: string,
  meta: {
    platform?: string;
    country?: string;
    community?: string;
    url?: string;
  } = {},
): Promise<AnalyseResult> {
  return request<AnalyseResult>("/playground/analyze", {
    method: "POST",
    body: JSON.stringify({ message, ...meta }),
  });
}

/* ---------------- outbound replies ---------------- */

export interface ReplyPreview {
  text: string;
  canSend: boolean;
  problems: string[];
}

export interface SendResult {
  externalMessageId: string;
  text: string;
  conversation: Conversation;
}

/**
 * What would be posted, and every reason it would be refused.
 *
 * The UI calls this to disable the send control up front, rather than letting
 * someone click and only then learn the reply is missing its disclosure.
 */
export function previewReply(id: string): Promise<ReplyPreview> {
  return request<ReplyPreview>(`/replies/${id}/preview`);
}

/**
 * Post the approved reply to the platform. This is visible to real people.
 *
 * The server re-runs the full safety check and refuses with 422 regardless of
 * what the client believed, so this cannot be talked into sending.
 */
export function sendReply(id: string): Promise<SendResult> {
  return request<SendResult>(`/replies/${id}/send`, { method: "POST" });
}

export interface ReplyUsage {
  perPlatformPerHour: number;
  dailyApprovedCeiling: number;
  sentLastHour: Record<string, number>;
  sentToday: number;
}

export function getReplyUsage(): Promise<ReplyUsage> {
  return request<ReplyUsage>("/replies/usage");
}

/* ---------------- agents (brief §2, §3) ---------------- */

export type AgentType = "engagement" | "content" | "backlink_audit";

export interface Agent {
  id: string;
  name: string;
  agentType: AgentType;
  description: string;
  enabled: boolean;
  rules: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface AgentOutput {
  id: string;
  agentId: string;
  locationKey: string;
  city: string;
  state: string;
  zipcode: string;
  category: string;
  title: string;
  body: string;
  contactEmail: string;
  publishedUrl: string | null;
  status: "generated" | "published";
  createdAt: string;
  publishedAt: string | null;
}

export function listAgents(filter?: {
  type?: AgentType;
  enabled?: boolean;
}): Promise<Agent[]> {
  const params = new URLSearchParams();
  if (filter?.type) params.set("type", filter.type);
  if (filter?.enabled !== undefined) params.set("enabled", String(filter.enabled));
  const query = params.toString();
  return request<Agent[]>(`/agents${query ? `?${query}` : ""}`);
}

/** The agent types that exist, each with a JSON Schema for its rules. */
export function listAgentTypes(): Promise<{
  types: {
    type: AgentType;
    label: string;
    description: string;
    ruleSchema: Record<string, unknown>;
  }[];
}> {
  return request("/agents/types");
}

export function createAgent(body: {
  name: string;
  agentType: AgentType;
  description?: string;
  enabled?: boolean;
  rules?: Record<string, unknown>;
}): Promise<Agent> {
  return request<Agent>("/agents", { method: "POST", body: JSON.stringify(body) });
}

export function updateAgent(
  id: string,
  patch: {
    name?: string;
    description?: string;
    enabled?: boolean;
    rules?: Record<string, unknown>;
  },
): Promise<Agent> {
  return request<Agent>(`/agents/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteAgent(id: string): Promise<void> {
  return request<void>(`/agents/${id}`, { method: "DELETE" });
}

/** Cities this agent has not generated an ad for yet (brief §2.2). */
export function remainingCities(id: string): Promise<{
  remaining: number;
  cities: { key: string; city: string; state: string; zipcode: string }[];
}> {
  return request(`/agents/${id}/cities`);
}

/**
 * Generate the next ad for a content agent.
 *
 * Content only — nothing is submitted to any site. The operator posts it and
 * records the live URL with markOutputPublished.
 */
export function generateOutput(id: string): Promise<AgentOutput> {
  return request<AgentOutput>(`/agents/${id}/generate`, { method: "POST" });
}

export async function listOutputs(
  id: string,
  status?: "generated" | "published",
): Promise<AgentOutput[]> {
  const query = status ? `&status=${status}` : "";
  const page = await request<Page<AgentOutput>>(
    `/agents/${id}/outputs?page=1&perPage=200${query}`,
  );
  return page.items;
}

/* ---------------- backlink audit agents ---------------- */

export type BacklinkResult = "dofollow" | "nofollow" | "not_found" | "error";

export interface BacklinkCheck {
  row: number;
  pageUrl: string;
  result: BacklinkResult;
  rel: string;
  linkHref: string;
  anchorText: string;
  httpStatus: number | null;
  detail: string;
  checkedAt: string;
}

export interface BacklinkAudit {
  status: "idle" | "running" | "completed" | "failed";
  total: number;
  done: number;
  error: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  counts: Partial<Record<BacklinkResult, number>>;
  items: BacklinkCheck[];
}

/** Start checking every URL in the agent's sheet. Poll getAudit for progress. */
export function startAudit(id: string): Promise<BacklinkAudit> {
  return request<BacklinkAudit>(`/agents/${id}/audit`, { method: "POST" });
}

export function getAudit(id: string): Promise<BacklinkAudit> {
  return request<BacklinkAudit>(`/agents/${id}/audit`);
}

/** Direct link for the CSV download; the session cookie goes with it. */
export function auditCsvUrl(id: string): string {
  return `${API_BASE}/agents/${id}/audit.csv`;
}

export function markOutputPublished(
  outputId: string,
  publishedUrl: string,
): Promise<AgentOutput> {
  return request<AgentOutput>(`/agents/outputs/${outputId}/publish`, {
    method: "POST",
    body: JSON.stringify({ publishedUrl }),
  });
}

/* ---------------- engagement + refinement (brief §1, §8) ---------------- */

export interface Engagement {
  windowHours: number;
  repliesSent: number;
  clicks: number;
  uniqueClicks: number;
  botHits: number;
  conversationsClicked: number;
  clickThroughRate: number;
  clicksByPlatform: Record<string, number>;
  repliesByPlatform: Record<string, number>;
}

export function getEngagement(range: "24h" | "7d" | "30d" = "7d"): Promise<Engagement> {
  return request<Engagement>(`/insights/engagement?range=${range}`);
}

export interface RefinementIndex {
  agentId: string | null;
  agentName: string | null;
  sampleSize: number;
  /** False when there is too little data for the score to mean anything. */
  confident: boolean;
  score: number;
  approvalRate: number;
  clickThroughRate: number;
  precision: number;
  notes: string[];
}

export function getRefinementIndex(days = 30): Promise<RefinementIndex> {
  return request<RefinementIndex>(`/insights/refinement?days=${days}`);
}

export function getAgentRefinement(id: string, days = 30): Promise<RefinementIndex> {
  return request<RefinementIndex>(`/agents/${id}/refinement?days=${days}`);
}

/* ---------------- presets (brief §5) ---------------- */

export interface Preset {
  id: string;
  name: string;
  createdAt: string;
  config: TuningConfig;
}

export function listPresets(): Promise<Preset[]> {
  return request<Preset[]>("/tuning/presets");
}

/** Omitting `config` snapshots whatever is active right now. */
export function createPreset(name: string, config?: TuningConfig): Promise<Preset> {
  return request<Preset>("/tuning/presets", {
    method: "POST",
    body: JSON.stringify(config ? { name, config } : { name }),
  });
}

export function applyPreset(id: string): Promise<TuningConfig> {
  return request<TuningConfig>(`/tuning/presets/${id}/apply`, { method: "POST" });
}

export function deletePreset(id: string): Promise<void> {
  return request<void>(`/tuning/presets/${id}`, { method: "DELETE" });
}

/* ---------------- general search (brief §8) ---------------- */

export interface SearchHit {
  kind: "conversation" | "agent" | "content" | "activity";
  id: string;
  title: string;
  subtitle: string;
  snippet: string;
}

export function searchAll(q: string): Promise<{
  query: string;
  total: number;
  hits: SearchHit[];
}> {
  return request(`/search?q=${encodeURIComponent(q)}`);
}

/* ============================================================
   Authentication (spec §38)

   The token itself is never visible here: the backend sets an httpOnly
   cookie, so there is nothing for this module to store or attach.
   ============================================================ */

export type CurrentUser = {
  id: string;
  email: string;
  name: string;
  role: string;
};

export function login(email: string, password: string): Promise<CurrentUser> {
  return request<CurrentUser>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  await request<void>("/auth/logout", { method: "POST" });
}

/** The signed-in user, or null when there is no valid session. */
export async function me(): Promise<CurrentUser | null> {
  try {
    return await request<CurrentUser>("/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/* ============================================================
   User administration (spec §38) — admin only on the server.
   ============================================================ */

export type PlatformUser = {
  id: string;
  email: string;
  name: string;
  role: string;
  isActive: boolean;
  createdAt: string | null;
  lastLoginAt: string | null;
};

export type RoleInfo = { id: string; label: string; description: string };

export function listUsers(): Promise<PlatformUser[]> {
  return request<PlatformUser[]>("/users");
}

export function listRoles(): Promise<{ roles: RoleInfo[] }> {
  return request<{ roles: RoleInfo[] }>("/users/roles");
}

export function createUser(body: {
  email: string;
  name?: string;
  password: string;
  role: string;
}): Promise<PlatformUser> {
  return request<PlatformUser>("/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateUser(
  id: string,
  body: Partial<{ name: string; role: string; isActive: boolean; password: string }>,
): Promise<PlatformUser> {
  return request<PlatformUser>(`/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
