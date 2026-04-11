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

type CompletionItem = {
  value?: string;
  display?: string;
  description?: string;
  type?: string;
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
const completionButton = document.getElementById(
  "completionButton",
) as HTMLButtonElement | null;
const completeButton = document.getElementById(
  "completeButton",
) as HTMLButtonElement | null;
const manualInterruptButton = document.getElementById(
  "manualInterruptButton",
) as HTMLButtonElement | null;
const runningIndicator = document.getElementById(
  "runningIndicator",
) as HTMLDivElement | null;
const completionModalOverlay = document.getElementById(
  "completionModalOverlay",
) as HTMLDivElement | null;
const closeCompletionModalButton = document.getElementById(
  "closeCompletionModalButton",
) as HTMLButtonElement | null;
const completionSearchInput = document.getElementById(
  "completionSearchInput",
) as HTMLInputElement | null;
const completionList = document.getElementById(
  "completionList",
) as HTMLDivElement | null;
const completionStatus = document.getElementById(
  "completionStatus",
) as HTMLDivElement | null;
const confirmDialog = document.getElementById(
  "confirmDialog",
) as HTMLDivElement | null;
const confirmMessage = document.getElementById(
  "confirmMessage",
) as HTMLParagraphElement | null;
const confirmCancelButton = document.getElementById(
  "confirmCancelButton",
) as HTMLButtonElement | null;
const confirmConfirmButton = document.getElementById(
  "confirmConfirmButton",
) as HTMLButtonElement | null;
let currentSelectedAgentId = "";
let currentConfirmAgentId = "";
let wasRunningIndicatorVisible = false;
let currentExecutionStatus = "running";
let completionCursorPos = -1;
let baseCompletions: CompletionItem[] = [];
let searchedCompletions: CompletionItem[] = [];
let selectedCompletionIndex = -1;

// 输入历史记录相关
const INPUT_HISTORY_STORAGE_KEY = "jarvis_vscode_input_history";
const MAX_INPUT_HISTORY_COUNT = 100;
let inputHistory: string[] = [];
let historyIndex = -1; // 当前浏览的历史记录索引（-1 表示未浏览历史）
let currentTempInput = ""; // 保存当前正在编辑的临时内容

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

function getLanguageFromFilename(filename: string): string {
  if (!filename) return "plaintext";

  const ext = filename.split(".").pop()?.toLowerCase();
  if (!ext) return "plaintext";

  const languageMap: Record<string, string> = {
    js: "javascript",
    jsx: "javascript",
    ts: "typescript",
    tsx: "typescript",
    py: "python",
    java: "java",
    cpp: "cpp",
    c: "c",
    cs: "csharp",
    php: "php",
    rb: "ruby",
    go: "go",
    rs: "rust",
    html: "html",
    css: "css",
    scss: "scss",
    json: "json",
    xml: "xml",
    yaml: "yaml",
    yml: "yaml",
    md: "markdown",
    sql: "sql",
    sh: "bash",
    bash: "bash",
  };

  return languageMap[ext] || "plaintext";
}

function renderSideBySideDiff(diffData: any): string {
  if (!diffData || !diffData.rows) {
    return '<div class="diff-error">No diff data</div>';
  }

  const { file_path, additions, deletions, rows } = diffData;

  // 推断语言类型用于语法高亮
  const language = getLanguageFromFilename(file_path);

  let html = '<div class="diff-side-by-side">';

  // 标题
  html += '<div class="diff-header">';
  html += `<span class="diff-file-path">📝 ${escapeHtml(file_path || "Unknown")}</span>`;
  html += `<span class="diff-stats">[<span class="diff-additions">+${additions}</span> / <span class="diff-deletions">-${deletions}</span>]</span>`;
  html += "</div>";

  // 表格
  html += '<table class="diff-table">';

  rows.forEach((row: any) => {
    const { type, old_line_num, old_line, new_line_num, new_line } = row;

    // 行背景色类
    let rowClass = "diff-row diff-row-" + type;
    html += `<tr class="${rowClass}">`;

    // 旧代码列
    if (type === "equal" || type === "delete" || type === "replace") {
      html += `<td class="diff-line-num diff-old-num">${escapeHtml(String(old_line_num || ""))}</td>`;

      // 统计并保留缩进
      let oldContent = "";
      if (old_line) {
        const leadingSpaces = old_line.match(/^(\s*)/)?.[0] || "";
        // 简化版本：不使用highlight.js，直接转义HTML
        oldContent =
          "&nbsp;".repeat(leadingSpaces.length) + escapeHtml(old_line);
      }

      // 对于 replace 和 delete，添加删除背景色到 td
      const oldClass =
        type === "replace" || type === "delete" ? "diff-deleted" : "";
      html += `<td class="diff-content diff-old-content ${oldClass}"><code>${oldContent}</code></td>`;
    } else {
      html += '<td class="diff-line-num diff-old-num"></td>';
      html += '<td class="diff-content diff-old-content"></td>';
    }

    // 新代码列
    if (type === "equal" || type === "insert" || type === "replace") {
      html += `<td class="diff-line-num diff-new-num">${escapeHtml(String(new_line_num || ""))}</td>`;

      // 统计并保留缩进
      let newContent = "";
      if (new_line) {
        const leadingSpaces = new_line.match(/^(\s*)/)?.[0] || "";
        // 简化版本：不使用highlight.js，直接转义HTML
        newContent =
          "&nbsp;".repeat(leadingSpaces.length) + escapeHtml(new_line);
      }

      // 对于 replace 和 insert，添加新增背景色到 td
      const newClass =
        type === "replace" || type === "insert" ? "diff-added" : "";
      html += `<td class="diff-content diff-new-content ${newClass}"><code>${newContent}</code></td>`;
    } else {
      html += '<td class="diff-line-num diff-new-num"></td>';
      html += '<td class="diff-content diff-new-content"></td>';
    }

    html += "</tr>";
  });

  html += "</table>";
  html += "</div>";

  return html;
}

function renderMessageHtml(item: ChatMessageItem): string {
  const text = String(item.text || "");

  // 检查是否是DIFF类型消息
  if (item.variant === "DIFF") {
    try {
      const diffData = JSON.parse(text);
      if (diffData.diff_type === "side_by_side") {
        return renderSideBySideDiff(diffData);
      }
    } catch (e) {
      console.error("[DIFF] Failed to parse side by side diff:", e);
      return escapeHtml(text);
    }
  }

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

function ensureMessageNode(
  item: ChatMessageItem,
  index: number,
): HTMLDivElement {
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
    fontFamily:
      '"JetBrains Mono", "Cascadia Code", "Fira Code", Consolas, "Courier New", monospace',
    fontSize: 14,
    lineHeight: 1.2,
    fontWeight: "400",
    fontWeightBold: "600",
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
  const defaultPlaceholder = isSingle
    ? "输入单行内容，按回车或 Ctrl+Enter 发送..."
    : "输入消息，按 Ctrl+Enter 发送...";
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

function getActiveInputElement():
  | HTMLInputElement
  | HTMLTextAreaElement
  | null {
  return singleInputRow?.style.display === "flex"
    ? singleMessageInput
    : messageInput;
}

function insertTextAtCursor(textToInsert: string): void {
  const inputElement = getActiveInputElement();
  if (!inputElement) {
    return;
  }
  const start = inputElement.selectionStart ?? inputElement.value.length;
  const end = inputElement.selectionEnd ?? inputElement.value.length;
  const currentValue = inputElement.value;
  const nextValue =
    currentValue.slice(0, start) + textToInsert + currentValue.slice(end);
  inputElement.value = nextValue;
  const nextCursorPosition = start + textToInsert.length;
  inputElement.setSelectionRange(nextCursorPosition, nextCursorPosition);
  inputElement.focus();
}

function getMergedCompletions(): CompletionItem[] {
  const query = String(completionSearchInput?.value || "")
    .trim()
    .toLowerCase();
  if (!query) {
    return baseCompletions;
  }
  const filteredBaseCompletions = baseCompletions.filter((item) => {
    const displayText = String(item.display || "").toLowerCase();
    const descriptionText = String(item.description || "").toLowerCase();
    const valueText = String(item.value || "").toLowerCase();
    return (
      displayText.includes(query) ||
      descriptionText.includes(query) ||
      valueText.includes(query)
    );
  });
  return [...filteredBaseCompletions, ...searchedCompletions];
}

function renderCompletionList(): void {
  if (!completionList) {
    return;
  }
  const items = getMergedCompletions();
  completionList.innerHTML = "";
  if (items.length === 0) {
    const emptyNode = document.createElement("div");
    emptyNode.className = "completion-empty";
    emptyNode.textContent = "没有找到匹配的补全";
    completionList.appendChild(emptyNode);
    return;
  }
  items.forEach((item, index) => {
    const node = document.createElement("div");
    node.className =
      "completion-item" +
      (selectedCompletionIndex === index ? " selected" : "");
    const typeClass = String(item.type || "").trim();
    if (typeClass) {
      node.classList.add(`completion-${typeClass}`);
    }
    const valueNode = document.createElement("div");
    valueNode.className = "completion-value";
    valueNode.textContent = String(item.display || item.value || "");
    node.appendChild(valueNode);
    const descNode = document.createElement("div");
    descNode.className = "completion-desc";
    descNode.textContent = String(item.description || "");
    node.appendChild(descNode);
    node.addEventListener("click", () => {
      insertCompletionItem(item);
    });
    completionList.appendChild(node);
  });
}

function setCompletionStatus(message: string, isError = false): void {
  if (!completionStatus) {
    return;
  }
  const text = String(message || "").trim();
  completionStatus.textContent = text;
  completionStatus.style.display = text ? "block" : "none";
  completionStatus.className = isError
    ? "completion-status error"
    : "completion-status";
}

function openCompletionModal(): void {
  const inputElement = getActiveInputElement();
  completionCursorPos =
    inputElement?.selectionStart ?? inputElement?.value.length ?? -1;
  selectedCompletionIndex = -1;
  searchedCompletions = [];
  setCompletionStatus("正在加载补全...");

  // 清空搜索输入框
  if (completionSearchInput) {
    completionSearchInput.value = "";
  }

  renderCompletionList();
  completionModalOverlay?.classList.add("visible");
  vscode.postMessage({ type: "openCompletions" });
}

function closeCompletionModal(insertAtOnClose = false): void {
  completionModalOverlay?.classList.remove("visible");
  setCompletionStatus("");
  selectedCompletionIndex = -1;
  baseCompletions = [];
  searchedCompletions = [];
  const cursorPos = completionCursorPos;
  completionCursorPos = -1;
  if (insertAtOnClose && cursorPos >= 0) {
    insertTextAtCursor("@");
  }
}

function insertCompletionItem(item: CompletionItem): void {
  const value = String(item.value || "").trim();
  if (!value) {
    return;
  }
  insertTextAtCursor(`'${value}'`);
  closeCompletionModal(false);
}

function moveCompletionSelection(delta: number): void {
  const items = getMergedCompletions();
  if (items.length === 0) {
    return;
  }
  if (selectedCompletionIndex < 0) {
    selectedCompletionIndex = delta > 0 ? 0 : items.length - 1;
  } else {
    selectedCompletionIndex =
      (selectedCompletionIndex + delta + items.length) % items.length;
  }
  renderCompletionList();
  const selectedNode = completionList?.children.item(selectedCompletionIndex);
  if (selectedNode instanceof HTMLDivElement) {
    selectedNode.scrollIntoView({ block: "nearest" });
  }
}

function shouldTriggerCompletionSignalByCtrlC(): boolean {
  if (currentExecutionStatus !== "waiting_multi") {
    return false;
  }
  if (completionModalOverlay?.classList.contains("visible")) {
    return false;
  }
  if (singleInputRow?.style.display === "flex") {
    return false;
  }
  // 检查焦点是否在多行输入框上
  const activeElement = document.activeElement;
  if (activeElement !== messageInput) {
    return false;
  }
  const selectedText = String(window.getSelection?.()?.toString() || "").trim();
  if (selectedText) {
    return false;
  }
  const multiLineText = String(messageInput?.value || "");
  return !multiLineText.trim();
}

// 检查光标是否在第一行
function isCursorAtFirstLine(textarea: HTMLTextAreaElement): boolean {
  const cursorPosition = textarea.selectionStart;
  const textBeforeCursor = textarea.value.substring(0, cursorPosition);
  return !textBeforeCursor.includes("\n");
}

// 检查光标是否在最后一行
function isCursorAtLastLine(textarea: HTMLTextAreaElement): boolean {
  const cursorPosition = textarea.selectionEnd;
  const textAfterCursor = textarea.value.substring(cursorPosition);
  return !textAfterCursor.includes("\n");
}

// 保存输入历史到 localStorage
function saveInputHistoryToStorage(): void {
  try {
    localStorage.setItem(
      INPUT_HISTORY_STORAGE_KEY,
      JSON.stringify(inputHistory),
    );
  } catch {
    // ignore storage errors
  }
}

// 从 localStorage 加载输入历史
function loadInputHistoryFromStorage(): void {
  try {
    const saved = localStorage.getItem(INPUT_HISTORY_STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed)) {
        inputHistory = parsed.filter(
          (item) => typeof item === "string" && item.trim(),
        );
      }
    }
  } catch {
    // ignore storage errors
  }
}

// 添加输入到历史记录
function addToInputHistory(text: string): void {
  const trimmedText = text.trim();
  if (!trimmedText) {
    return;
  }
  // 避免重复添加相同的记录
  if (inputHistory.length > 0 && inputHistory[0] === trimmedText) {
    return;
  }
  inputHistory.unshift(trimmedText);
  // 限制历史记录数量
  if (inputHistory.length > MAX_INPUT_HISTORY_COUNT) {
    inputHistory.pop();
  }
  saveInputHistoryToStorage();
  // 重置历史浏览状态
  historyIndex = -1;
  currentTempInput = "";
}

// 翻阅历史记录
function navigateHistory(direction: "up" | "down"): void {
  if (direction === "up") {
    // 向上翻阅：加载更早的历史记录
    if (historyIndex < inputHistory.length - 1) {
      // 第一次翻阅时，保存当前正在编辑的内容
      if (historyIndex === -1) {
        const activeInput = getActiveInputElement();
        currentTempInput = activeInput ? activeInput.value : "";
      }
      historyIndex++;
      const activeInput = getActiveInputElement();
      if (activeInput) {
        activeInput.value = inputHistory[historyIndex];
      }
    }
  } else if (direction === "down") {
    // 向下翻阅：加载更新的历史记录
    if (historyIndex > -1) {
      historyIndex--;
      const activeInput = getActiveInputElement();
      if (activeInput) {
        if (historyIndex === -1) {
          // 回到最新状态，恢复临时编辑的内容
          activeInput.value = currentTempInput;
        } else {
          activeInput.value = inputHistory[historyIndex];
        }
      }
    }
  }
}

function sendCurrentInput(mode: "single" | "multi"): void {
  const inputEl = mode === "single" ? singleMessageInput : messageInput;
  const text = inputEl ? inputEl.value : "";
  if (text.trim()) {
    addToInputHistory(text);
  }
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

completionButton?.addEventListener("click", () => {
  openCompletionModal();
});

completeButton?.addEventListener("click", () => {
  vscode.postMessage({ type: "sendCompletionSignal" });
});

manualInterruptButton?.addEventListener("click", () => {
  vscode.postMessage({ type: "sendManualInterrupt" });
});

messageInput?.addEventListener("keydown", (event) => {
  if (!event.ctrlKey && !event.metaKey && event.key === "@") {
    event.preventDefault();
    openCompletionModal();
    return;
  }
  if (event.ctrlKey && event.key === "Enter") {
    event.preventDefault();
    const text = messageInput.value;
    if (!text.trim()) {
      return;
    }
    sendCurrentInput("multi");
    return;
  }
  // 向上箭头：检查是否在第一行，是才触发历史
  if (event.key === "ArrowUp") {
    if (isCursorAtFirstLine(messageInput)) {
      event.preventDefault();
      navigateHistory("up");
    }
    return;
  }
  // 向下箭头：检查是否在最后一行，是才触发历史
  if (event.key === "ArrowDown") {
    if (isCursorAtLastLine(messageInput)) {
      event.preventDefault();
      navigateHistory("down");
    }
    return;
  }
});

singleMessageInput?.addEventListener("keydown", (event) => {
  if (!event.ctrlKey && !event.metaKey && event.key === "@") {
    event.preventDefault();
    openCompletionModal();
    return;
  }
  if (event.key === "Enter" && !event.ctrlKey && !event.metaKey) {
    event.preventDefault();
    sendCurrentInput("single");
    return;
  }
  if (event.ctrlKey && event.key === "Enter") {
    event.preventDefault();
    const text = singleMessageInput.value;
    if (!text.trim()) {
      return;
    }
    sendCurrentInput("single");
  }
});

closeCompletionModalButton?.addEventListener("click", () => {
  closeCompletionModal(true);
});

completionModalOverlay?.addEventListener("click", (event) => {
  if (event.target === completionModalOverlay) {
    closeCompletionModal(true);
  }
});

completionSearchInput?.addEventListener("input", () => {
  const query = completionSearchInput.value.trim();
  selectedCompletionIndex = -1;
  if (!query) {
    searchedCompletions = [];
    setCompletionStatus("");
    renderCompletionList();
    return;
  }
  setCompletionStatus("正在搜索补全...");
  renderCompletionList();
  vscode.postMessage({ type: "searchCompletions", query });
});

completionSearchInput?.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    closeCompletionModal(true);
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    moveCompletionSelection(1);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    moveCompletionSelection(-1);
    return;
  }
  if (event.key === "Enter") {
    const items = getMergedCompletions();
    if (
      selectedCompletionIndex >= 0 &&
      selectedCompletionIndex < items.length
    ) {
      event.preventDefault();
      insertCompletionItem(items[selectedCompletionIndex]);
    }
  }
});

