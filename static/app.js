/**
 * Iris frontend.
 *
 * Plain JS, no framework, no build step, matching the rest of this
 * deployment (Render serves this as static files from the same
 * FastAPI app that serves the API, so there is no separate host and
 * no CORS to configure).
 *
 * Auth: Clerk's vanilla JS SDK (see index.html for the script-tag
 * setup). Clerk.session.getToken() is called fresh before every
 * request rather than cached, since the underlying JWT is short-lived
 * and Clerk handles refreshing it internally.
 *
 * The transcript itself is never held here beyond what's rendered on
 * screen: the server owns it (app/session.py's Session.messages), so
 * a page refresh just re-fetches the session's current state rather
 * than replaying a client-side history the server would have to trust.
 */

const SESSION_STORAGE_KEY = "iris_session_id";

let currentSessionId = null;
let currentAttachment = null; // { attachment_id, filename } | null

// ---------------------------------------------------------------------------
// Boot: wait for Clerk, then react to sign-in state
// ---------------------------------------------------------------------------

window.addEventListener("load", async function () {
  try {
    // The Clerk bundles are loaded by deferred <script> tags in
    // index.html, with values the server substituted in. By the time
    // the window load event fires, they have executed and defined the
    // Clerk global. Runtime injection from here was tried and
    // reverted: Clerk's loader discovers its publishable key from its
    // own script tag and does not do so reliably for dynamically
    // inserted scripts, which left Clerk undefined.
    if (typeof Clerk === "undefined") {
      throw new Error(
        "The Clerk library did not load. Check the browser console for a " +
          "blocked or failed request to the Clerk CDN."
      );
    }
    await Clerk.load({ ui: { ClerkUI: window.__internal_ClerkUICtor } });
  } catch (err) {
    showBootError(err);
    return;
  }

  document.getElementById("boot-loading").hidden = true;
  Clerk.addListener(handleAuthStateChange);
  handleAuthStateChange({ user: Clerk.user });
});

function showBootError(err) {
  // Deliberately shows the real reason rather than one generic
  // string. Everything reachable here is a client-side configuration
  // problem, never server internals, and a single opaque message made
  // an earlier misconfiguration genuinely hard to diagnose.
  const boot = document.getElementById("boot-loading");
  boot.innerHTML = "";
  const heading = document.createElement("div");
  heading.className = "boot-error-heading";
  heading.textContent = "Iris could not start.";
  const detail = document.createElement("div");
  detail.className = "boot-error-detail";
  detail.textContent = (err && err.message) || String(err);
  boot.appendChild(heading);
  boot.appendChild(detail);
}

let appInitialized = false;

function handleAuthStateChange({ user }) {
  const signInContainer = document.getElementById("sign-in-container");
  const app = document.getElementById("app");

  if (user) {
    signInContainer.hidden = true;
    app.hidden = false;
    if (!appInitialized) {
      appInitialized = true;
      mountUserButton();
      initApp();
    }
  } else {
    app.hidden = true;
    signInContainer.hidden = false;
    signInContainer.innerHTML = "";
    Clerk.mountSignIn(signInContainer);
    appInitialized = false;
  }
}

function mountUserButton() {
  const container = document.getElementById("user-button-container");
  container.innerHTML = "";
  Clerk.mountUserButton(container);
}

// ---------------------------------------------------------------------------
// Authenticated fetch
// ---------------------------------------------------------------------------

async function apiFetch(path, options) {
  options = options || {};
  const token = await Clerk.session.getToken();
  const headers = Object.assign({}, options.headers, { Authorization: "Bearer " + token });
  return fetch(path, Object.assign({}, options, { headers: headers }));
}

async function withSessionRetry(makeRequest) {
  /* The server's session store is in memory on a single instance, so
     every deploy, restart, or idle-eviction destroys every live
     session. bootstrapSession() handles that at page load, but a
     session can just as easily vanish mid-conversation while the tab
     sits open, and until now that surfaced as a dead-end 404 with no
     way forward short of a manual reload.

     Recovering here rather than only at boot is the right layer: any
     session-scoped call can hit it. The user is told plainly that
     context was lost rather than being left to wonder why the
     assistant forgot everything, since a silent recovery would be
     worse than the error it replaces. */
  let response = await makeRequest(currentSessionId);
  if (response.status !== 404) {
    return response;
  }
  currentSessionId = await createNewSession();
  appendMessage(
    "system",
    "That session had expired, most likely because the server restarted. " +
      "Started a fresh one and retried, but the earlier conversation is gone. " +
      "Re-attach any file you had uploaded."
  );
  return makeRequest(currentSessionId);
}

// ---------------------------------------------------------------------------
// Session bootstrap: reuse a saved session if it still exists, else create
// one. The transcript itself is not restored into the message list on
// reload in this version - see the note in the module docstring above about
// why the server, not this file, is the source of truth for it.
// ---------------------------------------------------------------------------

async function initApp() {
  wireComposer();
  document.getElementById("new-session-btn").addEventListener("click", startNewSession);
  try {
    currentSessionId = await bootstrapSession();
  } catch (err) {
    appendMessage(
      "error",
      "Could not start a session. Refresh the page to try again; if it keeps happening, the backend may be down."
    );
  }
}

async function bootstrapSession() {
  const saved = localStorage.getItem(SESSION_STORAGE_KEY);
  if (saved) {
    const check = await apiFetch("/sessions/" + saved);
    if (check.ok) {
      return saved;
    }
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }
  return createNewSession();
}

