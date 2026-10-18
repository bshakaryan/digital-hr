import { ApiError, type ApiClient, type AssistantAnswer, type AssistantConversation,
  type AssistantConversationDetail, type AssistantConversationPage, type Knowledge } from "@/lib/api";

export type ChatScope = { kind: "general" } | { kind: "course"; courseId: number };
export type ConversationSummary = AssistantConversation;

export interface ConversationListPage {
  items: ConversationSummary[];
  nextPage: number | null;
}

export interface StoredChatMessage {
  id: string;
  turn_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  sources: Knowledge[];
  escalate_to_hr: boolean | null;
  mode: AssistantAnswer["mode"] | null;
}

export interface ConversationMessagePage {
  id: number;
  course_id: number | null;
  messages: StoredChatMessage[];
  previousPage: number | null;
}

export interface SentChatAnswer extends AssistantAnswer {
  conversation_id: number;
  turn_id: number;
  client_turn_id: string;
}

export interface ChatHistoryAdapter {
  list(scope: ChatScope, page?: number): Promise<ConversationListPage>;
  open(scope: ChatScope, id: number, page?: number): Promise<ConversationMessagePage>;
  send(scope: ChatScope, question: string, clientTurnId: string, conversationId?: number): Promise<SentChatAnswer>;
}

export class HistoryUnavailableError extends Error {
  constructor() { super("История диалогов недоступна."); this.name = "HistoryUnavailableError"; }
}

export function sameScope(scope: ChatScope, item: { course_id: number | null }): boolean {
  return scope.kind === "general" ? item.course_id === null : item.course_id === scope.courseId;
}

const listPageSize = 20;
const messagePageSize = 30;

function messagesFromDetail(detail: AssistantConversationDetail): ConversationMessagePage {
  return {
    id: detail.id,
    course_id: detail.course_id,
    previousPage: detail.page > 1 ? detail.page - 1 : null,
    messages: detail.messages.map((message) => ({
      id: `${message.id}:${message.role}`,
      turn_id: message.id,
      role: message.role,
      content: message.text,
      created_at: message.created_at,
      sources: message.sources || [],
      escalate_to_hr: message.escalate_to_hr,
      mode: message.mode,
    })),
  };
}

/** Uses the implemented PostgreSQL history API. List 404/405 means an older server: use stateless chat. */
export function createAssistantHistoryAdapter(api: ApiClient): ChatHistoryAdapter {
  const detail = (id: number, page: number) => api.call<AssistantConversationDetail>(
    `/assistant/conversations/${id}?page=${page}&page_size=${messagePageSize}`);
  return {
    async list(scope, page = 1) {
      let result: AssistantConversationPage;
      try {
        result = await api.call<AssistantConversationPage>(
          `/assistant/conversations?page=${page}&page_size=${listPageSize}`);
      } catch (cause) {
        if (cause instanceof ApiError && (cause.status === 404 || cause.status === 405)) throw new HistoryUnavailableError();
        throw cause;
      }
      return {
        items: result.items.filter((item) => sameScope(scope, item)),
        nextPage: result.page * result.page_size < result.total ? result.page + 1 : null,
      };
    },
    async open(scope, id, page) {
      // The server pages turns from oldest to newest. Open the last page for a normal chat view.
      const first = page === undefined ? await detail(id, 1) : null;
      if (first && !sameScope(scope, first)) throw new Error("Диалог не относится к этому разделу.");
      const lastPage = first ? Math.max(1, Math.ceil(first.total_turns / first.page_size)) : page!;
      const result = first && lastPage === 1 ? first : await detail(id, lastPage);
      if (!sameScope(scope, result) || result.id !== id) throw new Error("Диалог не относится к этому разделу.");
      return messagesFromDetail(result);
    },
    send(scope, question, clientTurnId, conversationId) {
      const path = scope.kind === "course" ? `/courses/${scope.courseId}/ask` : "/assistant/query";
      return api.post<SentChatAnswer>(path, {
        question,
        client_turn_id: clientTurnId,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      });
    },
  };
}
