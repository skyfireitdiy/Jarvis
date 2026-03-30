import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { marked } from "marked";
import plantumlEncoder from "plantuml-encoder";

type ChatMessageItem = {
  text?: string;
  variant?: string;
  lang?: string;
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
const PLANTUML_SERVER_URL = "https://www.plantuml.com/plantuml/svg/";
const PLANTUML_BLOCK_LANGUAGE = "plantuml";

function escapeHtml(value: string): string {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isPlantUmlLanguage(language: string | undefined): boolean {
  return (
    String(language || "")
      .trim()
      .toLowerCase() === PLANTUML_BLOCK_LANGUAGE
  );
}

function isPlantUmlComplete(source: string): boolean {
  const trimmedSource = String(source || "")
    .trim()
    .toLowerCase();
  return (
    trimmedSource.includes("@startuml") && trimmedSource.includes("@enduml")
  );
}

function renderPlantUmlBlock(plantUmlSource: string): string {
  const trimmedSource = String(plantUmlSource || "").trim();
  if (!trimmedSource) {
    return '<pre><code class="language-plantuml"></code></pre>';
  }
  if (!isPlantUmlComplete(trimmedSource)) {
    return `<pre><code class="language-plantuml">${escapeHtml(trimmedSource)}</code></pre>`;
  }
  try {
    const escapedSource = escapeHtml(trimmedSource);
    const encodedSource = plantumlEncoder.encode(trimmedSource);
    const plantUmlUrl = `${PLANTUML_SERVER_URL}${encodedSource}`;
    return [
      '<div class="plantuml-block">',
      '  <div class="plantuml-notice">',
      "    当前前端使用 PlantUML 在线服务渲染，若图片加载失败可展开查看源码。",
      "  </div>",
      `  <a class="plantuml-link" href="${plantUmlUrl}" target="_blank" rel="noopener noreferrer">`,
      `    <img class="plantuml-image" src="${plantUmlUrl}" alt="PlantUML diagram" loading="lazy" />`,
      "  </a>",
      '  <details class="plantuml-source">',
      "    <summary>查看 PlantUML 源码</summary>",
      `    <pre><code class="language-plantuml">${escapedSource}</code></pre>`,
      "  </details>",
      "</div>",
    ].join("\n");
  } catch (error) {
    console.error("[PlantUML] Failed to render PlantUML block:", error);
    return `<pre><code class="language-plantuml">${escapeHtml(trimmedSource)}</code></pre>`;
  }
}

const markedRenderer = new marked.Renderer();
const defaultCodeRenderer = markedRenderer.code.bind(markedRenderer);
markedRenderer.code = (token: Parameters<typeof defaultCodeRenderer>[0]) => {
  if (isPlantUmlLanguage(token.lang)) {
    return renderPlantUmlBlock(token.text);
  }
  return defaultCodeRenderer(token);
};
marked.setOptions({ renderer: markedRenderer });

function renderMessageHtml(item: ChatMessageItem): string {
  const text = String(item.text || "");
  if (item.lang === "markdown") {
    return marked.parse(text) as string;
  }
  if (item.lang === "diff") {
    return marked.parse(`\`\`\`diff\n${text}\n\`\`\``) as string;
  }
  return escapeHtml(text);
}

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
  const appended = nextBuffer.startsWith(entry.lastBuffer)
    ? nextBuffer.slice(entry.lastBuffer.length)
    : nextBuffer;
  if (!appended) {
    entry.lastBuffer = nextBuffer;
    return;
  }
  entry.terminal.write(appended);
  entry.lastBuffer = nextBuffer;
}

function isNearBottom(container: HTMLDivElement, threshold = 24): boolean {
  const distanceToBottom =
    container.scrollHeight - container.scrollTop - container.clientHeight;
  return distanceToBottom <= threshold;
}

function ensureMessageNode(item: ChatMessageItem, index: number): HTMLDivElement {
  if (!messages) {
    const fallbackNode = document.createElement("div");
    fallbackNode.className = "message " + (item.variant || "system");
    fallbackNode.innerHTML = renderMessageHtml(item);
    return fallbackNode;
  }

  const existingNode = messages.children.item(index);
  if (
    existingNode instanceof HTMLDivElement &&
    !existingNode.classList.contains("execution")
  ) {
    const nextClassName = "message " + (item.variant || "system");
    const nextHtml = renderMessageHtml(item);
    if (existingNode.className !== nextClassName) {
      existingNode.className = nextClassName;
    }
    if (existingNode.innerHTML !== nextHtml) {
      existingNode.innerHTML = nextHtml;
    }
    return existingNode;
  }

  const node = document.createElement("div");
  node.className = "message " + (item.variant || "system");
  node.innerHTML = renderMessageHtml(item);
  return node;
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

  terminal.onData((data: string) => {
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
  const shouldAutoScroll = isNearBottom(messages);
  const nextNodes: HTMLDivElement[] = [];
  (messageList || []).forEach((item, index) => {
    if (item.variant === "execution") {
      nextNodes.push(renderExecutionMessage(item, agentId));
      return;
    }
    nextNodes.push(ensureMessageNode(item, index));
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

  if (shouldAutoScroll) {
    messages.scrollTop = messages.scrollHeight;
  }
}

function syncInputMode(mode: "single" | "multi", tipText: string): void {
  const isSingle = mode === "single";
  if (singleInputRow) {
    singleInputRow.style.display = isSingle ? "flex" : "none";
  }
  if (multiInputRow) {
    multiInputRow.style.display = isSingle ? "none" : "block";
  }
  // 将 tip 显示到输入框的 placeholder
	const defaultPlaceholder = isSingle ? "输入单行内容..." : "输入消息...";
	const placeholder = tipText || defaultPlaceholder;
	if (singleMessageInput) {
		singleMessageInput.placeholder = placeholder;
	}
	if (messageInput) {
		messageInput.placeholder = placeholder;
	}
	// 隐藏 inputTip 元素的文本显示
	if (inputTip) {
		inputTip.textContent = "";
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
