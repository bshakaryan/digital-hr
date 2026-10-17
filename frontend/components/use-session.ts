"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiClient, ApiError, errorMessage, type Profile } from "@/lib/api";

export interface Session { token: string; profile: Profile }
const storageKey = "jana-hr.access-token";

function readToken(): string | null {
  try { return window.sessionStorage.getItem(storageKey); }
  catch { return null; }
}

function storeToken(token: string | null) {
  // Storage can be disabled by the browser; the current page can still sign in.
  try {
    if (token) window.sessionStorage.setItem(storageKey, token);
    else window.sessionStorage.removeItem(storageKey);
  } catch { /* Fall back to the in-memory session. */ }
}

export function useSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [message, setMessage] = useState("");
  const [restoring, setRestoring] = useState(true);
  const [restoreError, setRestoreError] = useState("");
  const [revision, setRevision] = useState(0);
  const currentToken = useRef<string | null>(null);

  const expire = useCallback((token: string) => {
    // Requests from an old workspace must not clear a newer login.
    if (currentToken.current !== token) return;
    currentToken.current = null;
    storeToken(null);
    setSession(null);
    setMessage("Сессия завершена. Войдите снова, чтобы продолжить.");
  }, []);

  useEffect(() => {
    let active = true;
    setRestoring(true);
    setRestoreError("");
    const token = readToken();
    currentToken.current = token;
    if (!token) { setRestoring(false); return; }

    // Only the token is stored. Profile and permissions come from the server.
    new ApiClient(token).call<Profile>("/me")
      .then((profile) => {
        if (active && currentToken.current === token) setSession({ token, profile });
      })
      .catch((cause: unknown) => {
        if (!active || currentToken.current !== token) return;
        if (cause instanceof ApiError && cause.status === 401) expire(token);
        else setRestoreError(errorMessage(cause));
      })
      .finally(() => { if (active) setRestoring(false); });
    return () => { active = false; };
  }, [revision, expire]);

  const login = useCallback((value: Session) => {
    currentToken.current = value.token;
    storeToken(value.token);
    setMessage("");
    setSession(value);
  }, []);

  const logout = useCallback(() => {
    currentToken.current = null;
    storeToken(null);
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setSession(null);
    setMessage("");
    setRestoreError("");
  }, []);

  const retry = useCallback(() => setRevision((value) => value + 1), []);
  const api = useMemo(() => session ? new ApiClient(session.token, () => expire(session.token)) : null, [session, expire]);
  return { session, api, message, restoring, restoreError, login, logout, retry };
}
