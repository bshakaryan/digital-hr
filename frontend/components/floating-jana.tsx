"use client";

import styles from "./floating-jana.module.css";

/** Mount inside the authenticated Workspace, outside the assistant tab. */
export function FloatingJana() {
  return <a className={styles.launcher} href="#assistant" aria-label="Открыть чат AI Jana">
    <span className={styles.character} aria-hidden="true">
      <svg viewBox="0 0 72 72" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="36" cy="36" r="33" fill="#ECF7EC" />
        <path d="M15 36c-3 0-5 2-5 5s2 5 5 5h3V36h-3Zm42 0c3 0 5 2 5 5s-2 5-5 5h-3V36h3Z" fill="#B7DEB9" stroke="#168632" strokeWidth="1.5" />
        <path d="M19 28c0-10 7-17 17-17s17 7 17 17v3H19v-3Z" fill="#008C00" />
        <path d="M25 24c3-5 7-7 12-7" stroke="white" strokeOpacity=".75" strokeWidth="2" strokeLinecap="round" />
        <rect x="17" y="27" width="38" height="34" rx="15" fill="white" stroke="#168632" strokeWidth="2" />
        <path d="M27 40v3m18-3v3" stroke="#165829" strokeWidth="3" strokeLinecap="round" />
        <path d="M31 50c3 3 7 3 10 0" stroke="#165829" strokeWidth="2" strokeLinecap="round" />
        <circle cx="49" cy="48" r="2" fill="#D4EDD4" />
        <path d="M30 61h12" stroke="#168632" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </span>
    <span className={styles.label}><strong>AI Jana</strong><small>Спросить</small></span>
  </a>;
}
