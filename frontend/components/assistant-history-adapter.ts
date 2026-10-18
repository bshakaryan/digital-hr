import type { ApiClient, AssistantAnswer, Knowledge } from "@/lib/api";

// Provisional contract from docs/AI_JANA_CHAT_AUDIT.md. No production component
// creates this adapter until the Integration Lead approves and implements it.
export type ChatScope = { kind: "general" } | { kind: "course"; courseId: number };

export interface ConversationSummary {
  id: string;
  scope: "general" | "course";
  course_id: number | null;
  title: string;
  updated_at: string;
}

export interface ConversationListPage {
  items: ConversationSummary[];
  next_cursor: string | null;
}

export interface StoredChatMessage {
  id: string;
  turn_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  sources?: Knowledge[];
  sources_unavailable?: boolean;
  escalate_to_hr?: boolean;
  mode?: AssistantAnswer["mode"];
}

export interface ConversationMessagePage {
  id: string;
  scope: "general" | "course";
  course_id: number | null;
  messages: StoredChatMessage[]; // oldest to newest; pages contain complete turns
  next_before_id: string | null;
}

export interface SentChatAnswer extends AssistantAnswer {
  conversation_id: string;
  turn_id: string;
}

export interface ChatHistoryAdapter {
  list(scope: ChatScope, cursor?: string): Promise<ConversationListPage>;
  open(scope: ChatScope, id: string, beforeId?: string): Promise<ConversationMessagePage>;
  send(scope: ChatScope, question: string, clientTurnId: string, conversationId?: string): Promise<SentChatAnswer>;
}

function scopeQuery(scope: ChatScope): string {
  const query = new URLSearchParams({ scope: scope.kind });
  if (scope.kind === "course") query.set("course_id", String(scope.courseId));
  return query.toString();
}

/** Construct only after the server contract is approved; never used by default. */
export function createProvisionalChatHistoryAdapter(api: ApiClient): ChatHistoryAdapter {
  return {
    list(scope, cursor) {
      const query = new URLSearchParams(scopeQuery(scope));
      if (cursor) query.set("cursor", cursor);
      return api.call<ConversationListPage>(`/assistant/conversations?${query}`);
    },
    open(scope, id, beforeId) {
      const query = new URLSearchParams(scopeQuery(scope));
      if (beforeId) query.set("before_id", beforeId);
      return api.call<ConversationMessagePage>(`/assistant/conversations/${encodeURIComponent(id)}?${query}`);
    },
    send(scope, question, clientTurnId, conversationId) {
      const path = scope.kind === "course" ? `/courses/${scope.courseId}/ask` : "/assistant/query";
      return api.post<SentChatAnswer>(path, {
        question, client_turn_id: clientTurnId,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      });
    },
  };
}

export function sameScope(scope: ChatScope, item: { scope: "general" | "course"; course_id: number | null }): boolean {
  return item.scope === scope.kind && (scope.kind === "general" ? item.course_id === null : item.course_id === scope.courseId);
}
