"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { employeeMessages } from "./employee-messages";

export type EmployeeLanguage = "ru" | "kk";
export const employeeLanguageKey = "jana-hr.employee-language";
const Locale = createContext<EmployeeLanguage>("ru");
const kazakhMonths = ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"];
const kazakhShortMonths = ["қаң", "ақп", "нау", "сәу", "мам", "мау", "шіл", "там", "қыр", "қаз", "қар", "жел"];
const asDate = (value: string) => new Date(value.length === 10 ? `${value}T00:00:00Z` : value);
const format = (message: string, values: unknown[]) => message.replace(/\{(\d+)\}/g, (match, index) => index < values.length ? String(values[index]) : match);
const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const templates = Object.entries(employeeMessages).filter(([key]) => /\{\d+\}/.test(key)).sort(([a], [b]) => b.replace(/\{\d+\}/g, "").length - a.replace(/\{\d+\}/g, "").length).map(([key, translation]) => {
  const slots: number[] = [];
  const parts = key.split(/(\{\d+\})/).map(part => {
    if (/^\{\d+\}$/.test(part)) { slots.push(Number(part.slice(1, -1))); return key.includes(`№${part}`) ? "([0-9]+)" : "(.+?)"; }
    return escape(part);
  });
  return { pattern: new RegExp(`^${parts.join("")}$`), translation, slots };
});

export function employeeI18n(language: EmployeeLanguage) {
  const t = (source: string, ...values: unknown[]): string => {
    if (language === "ru") return format(source, values);
    const key = source.trim();
    const prefix = source.slice(0, source.indexOf(key));
    const suffix = source.slice(source.indexOf(key) + key.length);
    if (employeeMessages[key]) return prefix + format(employeeMessages[key], values) + suffix;
    // Backend errors/toasts are kept in their original form in state. Translate
    // recognized system templates when rendering, so switching back is lossless.
    if (!values.length) for (const entry of templates) {
      const match = key.match(entry.pattern);
      if (match) {
        const params: string[] = [];
        entry.slots.forEach((slot, index) => { params[slot] = match[index + 1]; });
        return prefix + format(entry.translation, params) + suffix;
      }
    }
    return format(source, values);
  };
  const locale = language === "kk" ? "kk-KZ" : "ru-RU";
  return {
    language, locale, t,
    // Explicit Kazakh month names also work in browsers with limited ICU data.
    date: (value: string, full = false) => language === "kk"
      ? `${asDate(value).getUTCDate()} ${(full ? kazakhMonths : kazakhShortMonths)[asDate(value).getUTCMonth()]} ${asDate(value).getUTCFullYear()}${full ? " ж." : ""}`
      : new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: full ? "long" : "short", year: "numeric", timeZone: "UTC" }).format(asDate(value)),
    dateTime: (value: string) => language === "kk"
      ? `${asDate(value).getDate()} ${kazakhShortMonths[asDate(value).getMonth()]}, ${String(asDate(value).getHours()).padStart(2, "0")}:${String(asDate(value).getMinutes()).padStart(2, "0")}`
      : new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(asDate(value)),
    month: (value: string) => language === "kk"
      ? `${asDate(value).getUTCFullYear()} ж. ${kazakhMonths[asDate(value).getUTCMonth()]}`
      : new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric", timeZone: "UTC" }).format(asDate(value)),
  };
}

export function useEmployeeLanguage() {
  const [language, setLanguage] = useState<EmployeeLanguage>("ru");
  useEffect(() => {
    try { if (localStorage.getItem(employeeLanguageKey) === "kk") setLanguage("kk"); } catch { /* Storage may be unavailable. */ }
  }, []);
  return { language, changeLanguage(value: string) {
    const next = value === "kk" ? "kk" : "ru";
    setLanguage(next);
    try { localStorage.setItem(employeeLanguageKey, next); } catch { /* Switching still works in memory. */ }
  } };
}

export function EmployeeLocaleProvider({ language, children }: { language: EmployeeLanguage; children: ReactNode }) {
  useEffect(() => {
    document.documentElement.lang = language;
    return () => { document.documentElement.lang = "ru"; };
  }, [language]);
  return <Locale.Provider value={language}>{children}</Locale.Provider>;
}

export function useEmployeeI18n() {
  const language = useContext(Locale);
  return useMemo(() => employeeI18n(language), [language]);
}
