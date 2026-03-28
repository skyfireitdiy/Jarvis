import { Terminal } from "xterm";
import { FitAddon } from "@xterm/addon-fit";

type ChatMessageItem = {
  text?: string;
  variant?: string;
  executionId?: string;
  executionBuffer?: string;
  finished?: boolean;
};

type StatePayload = {
  selectedAgentId?: string;
  statusText?: string;
  isError?: boolean;
  executionStatus?: string;
  inputMode?: "single" | "multi";
  inputTip?: string;
  messages?: ChatMessageItem[];
};

declare function acquireVsCodeApi(): {
  postMessage(message: unknown): void;
};

const vscode = acquireVsCodeApi();
const messages = document.getElementById("messages") as HTMLDivElement | null;
const connectionStatus = document.getElementById("connectionStatus") as HTMLDivElement | null;
const selectedAgentLabel = document.getElementById("selectedAgentLabel") as HTMLSpanElement | null;
const executionStatusHint = document.getElementById("executionStatusHint") as HTMLDivElement | null;
const inputTip = document.getElementById("inputTip") as HTMLDivElement | null;
const multiInputRow = document.getElementById("multiInputRow") as HTMLDivElement | null;
const singleInputRow = document.getElementById("singleInputRow") as HTMLDivElement | null;
const messageInput = document.getElementById("messageInput") as HTMLTextAreaElement | null;
const singleMessageInput = document.getElementById("singleMessageInput") as HTMLInputElement | null;
const sendButton = document.getElementById("sendButton") as HTMLButtonElement | null;
const sendSingleButton = document.getElementById("sendSingleButton") as HTMLButtonElement | null;

type TerminalEntry = {
  terminal: Terminal;
  fitAddon: { fit: () => void };
  resizeObserver?: ResizeObserver;
  host?: HTMLDivElement;
  lastBuffer: string;
  finished: boolean;
};

const terminalRegistry = new Map<string, TerminalEntry>();
let currentSelectedAgentId = "";

function getTerminalRegistryKey(agentId: string, executionId: string): string {
  return `${agentId}::${executionId}`;
}

function ensureTerminalEntry(agentId: string, executionId: string): TerminalEntry {
  const registryKey = getTerminalRegistryKey(agentId, executionId);
  const existing = terminalRegistry.get(registryKey);
  if (existing) {
    return existing;
  }
  const terminal = new Terminal({
    theme: { background: "#111111" },
    fontSize: 12,
    convertEol: false,
  });
  const fitAddon = new FitAddon();
  terminal.loadAddon(fitAddon);
  const entry: TerminalEntry = {
    terminal,
    fitAddon,
    lastBuffer: "",
    finished: false,
  };
  terminal.onData((data) => {
    if (entry.finished) {
      return;
    }
    vscode.postMessage({
      type: "sendTerminalInput",
      text: data,
      executionId,
    });
  });
  terminalRegistry.set(registryKey, entry);
  return entry;
}

function syncTerminalSize(executionId: string, entry: TerminalEntry): void {
  if (!entry.host) {
    return;
  }
  const oldCols = entry.terminal.cols;
  const oldRows = entry.terminal.rows;
  entry.fitAddon.fit();
  const newCols = entry.terminal.cols;
  const newRows = entry.terminal.rows;
  if (oldCols === newCols && oldRows === newRows) {
    return;
  }
  vscode.postMessage({
    type: "terminalResize",
    executionId,
    cols: newCols,
    rows: newRows,
  });
}

