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
    // Fetch app config (non-Clerk fields like feedback_url) in the
    // background — not load-blocking since Clerk is already up.
    try {
      const cfgRes = await fetch("/config");
      if (cfgRes.ok) { window._irisConfig = await cfgRes.json(); }
    } catch (_) { /* non-fatal — feedback form just shows unavailable */ }
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
  document.getElementById("empty-state").style.display = "none";
  document.getElementById("composer").hidden = false;
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
  document.getElementById("start-session-btn").addEventListener("click", startFirstSession);

  // Help modal wiring. The modal has no [hidden] attribute — that
  // attribute triggers [hidden]{display:none!important} which fights
  // the JS display:flex open state. Instead the modal starts at
  // display:none via its own CSS rule and we toggle inline style.
  const helpBtn = document.getElementById("help-btn");
  const helpModal = document.getElementById("help-modal");
  const helpClose = document.getElementById("help-modal-close");
  const backdrop = helpModal.querySelector(".help-modal-backdrop");
  let feedbackLoaded = false;

  function openHelp() { helpModal.style.display = "flex"; }
  function closeHelp() { helpModal.style.display = "none"; }

  helpBtn.addEventListener("click", openHelp);
  helpClose.addEventListener("click", closeHelp);
  backdrop.addEventListener("click", closeHelp);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && helpModal.style.display === "flex") closeHelp();
  });

  // Tab switching
  document.querySelectorAll(".help-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".help-tab").forEach(function (t) { t.classList.remove("active"); });
      document.querySelectorAll(".help-tab-content").forEach(function (c) { c.style.display = "none"; });
      tab.classList.add("active");
      const target = document.getElementById("help-tab-" + tab.dataset.tab);
      if (target) target.style.display = "flex";

      // Lazy-load the feedback iframe the first time the tab opens
      if (tab.dataset.tab === "feedback" && !feedbackLoaded) {
        feedbackLoaded = true;
        loadFeedbackFrame();
      }
    });
  });

  function loadFeedbackFrame() {
    const container = document.getElementById("feedback-frame-container");
    const url = window._irisConfig && window._irisConfig.feedback_url;
    if (url) {
      const iframe = document.createElement("iframe");
      iframe.src = url;
      iframe.title = "Iris feedback form";
      iframe.setAttribute("frameborder", "0");
      iframe.setAttribute("marginheight", "0");
      iframe.setAttribute("marginwidth", "0");
      container.innerHTML = "";
      container.appendChild(iframe);
    } else {
      container.innerHTML = '<div class="feedback-unavailable">Feedback form coming soon.</div>';
    }
  }
  // Don't create a session eagerly — wait for the user to click
  // "Start a session." The composer stays hidden until that click.
}

async function startFirstSession() {
  const btn = document.getElementById("start-session-btn");
  btn.disabled = true;
  btn.textContent = "Starting...";
  try {
    currentSessionId = await createNewSession();
    // Swap the empty state for the working surface
    document.getElementById("empty-state").style.display = "none";
    document.getElementById("composer").hidden = false;
    document.getElementById("message-input").focus();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Start a session";
    appendMessage("error", "Could not start a session. Check your connection and try again.");
    document.getElementById("empty-state").style.display = "none";
    document.getElementById("composer").hidden = false;
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
    document.getElementById("empty-state").style.display = "none";
    document.getElementById("composer").hidden = false;
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
  showStatus("Sending...");  // immediately replaced by server's first status event

  try {
    const response = await withSessionRetry(function (sessionId) {
      return apiFetch("/sessions/" + sessionId + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: messageToSend }),
      });
    });

    // Pre-flight failures (rate limit, bad tool_ids, auth) are checked
    // in main.py before any streaming starts and still come back as a
    // plain JSON error response with a real HTTP status, exactly as
    // before this change - only a successful response is a stream.
    if (!response.ok) {
      hideStatus();
      await handleChatError(response);
      return;
    }

    await consumeChatStream(response);
  } catch (err) {
    hideStatus();
    appendMessage("error", "Could not reach Iris. Check your connection and try again.");
  } finally {
    setComposerDisabled(false);
    input.focus();
  }
}