async function createNewSession() {
  const response = await apiFetch("/sessions", { method: "POST" });
  if (!response.ok) {
    throw new Error("Failed to create a session (status " + response.status + ")");
  }
  const body = await response.json();
  localStorage.setItem(SESSION_STORAGE_KEY, body.session_id);
  return body.session_id;
}

async function startNewSession() {
  // Previously had no error handling and no success feedback, so a
  // failure was silent and a success looked identical to nothing
  // happening at all: both read as "the button does nothing."
  const btn = document.getElementById("new-session-btn");
  btn.disabled = true;
  try {
    clearAttachmentChip();
    document.getElementById("message-list").innerHTML = "";
    currentSessionId = await createNewSession();
    appendMessage("system", "Started a new session.");
  } catch (err) {
    appendMessage("error", "Could not start a new session. Check your connection and try again.");
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Composer: message input, attach, send
// ---------------------------------------------------------------------------

function wireComposer() {
  const input = document.getElementById("message-input");
  const sendBtn = document.getElementById("send-btn");
  const attachBtn = document.getElementById("attach-btn");
  const fileInput = document.getElementById("file-input");
  const removeChipBtn = document.getElementById("attachment-chip-remove");

  sendBtn.addEventListener("click", sendMessage);

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Grows with content up to the CSS max-height, then scrolls.
  input.addEventListener("input", function () {
    input.style.height = "auto";
    input.style.height = input.scrollHeight + "px";
  });

  attachBtn.addEventListener("click", function () {
    fileInput.click();
  });

  fileInput.addEventListener("change", handleFileSelected);
  removeChipBtn.addEventListener("click", clearAttachmentChip);
}

async function handleFileSelected(event) {
  const file = event.target.files[0];
  event.target.value = ""; // allow re-selecting the same file later
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  setComposerDisabled(true);
  try {
    const response = await withSessionRetry(function (sessionId) {
      return apiFetch("/sessions/" + sessionId + "/attachments", {
        method: "POST",
        body: formData,
      });
    });
    if (!response.ok) {
      const body = await safeJson(response);
      appendMessage("error", (body && body.detail) || "Could not attach that file.");
      return;
    }
    const body = await response.json();
    currentAttachment = { attachment_id: body.attachment_id, filename: body.filename };
    showAttachmentChip(body.filename);
  } catch (err) {
    appendMessage("error", "Could not upload the file. Check your connection and try again.");
  } finally {
    setComposerDisabled(false);
  }
}

function showAttachmentChip(filename) {
  const chip = document.getElementById("attachment-chip");
  document.getElementById("attachment-chip-label").textContent = filename;
  chip.hidden = false;
}

function clearAttachmentChip() {
  currentAttachment = null;
  document.getElementById("attachment-chip").hidden = true;
}

async function sendMessage() {
  const input = document.getElementById("message-input");
  const text = input.value.trim();
  if (!text && !currentAttachment) return;

  // The model receives attachment_id as a short reference inside the
  // message text, not the file's bytes: ingest_document (T-0.1) reads
  // the file from the session server-side. This keeps the chat
  // request schema as plain text with no dedicated attachment field,
  // since a filename and a UUID cost nothing like the base64 dump
  // this mechanism exists to avoid.
  let messageToSend = text;
  if (currentAttachment) {
    messageToSend +=
      "\n\n[Attached file: " +
      currentAttachment.filename +
      ", attachment_id: " +
      currentAttachment.attachment_id +
      ". Use ingest_document to read it.]";
  }

  appendMessage("user", text || "Attached " + currentAttachment.filename);
  input.value = "";
  input.style.height = "auto";
  clearAttachmentChip();
  setComposerDisabled(true);
  showThinking(true);

  try {
    const response = await withSessionRetry(function (sessionId) {
      return apiFetch("/sessions/" + sessionId + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: messageToSend }),
      });
    });
    showThinking(false);
    if (response.ok) {
      const body = await response.json();
      appendMessage("assistant", body.text);
    } else {
      await handleChatError(response);
    }
  } catch (err) {
    showThinking(false);
    appendMessage("error", "Could not reach Iris. Check your connection and try again.");
  } finally {
    setComposerDisabled(false);
    input.focus();
  }
}

async function handleChatError(response) {
  const body = await safeJson(response);
  const detail =
    body && typeof body.detail === "string"
      ? body.detail
      : body && body.detail && body.detail.message
        ? body.detail.message
        : "";

  if (response.status === 429) {
    appendMessage("system", "You're sending messages faster than Iris can keep up. Wait a bit and try again.");
  } else if (response.status === 409) {
    appendMessage("system", detail || "Iris could not finish that. Try rephrasing.");
  } else if (response.status === 400) {
    appendMessage("error", detail || "That request was not valid.");
  } else if (response.status === 401) {
    appendMessage("error", "Your session expired. Refresh the page and sign in again.");
  } else {
    appendMessage("error", "Something went wrong on Iris's end. Try again in a moment.");
  }
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch (err) {
    return null;
  }
}

function setComposerDisabled(disabled) {
  document.getElementById("send-btn").disabled = disabled;
  document.getElementById("attach-btn").disabled = disabled;
  document.getElementById("message-input").disabled = disabled;
}

function showThinking(visible) {
  document.getElementById("thinking-indicator").hidden = !visible;
  if (visible) {
    document.getElementById("thinking-indicator").scrollIntoView({ behavior: "smooth", block: "end" });
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function appendMessage(role, text) {
  const list = document.getElementById("message-list");
  const el = document.createElement("div");
  el.className = "message message-" + role;
  el.textContent = text;
  list.appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
}
