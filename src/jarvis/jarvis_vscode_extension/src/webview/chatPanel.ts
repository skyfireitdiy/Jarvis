import { Terminal } from "@xterm/xterm";
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
const connectionStatus = document.getElementById(
  "connectionStatus",
) as HTMLDivElement | null;
const selectedAgentLabel = document.getElementById(
  "selectedAgentLabel",
) as HTMLSpanElement | null;
const executionStatusHint = document.getElementById(
  "executionStatusHint",
) as HTMLDivElement | null;
const inputTip = document.getElementById("inputTip") as HTMLDivElement | null;
const multiInputRow = document.getElementById(
  "multiInputRow",
) as HTMLDivElement | null;
const singleInputRow = document.getElementById(
  "singleInputRow",
) as HTMLDivElement | null;
const messageInput = document.getElementById(
  "messageInput",
) as HTMLTextAreaElement | null;
const singleMessageInput = document.getElementById(
  "singleMessageInput",
) as HTMLInputElement | null;
const sendButton = document.getElementById(
  "sendButton",
) as HTMLButtonElement | null;
const sendSingleButton = document.getElementById(
  "sendSingleButton",
) as HTMLButtonElement | null;
let currentSelectedAgentId = "";

type ExecutionTerminalEntry = {
  wrapper: HTMLDivElement;
  terminalHost: HTMLDivElement;
  terminal: Terminal;
  fitAddon: FitAddon;
  resizeObserver: ResizeObserver;
  lastBuffer: string;
};

const executionTerminals = new Map<string, ExecutionTerminalEntry>();

function sendTerminalResize(
  executionId: string,
  cols: number,
  rows: number,
): void {
  if (!executionId || cols <= 0 || rows <= 0) {
    return;
  }
  vscode.postMessage({ type: "terminalResize", executionId, cols, rows });
}

function syncExecutionTerminalBuffer(
  entry: ExecutionTerminalEntry,
  nextBuffer: string,
): void {
  if (entry.lastBuffer === nextBuffer) {
    return;
  }
  if (!nextBuffer.startsWith(entry.lastBuffer)) {
    entry.terminal.reset();
    entry.terminal.write(nextBuffer);
    entry.lastBuffer = nextBuffer;
    return;
  }
  const appended = nextBuffer.slice(entry.lastBuffer.length);
  if (appended) {
    entry.terminal.write(appended);
  }
  entry.lastBuffer = nextBuffer;
}