async function consumeChatStream(response) {
  // Server-Sent Events, read by hand rather than via EventSource:
  // EventSource only supports GET, and this is a POST. Each event is
  // "data: <json>\n\n"; chunks can split an event across reads, so
  // partial text is buffered and only complete events (delimited by
  // the blank line) are parsed out of it.
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawTerminalEvent = false;

  // Live-streamed assistant text for this turn. Before "text_delta"
  // existed, the UI had nothing to show between the last tool_call/
  // tool_result and the final "done" event - so a slow-but-healthy
  // response generating several thousand tokens looked identical to a
  // hung one, for as long as it took to finish. streamingEl is created
  // on the first delta and grown in place; "done" always overwrites it
  // with the authoritative final text rather than trusting the
  // accumulated deltas, since a max_tokens cutoff notice is appended
  // server-side after streaming ends and was never itself streamed.
  let streamingEl = null;
  let streamingBuffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const line = rawEvent.split("\n").find(function (l) {
        return l.indexOf("data: ") === 0;
      });
      if (!line) continue;

      let event;
      try {
        event = JSON.parse(line.slice("data: ".length));
      } catch (err) {
        continue; // an unparseable event is dropped, not fatal to the stream
      }

      if (event.type === "status") {
        showStatus(event.message);
      } else if (event.type === "tool_call") {
        showStatus("Running: " + event.tool);
      } else if (event.type === "text_delta") {
        if (!streamingEl) {
          hideStatus();
          streamingEl = appendStreamingMessage();
        }
        streamingBuffer += event.text;
        streamingEl.innerHTML = renderMarkdown(streamingBuffer);
        streamingEl.scrollIntoView({ behavior: "smooth", block: "end" });
      } else if (event.type === "file_ready") {
        appendDownloadButton(event.filename, event.content_type, event.data_base64);
      } else if (event.type === "done") {
        sawTerminalEvent = true;
        hideStatus();
        if (streamingEl) {
          streamingEl.innerHTML = renderMarkdown(event.text);
          streamingEl.scrollIntoView({ behavior: "smooth", block: "end" });
        } else {
          appendMessage("assistant", event.text);
        }
        streamingEl = null;
        streamingBuffer = "";
      } else if (event.type === "error") {
        sawTerminalEvent = true;
        hideStatus();
        appendMessage("system", event.detail || "Something went wrong on Iris's end. Try again in a moment.");
        streamingEl = null;
        streamingBuffer = "";
      }
      // "tool_result" carries no separate UI treatment: the tool_call
      // event already said what was running, and the next status or
      // tool_call event replaces it, which is enough signal without
      // adding a second, competing display for pass/fail detail the
      // final assistant message will already summarize.
    }
  }

  if (!sawTerminalEvent) {
    // The connection closed with no "done" or "error" event, most
    // likely a network drop or the server process restarting
    // mid-stream (the same in-memory-session reality withSessionRetry
    // exists for). Silence here would be exactly the empty-bubble
    // problem this whole mechanism was built to avoid.
    hideStatus();
    appendMessage("error", "The connection to Iris was lost partway through. Try again.");
  }
}