document.addEventListener("keydown", (event) => {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "c") {
    return;
  }
  if (!shouldTriggerCompletionSignalByCtrlC()) {
    return;
  }
  event.preventDefault();
  vscode.postMessage({ type: "sendCompletionSignal" });
});

// 确认对话框相关函数
function showConfirmDialog(
  message: string,
  defaultConfirm: boolean,
  agentId: string,
): void {
  currentConfirmAgentId = agentId;
  if (confirmMessage) {
    confirmMessage.textContent = message;
  }
  if (confirmCancelButton && confirmConfirmButton) {
    // 根据默认选项设置按钮样式
    if (defaultConfirm) {
      confirmCancelButton.classList.remove("default");
      confirmConfirmButton.classList.add("default");
    } else {
      confirmCancelButton.classList.add("default");
      confirmConfirmButton.classList.remove("default");
    }
  }
  confirmDialog?.classList.add("visible");
}

function hideConfirmDialog(): void {
  confirmDialog?.classList.remove("visible");
  currentConfirmAgentId = "";
}

function sendConfirmResult(confirmed: boolean): void {
  vscode.postMessage({
    type: "confirmResult",
    confirmed,
    agentId: currentConfirmAgentId,
  });
  hideConfirmDialog();
}

// 确认对话框按钮事件监听
confirmCancelButton?.addEventListener("click", () => {
  sendConfirmResult(false);
});

