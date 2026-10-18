"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, type AssistantAnswer } from "@/lib/api";
import { sameScope, type ChatHistoryAdapter, type ChatScope, type ConversationSummary, type StoredChatMessage } from "./assistant-history-adapter";

export interface HistoryExchange {
  id: string;
  question: string;
  result: AssistantAnswer;
  sourcesUnavailable?: boolean;
}

export function exchangesFromMessages(messages: StoredChatMessage[]): HistoryExchange[] {
  const questions = new Map<string, string>();
  const exchanges: HistoryExchange[] = [];
  for (const message of messages) {
    if (message.role === "user") questions.set(message.turn_id, message.content);
    else {
      const question = questions.get(message.turn_id);
      if (question === undefined) continue;
      exchanges.push({
        id: message.turn_id, question,
        result: {
          answer: message.content,
          sources: message.sources || [],
          escalate_to_hr: message.escalate_to_hr ?? false,
          mode: message.mode ?? "extractive_demo",
        },
        sourcesUnavailable: message.sources_unavailable,
      });
      questions.delete(message.turn_id);
    }
  }
  return exchanges;
}

export function useAssistantHistory(adapter: ChatHistoryAdapter | undefined, scope: ChatScope) {
  const scopeKey = scope.kind === "course" ? `course:${scope.courseId}` : "general";
  const generation = useRef(0);
  const selectionGeneration = useRef(0);
  const sending = useRef(false);
  const retryTurn = useRef<{ question: string; conversationId: string | null; id: string } | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [listMoreLoading, setListMoreLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<StoredChatMessage[]>([]);
  const [nextBeforeId, setNextBeforeId] = useState<string | null>(null);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesError, setMessagesError] = useState("");
  const [olderLoading, setOlderLoading] = useState(false);
  const [olderError, setOlderError] = useState("");
  const [sendLoading, setSendLoading] = useState(false);
  const [sendError, setSendError] = useState("");

  const refreshList = useCallback(async () => {
    if (!adapter) return;
    const current = generation.current;
    setListLoading(true);
    setListError("");
    try {
      const page = await adapter.list(scope);
      if (generation.current !== current) return;
      setConversations(page.items.filter((item) => sameScope(scope, item)));
      setNextCursor(page.next_cursor);
    } catch (cause) {
      if (generation.current === current) setListError(errorMessage(cause));
    } finally {
      if (generation.current === current) setListLoading(false);
    }
  }, [adapter, scopeKey]); // scope is identified by its stable kind/course ID.

  useEffect(() => {
    generation.current += 1;
    selectionGeneration.current += 1;
    retryTurn.current = null;
    setConversations([]);
    setNextCursor(null);
    setSelectedId(null);
    setMessages([]);
    setNextBeforeId(null);
    setMessagesError("");
    setOlderError("");
    setSendError("");
    setListError("");
    setListLoading(false);
    setListMoreLoading(false);
    setMessagesLoading(false);
    setOlderLoading(false);
    setSendLoading(false);
    sending.current = false;
    if (adapter) void refreshList();
    return () => { generation.current += 1; selectionGeneration.current += 1; };
  }, [adapter, scopeKey, refreshList]);

  async function loadMoreConversations() {
    if (!adapter || !nextCursor || listMoreLoading) return;
    const current = generation.current;
    setListMoreLoading(true);
    setListError("");
    try {
      const page = await adapter.list(scope, nextCursor);
      if (generation.current !== current) return;
      setConversations((old) => {
        const ids = new Set(old.map((item) => item.id));
        return [...old, ...page.items.filter((item) => sameScope(scope, item) && !ids.has(item.id))];
      });
      setNextCursor(page.next_cursor);
    } catch (cause) {
      if (generation.current === current) setListError(errorMessage(cause));
    } finally {
      if (generation.current === current) setListMoreLoading(false);
    }
  }

  async function openConversation(id: string) {
    if (!adapter || sending.current) return;
    const current = generation.current;
    const selection = ++selectionGeneration.current;
    retryTurn.current = null;
    setSelectedId(id);
    setMessages([]);
    setNextBeforeId(null);
    setSendError("");
    setMessagesError("");
    setOlderError("");
    setMessagesLoading(true);
    try {
      const page = await adapter.open(scope, id);
      if (generation.current !== current || selectionGeneration.current !== selection) return;
      if (page.id !== id || !sameScope(scope, page)) throw new Error("Диалог не относится к этому разделу.");
      setMessages(page.messages);
      setNextBeforeId(page.next_before_id);
    } catch (cause) {
      if (generation.current === current && selectionGeneration.current === selection) setMessagesError(errorMessage(cause));
    } finally {
      if (generation.current === current && selectionGeneration.current === selection) setMessagesLoading(false);
    }
  }

  function newConversation() {
    if (sending.current) return;
    selectionGeneration.current += 1;
    retryTurn.current = null;
    setSelectedId(null);
    setMessages([]);
    setNextBeforeId(null);
    setMessagesError("");
    setOlderError("");
    setSendError("");
    setMessagesLoading(false);
  }

  async function loadOlderMessages(): Promise<boolean> {
    if (!adapter || !selectedId || !nextBeforeId || olderLoading || messagesLoading) return false;
    const current = generation.current;
    const selection = selectionGeneration.current;
    const id = selectedId;
    setOlderLoading(true);
    setOlderError("");
    try {
      const page = await adapter.open(scope, id, nextBeforeId);
      if (generation.current !== current || selectionGeneration.current !== selection) return false;
      if (page.id !== id || !sameScope(scope, page)) throw new Error("Диалог не относится к этому разделу.");
      setMessages((old) => {
        const ids = new Set(old.map((message) => message.id));
        return [...page.messages.filter((message) => !ids.has(message.id)), ...old];
      });
      setNextBeforeId(page.next_before_id);
      return true;
    } catch (cause) {
      if (generation.current === current && selectionGeneration.current === selection) setOlderError(errorMessage(cause));
      return false;
    } finally {
      if (generation.current === current && selectionGeneration.current === selection) setOlderLoading(false);
    }
  }

  async function send(question: string): Promise<boolean> {
    if (!adapter || sending.current || messagesLoading || question.trim().length < 3) return false;
    const trimmed = question.trim();
    const current = generation.current;
    const selection = selectionGeneration.current;
    const conversationId = selectedId;
    const previous = retryTurn.current;
    const clientTurnId = previous?.question === trimmed && previous.conversationId === conversationId
      ? previous.id : crypto.randomUUID();
    retryTurn.current = { question: trimmed, conversationId, id: clientTurnId };
    sending.current = true;
    setSendLoading(true);
    setSendError("");
    try {
      const answer = await adapter.send(scope, trimmed, clientTurnId, conversationId || undefined);
      if (generation.current !== current || selectionGeneration.current !== selection) return false;
      if (!answer.conversation_id || !answer.turn_id) throw new Error("Сервер не подтвердил сохранение диалога.");
      retryTurn.current = null;
      setSelectedId(answer.conversation_id);
      const createdAt = new Date().toISOString();
      setMessages((old) => [...old,
        { id: `${answer.turn_id}:user`, turn_id: answer.turn_id, role: "user", content: trimmed, created_at: createdAt },
        { id: `${answer.turn_id}:assistant`, turn_id: answer.turn_id, role: "assistant", content: answer.answer,
          sources: answer.sources, escalate_to_hr: answer.escalate_to_hr, mode: answer.mode, created_at: createdAt },
      ]);
      void refreshList();
      return true;
    } catch (cause) {
      if (generation.current === current && selectionGeneration.current === selection) setSendError(errorMessage(cause));
      return false;
    } finally {
      if (generation.current === current && selectionGeneration.current === selection) {
        sending.current = false;
        setSendLoading(false);
      }
    }
  }

  return {
    enabled: Boolean(adapter), conversations, nextCursor, listLoading, listMoreLoading, listError,
    selectedId, messages, nextBeforeId, messagesLoading, messagesError, olderLoading, olderError,
    sendLoading, sendError, refreshList, loadMoreConversations, openConversation,
    newConversation, loadOlderMessages, send,
  };
}