function mountTerminal(
  host: HTMLDivElement,
  item: ChatMessageItem,
  agentId: string,
): void {
  const executionId = String(item.executionId || "").trim();
  if (!executionId) {
    host.textContent = item.executionBuffer || "";
    return;
  }
  const entry = ensureTerminalEntry(agentId, executionId);
  entry.finished = Boolean(item.finished);
  if (entry.host !== host) {
    entry.host = host;
    entry.terminal.open(host);
    if (entry.resizeObserver) {
      entry.resizeObserver.disconnect();
    }
    if (typeof ResizeObserver !== "undefined") {
      entry.resizeObserver = new ResizeObserver(() => {
        syncTerminalSize(executionId, entry);
      });
      entry.resizeObserver.observe(host);
    }
  }
  const nextBuffer = String(item.executionBuffer || "");
  if (nextBuffer !== entry.lastBuffer) {
    entry.terminal.reset();
    if (nextBuffer) {
      entry.terminal.write(nextBuffer);
    }
    entry.lastBuffer = nextBuffer;
  }
  requestAnimationFrame(() => {
    syncTerminalSize(executionId, entry);
  });
}

function renderMessages(messageList: ChatMessageItem[], agentId: string): void {
  if (!messages) {
    return;
  }
  messages.innerHTML = "";
  (messageList || []).forEach((item) => {
    const node = document.createElement("div");
    node.className = "message " + (item.variant || "system");
    if (item.variant === "execution") {
      const header = document.createElement("div");
      header.className = "message-header";
      header.textContent = item.text || "执行中";
      node.appendChild(header);

      const terminalHost = document.createElement("div");
      terminalHost.className = "execution-terminal";
      node.appendChild(terminalHost);
      mountTerminal(terminalHost, item, agentId);

      if (item.finished) {
        const finishedNode = document.createElement("div");
        finishedNode.className = "execution-finished";
        finishedNode.textContent = "执行已结束";
        node.appendChild(finishedNode);
      }
    } else {
      node.textContent = item.text || "";
    }
    messages.appendChild(node);
  });
  messages.scrollTop = messages.scrollHeight;
}

function syncInputMode(mode: "single" | "multi", tipText: string): void {
  const isSingle = mode === "single";
  if (singleInputRow) {
    singleInputRow.style.display = isSingle ? "flex" : "none";
  }
  if (multiInputRow) {
    multiInputRow.style.display = isSingle ? "none" : "block";
  }
  if (inputTip) {
    inputTip.textContent = tipText || (isSingle ? "当前为单行输入模式" : "当前为多行输入模式");
  }
}

function sendCurrentInput(mode: "single" | "multi"): void {
  const inputEl = mode === "single" ? singleMessageInput : messageInput;
  const text = inputEl ? inputEl.value : "";
  vscode.postMessage({ type: "sendMessage", text });
  if (inputEl) {
    inputEl.value = "";
  }
}

sendButton?.addEventListener("click", () => {
  const text = messageInput ? messageInput.value : "";
  if (!text.trim()) {
    return;
  }
  sendCurrentInput("multi");
});

sendSingleButton?.addEventListener("click", () => {
  sendCurrentInput("single");
});

messageInput?.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.key === "Enter") {
    event.preventDefault();
    const text = messageInput.value;
    if (!text.trim()) {
      return;
    }
    sendCurrentInput("multi");
  }
});

singleMessageInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendCurrentInput("single");
  }
});

window.addEventListener("message", (event: MessageEvent<{ type?: string; payload?: StatePayload }>) => {
  const data = event.data || {};
  if (data.type !== "state") {
    return;
  }
  const payload = data.payload || {};
  currentSelectedAgentId = String(payload.selectedAgentId || "").trim();
  if (selectedAgentLabel) {
    selectedAgentLabel.textContent = payload.selectedAgentId || "未选择 Agent";
  }
  if (connectionStatus) {
    connectionStatus.textContent = payload.statusText || "未连接";
    connectionStatus.className = payload.isError ? "status error" : "status";
  }
  if (executionStatusHint) {
    executionStatusHint.textContent = "执行状态：" + (payload.executionStatus || "running");
  }
  syncInputMode(payload.inputMode || "multi", payload.inputTip || "");
  renderMessages(payload.messages || [], currentSelectedAgentId);
});
