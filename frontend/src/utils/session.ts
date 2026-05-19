/**
 * utils/session.js
 * -----------------
 * Persistent session management for the Research Assistant frontend.
 *
 * THE BUG THIS FIXES:
 *   Without this file, the app generates a fresh UUID on every page load.
 *   That means every refresh creates a brand-new session in the DB — the
 *   backend has no idea who the user is, so it "forgets" everything.
 *
 * THE FIX:
 *   We store the session_id in localStorage on first visit, then reuse it
 *   on every subsequent page load. The backend receives the same session_id
 *   each time, so it can reload history from SQLite and remember the user.
 *
 * USAGE:
 *   import { getSessionId, resetSession } from './utils/session';
 *
 *   // Always use this instead of crypto.randomUUID() directly:
 *   const sessionId = getSessionId();
 *
 *   // To start a fresh conversation (e.g. "New Chat" button):
 *   const newId = resetSession();
 */

const STORAGE_KEY = "research_assistant_session_id";

/**
 * Returns the persistent session ID, creating one if it doesn't exist yet.
 * Safe to call on every render — reads from localStorage, never regenerates.
 *
 * @returns {string} UUID v4 session identifier
 */
export function getSessionId(): string {
  let sessionId = localStorage.getItem(STORAGE_KEY);

  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, sessionId);
    console.debug("[session] New session created:", sessionId);
  } else {
    console.debug("[session] Resumed session:", sessionId);
  }

  return sessionId;
}

/**
 * Clears the current session and generates a fresh one.
 * Call this when the user clicks "New Chat" or "Clear History".
 *
 * @returns {string} The new session ID
 */
export function resetSession(): string {
  const newId = crypto.randomUUID();
  localStorage.setItem(STORAGE_KEY, newId);
  console.debug("[session] Session reset. New ID:", newId);
  return newId;
}

/**
 * Returns the raw value from localStorage without creating a new one.
 * Returns null if no session has been created yet.
 *
 * @returns {string | null}
 */
export function peekSessionId(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}