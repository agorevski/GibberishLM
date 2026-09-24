"use strict";

const transcript = document.getElementById("transcript");
const promptEl = document.getElementById("prompt");
const sendBtn = document.getElementById("send");

let busy = false;

function scrollToBottom() {
  transcript.scrollTop = transcript.scrollHeight;
}

function autoGrow() {
  promptEl.style.height = "auto";
  promptEl.style.height = Math.min(promptEl.scrollHeight, 160) + "px";
}
promptEl.addEventListener("input", autoGrow);

const THINKING_LABELS = {
  thinking: "Thinking",
};

function makeTurn() {
  const turn = document.createElement("div");
  turn.className = "turn";
  transcript.appendChild(turn);
  return turn;
}

function addUserMessage(turn, text) {
  const wrap = document.createElement("div");
  wrap.className = "user-msg";
  const sigil = document.createElement("span");
  sigil.className = "sigil";
  sigil.textContent = ">";
  const body = document.createElement("div");
  body.className = "text";
  body.textContent = text;
  wrap.append(sigil, body);
  turn.appendChild(wrap);
}

// Renders one streaming session driven by SSE events.
function runSession(turn, prompt) {
  return new Promise((resolve) => {
    let statusEl = null;
    let currentBlock = null;       // active thinking/text block element
    let currentBody = null;        // text node container within block
    let currentTool = null;        // active tool card element

    function setStatus(label) {
      if (!label || label === "Done") {
        if (statusEl) { statusEl.remove(); statusEl = null; }
        return;
      }
      if (!statusEl) {
        statusEl = document.createElement("div");
        statusEl.className = "status";
        statusEl.innerHTML = '<span class="spinner"></span><span class="lbl"></span>';
        turn.appendChild(statusEl);
      }
      statusEl.querySelector(".lbl").textContent = label + "…";
      scrollToBottom();
    }

    function startBlock(type) {
      currentBlock = document.createElement("div");
      currentBlock.className = "block " + type + " cursor";
      if (type === "thinking") {
        const label = document.createElement("span");
        label.className = "label";
        label.textContent = THINKING_LABELS[type] || type;
        currentBlock.appendChild(label);
      }
      currentBody = document.createElement("span");
      currentBody.className = "body";
      currentBlock.appendChild(currentBody);
      // Insert blocks before the status line so the spinner stays at the bottom.
      if (statusEl) turn.insertBefore(currentBlock, statusEl);
      else turn.appendChild(currentBlock);
    }

    function endBlock() {
      if (currentBlock) currentBlock.classList.remove("cursor");
      currentBlock = null;
      currentBody = null;
    }

    function addToolCall(command) {
      currentTool = document.createElement("div");
      currentTool.className = "tool";
      const head = document.createElement("div");
      head.className = "tool-head";
      head.innerHTML = '<span class="badge">bash</span><span>Running command</span>';
      const cmd = document.createElement("div");
      cmd.className = "tool-cmd";
      cmd.textContent = command;
      const out = document.createElement("div");
      out.className = "tool-out";
      currentTool.append(head, cmd, out);
      if (statusEl) turn.insertBefore(currentTool, statusEl);
      else turn.appendChild(currentTool);
      scrollToBottom();
    }

    const source = new SSEStream("/api/stream", { prompt });

    source.on("status", (d) => setStatus(d.label));

    source.on("tool_call", (d) => addToolCall(d.command));

    source.on("block_start", (d) => {
      if (d.type === "tool_result") return; // handled inline on the tool card
      startBlock(d.type);
    });

    source.on("delta", (d) => {
      if (d.type === "tool_result") {
        if (currentTool) {
          currentTool.querySelector(".tool-out").textContent += d.text;
        }
      } else if (currentBody) {
        currentBody.textContent += d.text;
      }
      scrollToBottom();
    });

    source.on("block_end", (d) => {
      if (d.type === "tool_result") { currentTool = null; return; }
      endBlock();
    });

    source.on("done", () => {
      setStatus(null);
      endBlock();
      source.close();
      resolve();
    });

    source.on("error", () => {
      setStatus(null);
      endBlock();
      const err = document.createElement("div");
      err.className = "block text";
      err.style.color = "#ff7b72";
      err.textContent = "[gibberish] stream interrupted.";
      turn.appendChild(err);
      source.close();
      resolve();
    });
  });
}

// Minimal POST-based SSE client (EventSource only supports GET).
class SSEStream {
  constructor(url, body) {
    this.handlers = {};
    this.controller = new AbortController();
    this._start(url, body);
  }
  on(event, fn) { this.handlers[event] = fn; return this; }
  _emit(event, data) { if (this.handlers[event]) this.handlers[event](data); }
  close() { this.controller.abort(); }

  async _start(url, body) {
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: this.controller.signal,
      });
      if (!resp.ok || !resp.body) throw new Error("bad response");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          this._dispatch(raw);
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") this._emit("error", e);
    }
  }

  _dispatch(raw) {
    let event = "message";
    let data = "";
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    let parsed = {};
    try { parsed = data ? JSON.parse(data) : {}; } catch (_) {}
    this._emit(event, parsed);
  }
}

async function submit() {
  if (busy) return;
  const text = promptEl.value.trim();
  if (!text) return;

  busy = true;
  sendBtn.disabled = true;
  promptEl.value = "";
  autoGrow();

  const turn = makeTurn();
  addUserMessage(turn, text);
  scrollToBottom();

  await runSession(turn, text);

  busy = false;
  sendBtn.disabled = false;
  promptEl.focus();
}

sendBtn.addEventListener("click", submit);
promptEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submit();
  }
});