confirmConfirmButton?.addEventListener("click", () => {
  sendConfirmResult(true);
});

// 确认对话框键盘事件监听（Enter 键触发默认按钮）
confirmDialog?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    // 检查哪个按钮是默认按钮
    const isConfirmDefault =
      confirmConfirmButton?.classList.contains("default");
    sendConfirmResult(isConfirmDefault);
  }
  if (event.key === "Escape") {
    event.preventDefault();
    sendConfirmResult(false);
  }
});

window.addEventListener(
  "message",
  (
    event: MessageEvent<{
      type?: string;
      payload?: StatePayload & {
        items?: CompletionItem[];
        query?: string;
        error?: string;
        message?: string;
        defaultConfirm?: boolean;
        agentId?: string;
      };
    }>,
  ) => {
    const data = event.data || {};
    if (data.type === "showConfirm") {
      const payload = data.payload || {};
      showConfirmDialog(
        String(payload.message || "请确认"),
        payload.defaultConfirm !== false,
        String(payload.agentId || ""),
      );
      return;
    }
    if (data.type === "completionsResult") {
      const payload = data.payload || {};
      baseCompletions = Array.isArray(payload.items) ? payload.items : [];
      searchedCompletions = [];
      selectedCompletionIndex = -1;
      setCompletionStatus(String(payload.error || ""), Boolean(payload.error));
      renderCompletionList();
      completionModalOverlay?.classList.add("visible");
      requestAnimationFrame(() => {
        completionSearchInput?.focus();
      });
      return;
    }
    if (data.type === "completionSearchResult") {
      const payload = data.payload || {};
      const currentQuery = completionSearchInput?.value.trim() || "";
      if (String(payload.query || "") !== currentQuery) {
        return;
      }
      searchedCompletions = Array.isArray(payload.items) ? payload.items : [];
      selectedCompletionIndex = -1;
      setCompletionStatus(String(payload.error || ""), Boolean(payload.error));
      renderCompletionList();
      return;
    }
    if (data.type !== "state") {
      return;
    }
    const payload = data.payload || {};
    currentSelectedAgentId = String(payload.selectedAgentId || "").trim();
    currentExecutionStatus = String(payload.executionStatus || "running");
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
    const isRunningIndicatorVisible = payload.executionStatus === "running";
    if (runningIndicator) {
      runningIndicator.style.display = isRunningIndicatorVisible
        ? "flex"
        : "none";
    }
    const isWaitingMulti = payload.executionStatus === "waiting_multi";
    if (completeButton) {
      completeButton.disabled = !isWaitingMulti;
    }
    if (completionButton) {
      completionButton.disabled = !isWaitingMulti;
    }
    if (manualInterruptButton) {
      manualInterruptButton.style.display =
        payload.executionStatus === "running" ? "inline-flex" : "none";
      manualInterruptButton.disabled = payload.executionStatus !== "running";
    }
    syncInputMode(payload.inputMode || "multi", payload.inputTip || "");
    renderMessages(payload.messages || [], currentSelectedAgentId);
    if (messages && isRunningIndicatorVisible && !wasRunningIndicatorVisible) {
      requestAnimationFrame(() => {
        messages.scrollTop = messages.scrollHeight;
      });
    }
    wasRunningIndicatorVisible = isRunningIndicatorVisible;
  },
);

// 初始化：加载输入历史
loadInputHistoryFromStorage();
