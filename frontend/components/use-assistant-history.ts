"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, type AssistantAnswer } from "@/lib/api";
import { HistoryUnavailableError, sameScope, type ChatHistoryAdapter, type ChatScope, type ConversationSummary, type StoredChatMessage } from "./assistant-history-adapter";

export interface HistoryExchange {
  id: string;
  question: string;
  result: AssistantAnswer;
}

export function exchangesFromMessages(messages: StoredChatMessage[]): HistoryExchange[] {
  const questions = new Map<number, string>();
  const exchanges: HistoryExchange[] = [];
  for (const message of messages) {
    if (message.role === "user") questions.set(message.turn_id, message.content);
    else {
      const question = questions.get(message.turn_id);
      if (question === undefined) continue;
      exchanges.push({
        id: String(message.turn_id), question,
        result: {
          answer: message.content,
          sources: message.sources || [],
          escalate_to_hr: message.escalate_to_hr ?? false,
          mode: message.mode ?? "extractive_demo",
        },
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
  const retryTurn = useRef<{ question: string; conversationId: number | null; id: string } | null>(null);
  const [activeScopeKey, setActiveScopeKey] = useState(scopeKey);
  const [unavailable, setUnavailable] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [nextPage, setNextPage] = useState<number | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [listMoreLoading, setListMoreLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messages, setMessages] = useState<StoredChatMessage[]>([]);
  const [previousPage, setPreviousPage] = useState<number | null>(null);
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
      setNextPage(page.nextPage);
    } catch (cause) {
      if (generation.current === current) {
        if (cause instanceof HistoryUnavailableError) setUnavailable(true);
        else setListError(errorMessage(cause));
      }
    } finally {
      if (generation.current === current) setListLoading(false);
    }
  }, [adapter, scopeKey]); // scope is identified by its stable kind/course ID.

  useEffect(() => {
    generation.current += 1;
    selectionGeneration.current += 1;
    retryTurn.current = null;
    setActiveScopeKey(scopeKey);
    setUnavailable(false);
    setConversations([]);
    setNextPage(null);
    setSelectedId(null);
    setMessages([]);
    setPreviousPage(null);
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
    if (!adapter || unavailable || activeScopeKey !== scopeKey || !nextPage || listMoreLoading) return;
    const current = generation.current;
    setListMoreLoading(true);
    setListError("");
    try {
      const page = await adapter.list(scope, nextPage);
      if (generation.current !== current) return;
      setConversations((old) => {
        const ids = new Set(old.map((item) => item.id));
        return [...old, ...page.items.filter((item) => sameScope(scope, item) && !ids.has(item.id))];
      });
      setNextPage(page.nextPage);
    } catch (cause) {
      if (generation.current === current) {
        if (cause instanceof HistoryUnavailableError) setUnavailable(true);
        else setListError(errorMessage(cause));
      }
    } finally {
      if (generation.current === current) setListMoreLoading(false);
    }
  }

  async function openConversation(id: number) {
    if (!adapter || unavailable || activeScopeKey !== scopeKey || sending.current) return;
    const current = generation.current;
    const selection = ++selectionGeneration.current;
    retryTurn.current = null;
    setSelectedId(id);
    setMessages([]);
    setPreviousPage(null);
    setSendError("");
    setMessagesError("");
    setOlderError("");
    setMessagesLoading(true);
    try {
      const page = await adapter.open(scope, id);
      if (generation.current !== current || selectionGeneration.current !== selection) return;
      if (page.id !== id || !sameScope(scope, page)) throw new Error("Диалог не относится к этому разделу.");
      setMessages(page.messages);
      setPreviousPage(page.previousPage);
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
    setPreviousPage(null);
    setMessagesError("");
    setOlderError("");
    setSendError("");
    setMessagesLoading(false);
  }

  async function loadOlderMessages(): Promise<boolean> {
    if (!adapter || unavailable || activeScopeKey !== scopeKey || !selectedId || !previousPage || olderLoading || messagesLoading) return false;
    const current = generation.current;
    const selection = selectionGeneration.current;
    const id = selectedId;
    setOlderLoading(true);
    setOlderError("");
    try {
      const page = await adapter.open(scope, id, previousPage);
      if (generation.current !== current || selectionGeneration.current !== selection) return false;
      if (page.id !== id || !sameScope(scope, page)) throw new Error("Диалог не относится к этому разделу.");
      setMessages((old) => {
        const ids = new Set(old.map((message) => message.id));
        return [...page.messages.filter((message) => !ids.has(message.id)), ...old];
      });
      setPreviousPage(page.previousPage);
      return true;
    } catch (cause) {
      if (generation.current === current && selectionGeneration.current === selection) setOlderError(errorMessage(cause));
      return false;
    } finally {
      if (generation.current === current && selectionGeneration.current === selection) setOlderLoading(false);
    }
  }

  async function send(question: string): Promise<boolean> {
    if (!adapter || unavailable || activeScopeKey !== scopeKey || sending.current || messagesLoading || question.trim().length < 3) return false;
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
      if (!answer.conversation_id || !answer.turn_id || answer.client_turn_id !== clientTurnId)
        throw new Error("Сервер не подтвердил сохранение диалога.");
      retryTurn.current = null;
      setSelectedId(answer.conversation_id);
      const createdAt = new Date().toISOString();
      setMessages((old) => [...old,
        { id: `${answer.turn_id}:user`, turn_id: answer.turn_id, role: "user", content: trimmed,
          sources: [], escalate_to_hr: null, mode: null, created_at: createdAt },
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

  const scopeReady = activeScopeKey === scopeKey;
  return {
    enabled: Boolean(adapter) && !unavailable,
    conversations: scopeReady ? conversations : [], nextPage: scopeReady ? nextPage : null,
    listLoading, listMoreLoading, listError,
    selectedId: scopeReady ? selectedId : null, messages: scopeReady ? messages : [],
    previousPage: scopeReady ? previousPage : null, messagesLoading, messagesError, olderLoading, olderError,
    sendLoading, sendError, refreshList, loadMoreConversations, openConversation,
    newConversation, loadOlderMessages, send,
  };
}