function ensureExecutionTerminal(executionId: string): ExecutionTerminalEntry {
  const existing = executionTerminals.get(executionId);
  if (existing) {
    return existing;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "message execution";

  const header = document.createElement("div");
  header.className = "message-header";
  wrapper.appendChild(header);

  const hint = document.createElement("div");
  hint.className = "execution-hint";
  wrapper.appendChild(hint);

  const terminalHost = document.createElement("div");
  terminalHost.className = "execution-terminal";
  terminalHost.tabIndex = 0;
  wrapper.appendChild(terminalHost);

  const terminal = new Terminal({
    convertEol: false,
    cursorBlink: true,
    fontFamily: "var(--vscode-editor-font-family)",
    fontSize: 13,
    theme: {
      background: "#1e1e1e",
    },
  });
  const fitAddon = new FitAddon();
  terminal.loadAddon(fitAddon);
  terminal.open(terminalHost);

  const focusTerminal = () => {
    terminalHost.focus();
    terminal.focus();
  };

  terminalHost.addEventListener("click", focusTerminal);
  wrapper.addEventListener("click", focusTerminal);

  terminal.onData((data) => {
    vscode.postMessage({ type: "sendTerminalInput", text: data, executionId });
  });

  const resizeObserver = new ResizeObserver(() => {
    fitAddon.fit();
    sendTerminalResize(executionId, terminal.cols, terminal.rows);
  });
  resizeObserver.observe(terminalHost);

  requestAnimationFrame(() => {
    fitAddon.fit();
    sendTerminalResize(executionId, terminal.cols, terminal.rows);
    focusTerminal();
  });

  const entry: ExecutionTerminalEntry = {
    wrapper,
    terminalHost,
    terminal,
    fitAddon,
    resizeObserver,
    lastBuffer: "",
  };
  executionTerminals.set(executionId, entry);
  return entry;
}

function renderExecutionMessage(
  item: ChatMessageItem,
  _agentId: string,
): HTMLDivElement {
  const executionId = String(item.executionId || "").trim();
  const entry = ensureExecutionTerminal(executionId || "default");
  const header = entry.wrapper.querySelector(".message-header");
  if (header instanceof HTMLDivElement) {
    header.textContent = item.text || "执行中";
  }
  const hint = entry.wrapper.querySelector(".execution-hint");
  if (hint instanceof HTMLDivElement) {
    hint.textContent = executionId
      ? `终端会话：${executionId}`
      : "终端会话已建立";
  }
  syncExecutionTerminalBuffer(entry, String(item.executionBuffer || ""));

  const existingFinished = entry.wrapper.querySelector(".execution-finished");
  if (item.finished) {
    if (!existingFinished) {
      const finishedNode = document.createElement("div");
      finishedNode.className = "execution-finished";
      finishedNode.textContent = "执行已结束";
      entry.wrapper.appendChild(finishedNode);
    }
  } else if (existingFinished) {
    existingFinished.remove();
  }

  requestAnimationFrame(() => {
    entry.fitAddon.fit();
    sendTerminalResize(
      executionId || "default",
      entry.terminal.cols,
      entry.terminal.rows,
    );
  });

  return entry.wrapper;
}

function renderMessages(messageList: ChatMessageItem[], agentId: string): void {
  if (!messages) {
    return;
  }
  const nextNodes: HTMLDivElement[] = [];
  (messageList || []).forEach((item) => {
    if (item.variant === "execution") {
      nextNodes.push(renderExecutionMessage(item, agentId));
      return;
    }
    const node = document.createElement("div");
    node.className = "message " + (item.variant || "system");
    node.textContent = item.text || "";
    nextNodes.push(node);
  });

  nextNodes.forEach((node, index) => {
    const currentNode = messages.children.item(index);
    if (currentNode === node) {
      return;
    }
    if (
      node.classList.contains("execution") &&
      node.parentElement === messages &&
      node.previousElementSibling === currentNode
    ) {
      return;
    }
    messages.insertBefore(node, currentNode || null);
  });

  while (messages.children.length > nextNodes.length) {
    const lastChild = messages.lastElementChild;
    if (!lastChild) {
      break;
    }
    if (
      lastChild instanceof HTMLDivElement &&
      lastChild.classList.contains("execution")
    ) {
      messages.removeChild(lastChild);
      continue;
    }
    messages.removeChild(lastChild);
  }

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
    inputTip.textContent =
      tipText || (isSingle ? "当前为单行输入模式" : "当前为多行输入模式");
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

window.addEventListener(
  "message",
  (event: MessageEvent<{ type?: string; payload?: StatePayload }>) => {
    const data = event.data || {};
    if (data.type !== "state") {
      return;
    }
    const payload = data.payload || {};
    currentSelectedAgentId = String(payload.selectedAgentId || "").trim();
    if (selectedAgentLabel) {
      selectedAgentLabel.textContent =
        payload.selectedAgentId || "未选择 Agent";
    }
    if (connectionStatus) {
      connectionStatus.textContent = payload.statusText || "未连接";
      connectionStatus.className = payload.isError ? "status error" : "status";
    }
    if (executionStatusHint) {
      executionStatusHint.textContent =
        "执行状态：" + (payload.executionStatus || "running");
    }
    syncInputMode(payload.inputMode || "multi", payload.inputTip || "");
    renderMessages(payload.messages || [], currentSelectedAgentId);
  },
);