async function handleChatError(response) {
  // Only ever reached for pre-flight failures now (429 rate limit, 400
  // bad tool_ids, 401 auth, or a 404 the session-retry already failed
  // to recover from) - main.py checks all of these before starting
  // the SSE stream. Anything that happens once the model is actually
  // involved (upstream API errors, tool-loop exhaustion) arrives as an
  // "error" event inside the stream instead, handled in
  // consumeChatStream, since by that point the HTTP status is already
  // committed to 200 and cannot change.
  const body = await safeJson(response);
  const detail =
    body && typeof body.detail === "string"
      ? body.detail
      : body && body.detail && body.detail.message
        ? body.detail.message
        : "";

  if (response.status === 429) {
    appendMessage("system", "You're sending messages faster than Iris can keep up. Wait a bit and try again.");
  } else if (response.status === 422) {
    appendMessage("error", "That message is too long to send directly. Attach your resume as a file using the + button instead of pasting it.");
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

function showStatus(text) {
  const indicator = document.getElementById("status-indicator");
  document.getElementById("status-text").textContent = text;
  indicator.hidden = false;
  indicator.scrollIntoView({ behavior: "smooth", block: "end" });
}

function hideStatus() {
  document.getElementById("status-indicator").hidden = true;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function appendMessage(role, text) {
  const list = document.getElementById("message-list");
  const el = document.createElement("div");
  el.className = "message message-" + role;
  if (role === "assistant") {
    el.innerHTML = renderMarkdown(text);
  } else {
    el.textContent = text;
  }
  list.appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
}

function appendStreamingMessage() {
  // Empty assistant bubble, grown in place as "text_delta" events
  // arrive. Separate from appendMessage because that one sets content
  // and returns nothing - this needs the element handle back so
  // consumeChatStream can keep updating the same node.
  const list = document.getElementById("message-list");
  const el = document.createElement("div");
  el.className = "message message-assistant";
  list.appendChild(el);
  return el;
}

function appendDownloadButton(filename, contentType, dataBase64) {
  const list = document.getElementById("message-list");
  const card = document.createElement("div");
  card.className = "download-card";

  const icon = document.createElement("span");
  icon.className = "download-icon";
  icon.textContent = "\u2193";

  const label = document.createElement("span");
  label.className = "download-filename";
  label.textContent = filename;

  const btn = document.createElement("a");
  btn.className = "lore-btn-primary download-btn";
  btn.textContent = "Download";
  btn.download = filename;

  if (dataBase64) {
    btn.href = "data:" + contentType + ";base64," + dataBase64;
  } else {
    btn.href = "/sessions/" + currentSessionId + "/files/" + filename;
  }

  card.appendChild(icon);
  card.appendChild(label);
  card.appendChild(btn);
  list.appendChild(card);
  card.scrollIntoView({ behavior: "smooth", block: "end" });
}

function renderMarkdown(text) {
  // Minimal safe markdown rendering: bold, inline code, and bullet
  // lists only. Does NOT use innerHTML on raw text: each segment is
  // built as a DOM node (never innerHTML on user/model-supplied
  // content) — specifically to handle resume text and document
  // excerpts that may contain < > & characters or look like HTML.
  // The approach: split on the patterns we handle, process segment
  // by segment, assemble into a DocumentFragment, then return the
  // outer HTML of a wrapper div.
  const wrapper = document.createElement("div");
  const lines = text.split("\n");
  let inBulletList = false;
  let ul = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      if (inBulletList) { wrapper.appendChild(ul); ul = null; inBulletList = false; }
      wrapper.appendChild(document.createElement("hr"));
      continue;
    }

    // Bullet list item
    if (/^[-*] /.test(line)) {
      if (!inBulletList) { ul = document.createElement("ul"); inBulletList = true; }
      const li = document.createElement("li");
      appendInlineMarkdown(li, line.replace(/^[-*] /, ""));
      ul.appendChild(li);
      continue;
    }

    if (inBulletList) { wrapper.appendChild(ul); ul = null; inBulletList = false; }

    // Empty line -> paragraph break (skip consecutive empties)
    if (line.trim() === "") {
      if (wrapper.lastChild && wrapper.lastChild.tagName !== "BR") {
        wrapper.appendChild(document.createElement("br"));
      }
      continue;
    }

    // Heading
    if (/^#{1,3} /.test(line)) {
      const level = (line.match(/^(#{1,3}) /) || [])[1].length;
      const h = document.createElement("h" + Math.min(level + 2, 6));
      appendInlineMarkdown(h, line.replace(/^#{1,3} /, ""));
      wrapper.appendChild(h);
      continue;
    }

    // Plain paragraph line
    const p = document.createElement("p");
    appendInlineMarkdown(p, line);
    wrapper.appendChild(p);
  }

  if (inBulletList && ul) wrapper.appendChild(ul);
  return wrapper.innerHTML;
}

function appendInlineMarkdown(parent, text) {
  // Handles **bold**, *italic*, `code`, and plain text, in sequence.
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  let lastIndex = 0;
  let match;
  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parent.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
    }
    if (match[2] !== undefined) {
      const b = document.createElement("strong");
      b.textContent = match[2];
      parent.appendChild(b);
    } else if (match[3] !== undefined) {
      const em = document.createElement("em");
      em.textContent = match[3];
      parent.appendChild(em);
    } else if (match[4] !== undefined) {
      const code = document.createElement("code");
      code.textContent = match[4];
      parent.appendChild(code);
    }
    lastIndex = re.lastIndex;
  }
  if (lastIndex < text.length) {
    parent.appendChild(document.createTextNode(text.slice(lastIndex)));
  }
}
