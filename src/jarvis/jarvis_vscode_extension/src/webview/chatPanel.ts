import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { marked } from "marked";
import plantumlEncoder from "plantuml-encoder";
import hljs from "highlight.js";

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

// 渲染缓存：避免对未变化的消息重复调用 renderMessageHtml
const renderHtmlCache = new Map<string, string>();
let prevMessageList: ChatMessageItem[] = [];

// 分页加载相关变量
const MESSAGES_PER_PAGE = 50;
let currentMessages: ChatMessageItem[] = [];
let historyOffset = 0;
let isLoadingHistory = false;
let hasMoreHistory = false;
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

// 缓冲区相关状态
const inputBuffers = new Map<string, string>(); // 每个 Agent 的输入缓冲区
let showBufferPanel = false;
let bufferEditText = "";
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
(markedRenderer as any).code = function (
  code: string,
  language?: string,
  isEscaped?: boolean,
) {
  if (isPlantUmlLanguage(language)) {
    return renderPlantUmlBlock(code);
  }
  return (defaultCodeRenderer as any)(code, language, isEscaped);
};

// 配置 marked 使用 highlight.js 进行语法高亮，并启用 GFM 换行处理
marked.setOptions({
  renderer: markedRenderer,
  highlight: function (code: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value;
      } catch (e) {
        console.error("[highlight.js] Error highlighting code:", e);
      }
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true, // 启用 GFM 换行处理（换行显示为 <br>）
  gfm: true, // 启用 GitHub Flavored Markdown
} as any);

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
  const cacheKey = `${item.variant || ""}|${item.lang || ""}|${text}`;
  const cached = renderHtmlCache.get(cacheKey);
  if (cached !== undefined) {
    return cached;
  }

  let html: string;

  // 检查是否是DIFF类型消息
  if (item.variant === "DIFF") {
    try {
      const diffData = JSON.parse(text);
      if (diffData.diff_type === "side_by_side") {
        html = renderSideBySideDiff(diffData);
      } else {
        html = escapeHtml(text);
      }
    } catch (e) {
      console.error("[DIFF] Failed to parse side by side diff:", e);
      html = escapeHtml(text);
    }
  } else if (item.lang === "markdown") {
    html = marked.parse(text) as string;
  } else if (item.lang === "diff") {
    html = marked.parse(`\`\`\`diff\n${text}\n\`\`\``) as string;
  } else {
    html = escapeHtml(text);
  }

  renderHtmlCache.set(cacheKey, html);
  return html;
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

function showCopySuccess(): void {
  // 创建提示元素
  const notification = document.createElement("div");
  notification.textContent = "已复制";
  notification.style.cssText = `
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: rgba(0, 0, 0, 0.8);
    color: white;
    padding: 8px 16px;
    border-radius: 4px;
    font-size: 14px;
    z-index: 1000;
    opacity: 0;
    transition: opacity 0.3s ease;
  `;

  document.body.appendChild(notification);

  // 显示提示
  requestAnimationFrame(() => {
    notification.style.opacity = "1";
  });

  // 2秒后自动消失
  setTimeout(() => {
    notification.style.opacity = "0";
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 300);
  }, 2000);
}

function copyMessageToClipboard(item: ChatMessageItem): void {
  const text = String(item.text || "");
  if (!text.trim()) {
    return;
  }

  // 使用现代Clipboard API
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        // 显示复制成功提示
        showCopySuccess();
      })
      .catch((err) => {
        console.error("复制失败:", err);
        // 降级方案：使用传统方法
        fallbackCopyToClipboard(text);
      });
  } else {
    fallbackCopyToClipboard(text);
  }
}

function fallbackCopyToClipboard(text: string): void {
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  textArea.style.left = "-999999px";
  textArea.style.top = "-999999px";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();

  try {
    const successful = document.execCommand("copy");
    if (successful) {
      showCopySuccess();
    } else {
      console.error("复制失败");
    }
  } catch (err) {
    console.error("复制失败:", err);
  }

  document.body.removeChild(textArea);
}

function addMessageActions(
  messageNode: HTMLDivElement,
  item: ChatMessageItem,
): void {
  // 检查是否已经添加了操作图标
  if (messageNode.querySelector(".message-actions")) {
    return;
  }

  const actionsContainer = document.createElement("div");
  actionsContainer.className = "message-actions";
  actionsContainer.style.cssText = `
    position: absolute;
    bottom: 8px;
    right: 8px;
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity 0.2s ease;
  `;

  // 复制图标
  const copyButton = document.createElement("button");
  copyButton.innerHTML = "📋";
  copyButton.title = "复制到剪贴板";
  copyButton.style.cssText = `
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
    border-radius: 3px;
    font-size: 14px;
    transition: background-color 0.2s ease;
  `;
  copyButton.addEventListener("click", () => {
    copyMessageToClipboard(item);
  });

  actionsContainer.appendChild(copyButton);

  // 添加悬停效果
  messageNode.style.position = "relative";
  messageNode.addEventListener("mouseenter", () => {
    actionsContainer.style.opacity = "1";
  });
  messageNode.addEventListener("mouseleave", () => {
    actionsContainer.style.opacity = "0";
  });

  messageNode.appendChild(actionsContainer);
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
    // 为现有节点添加操作图标
    addMessageActions(existingNode, item);
    return existingNode;
  }

  const node = document.createElement("div");
  node.className = "message " + (item.variant || "system");
  node.innerHTML = renderMessageHtml(item);
  // 为新节点添加操作图标
  addMessageActions(node, item);
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
    fontSize: 13,
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

  // 如果执行已完成，始终显示静态内容，避免为历史消息创建 xterm
  if (item.finished) {
    const existingEntry = executionTerminals.get(executionId || "default");
    if (existingEntry) {
      existingEntry.terminal.dispose();
      existingEntry.fitAddon.dispose();
      existingEntry.resizeObserver.disconnect();
      executionTerminals.delete(executionId || "default");
    }

    const staticWrapper = document.createElement("div");
    staticWrapper.className = "message execution terminal-history";

    const header = document.createElement("div");
    header.className = "message-header";
    header.textContent = item.text || "执行完成";
    staticWrapper.appendChild(header);

    const hint = document.createElement("div");
    hint.className = "execution-hint";
    hint.textContent = executionId
      ? `终端会话：${executionId}（已完成）`
      : "终端会话已完成";
    staticWrapper.appendChild(hint);

    const content = document.createElement("pre");
    content.className = "terminal-history-content";
    content.textContent = String(item.executionBuffer || "");
    staticWrapper.appendChild(content);

    return staticWrapper;
  }

  // 执行未完成，继续使用 xterm
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

function renderMessages(
  messageList: ChatMessageItem[],
  agentId: string,
  isInitialLoad = false,
): void {
  if (!messages) {
    return;
  }

  // 如果是初始加载，更新当前消息列表
  if (isInitialLoad) {
    currentMessages = messageList || [];
    historyOffset = currentMessages.length;
    hasMoreHistory = historyOffset >= MESSAGES_PER_PAGE;
    console.log(
      "[HISTORY] Initial load:",
      currentMessages.length,
      "messages, hasMore:",
      hasMoreHistory,
    );
  }

  const safeList = messageList || [];
  const shouldAutoScroll = isNearBottom(messages);

  // 增量追加快速路径：如果新列表是旧列表末尾追加，只处理新增消息
  if (
    safeList.length >= prevMessageList.length &&
    prevMessageList.length > 0 &&
    isAppendOnly(prevMessageList, safeList)
  ) {
    const startIndex = prevMessageList.length;
    // 先更新最后一条旧消息（可能是 streaming 内容变化）
    if (startIndex > 0) {
      const lastOldItem = safeList[startIndex - 1];
      if (lastOldItem.variant !== "execution") {
        ensureMessageNode(lastOldItem, startIndex - 1);
      }
    }
    for (let i = startIndex; i < safeList.length; i++) {
      const item = safeList[i];
      const node =
        item.variant === "execution"
          ? renderExecutionMessage(item, agentId)
          : ensureMessageNode(item, i);
      messages.appendChild(node);
    }
    prevMessageList = safeList;
    if (shouldAutoScroll) {
      messages.scrollTop = messages.scrollHeight;
    }
    return;
  }

  // 全量渲染路径（首次加载、切换 agent、历史加载等）
  const nextNodes: HTMLDivElement[] = [];
  safeList.forEach((item, index) => {
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

  prevMessageList = safeList;
  if (shouldAutoScroll) {
    messages.scrollTop = messages.scrollHeight;
  }
}

/** 检查 newList 是否只是在 oldList 末尾追加了消息（前缀完全相同） */
function isAppendOnly(
  oldList: ChatMessageItem[],
  newList: ChatMessageItem[],
): boolean {
  for (let i = 0; i < oldList.length; i++) {
    const o = oldList[i];
    const n = newList[i];
    // 快速引用比较，再逐字段比较
    if (o === n) continue;
    if (
      o.text !== n.text ||
      o.variant !== n.variant ||
      o.lang !== n.lang ||
      o.executionId !== n.executionId
    ) {
      return false;
    }
  }
  return true;
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

  // 单行输入模式：直接发送
  // 多行输入模式：根据执行状态决定是直接发送还是保存到缓冲区
  if (mode === "single" || currentExecutionStatus === "waiting_multi") {
    // 后端正在等待输入，直接发送
    if (text.trim()) {
      addToInputHistory(text);
    }
    vscode.postMessage({ type: "sendMessage", text });
    if (inputEl) {
      inputEl.value = "";
    }
  } else {
    // 后端没有等待输入，保存到缓冲区
    if (!text.trim()) return;
    addToInputHistory(text);
    appendToInputBuffer(currentSelectedAgentId, text);
    if (inputEl) {
      inputEl.value = "";
    }
    // 显示提示消息
    vscode.postMessage({
      type: "bufferAppended",
      text: "✓ 输入已追加到缓冲区，等待后端请求",
    });
  }
}

sendButton?.addEventListener("click", () => {
  // 如果有缓冲区内容且不在等待多行输入状态，发送缓冲区
  if (hasBufferedInput() && currentExecutionStatus !== "waiting_multi") {
    sendBufferedInput();
    return;
  }
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

// 缓冲区指示器和清空按钮
const bufferIndicator = document.getElementById(
  "bufferIndicator",
) as HTMLDivElement | null;
const clearBufferBtn = document.getElementById(
  "clearBufferBtn",
) as HTMLButtonElement | null;

bufferIndicator?.addEventListener("click", () => {
  openBufferPanel();
});

clearBufferBtn?.addEventListener("click", () => {
  clearBuffer();
});

// 处理文件拖放功能
function handleFileDrop(event: DragEvent): void {
  event.preventDefault();
  event.stopPropagation();

  const files = event.dataTransfer?.files;
  if (!files || files.length === 0) {
    return;
  }

  // 在VS Code环境中，文件路径可能通过dataTransfer的items获取
  const items = event.dataTransfer?.items;
  if (items && items.length > 0) {
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) {
          // 在VS Code环境中，文件路径可能通过文件名或其他方式获取
          // 这里我们使用文件名作为路径（在实际使用中可能需要更复杂的逻辑）
          const fileName = file.name;
          const quotedPath = `'${fileName}'`;
          insertTextAtCursor(quotedPath);
          return;
        }
      }
    }
  }

  // 备用方案：如果无法通过items获取，尝试使用第一个文件的name属性
  const fileName = files[0].name;
  if (fileName) {
    const quotedPath = `'${fileName}'`;
    insertTextAtCursor(quotedPath);
  }
}

messageInput?.addEventListener("dragover", (event) => {
  event.preventDefault();
  event.stopPropagation();
  messageInput.style.backgroundColor = "#f0f8ff";
});

messageInput?.addEventListener("dragenter", (event) => {
  event.preventDefault();
  event.stopPropagation();
  messageInput.style.backgroundColor = "#e6f3ff";
});

messageInput?.addEventListener("dragleave", (event) => {
  event.preventDefault();
  event.stopPropagation();
  messageInput.style.backgroundColor = "";
});

messageInput?.addEventListener("drop", handleFileDrop);

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

let searchDebounceTimer: ReturnType<typeof setTimeout> | undefined = undefined;

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
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer);
  }
  searchDebounceTimer = setTimeout(() => {
    vscode.postMessage({ type: "searchCompletions", query });
  }, 300);
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
  // 自动聚焦到默认按钮（延迟确保 DOM 渲染完成）
  requestAnimationFrame(() => {
    if (defaultConfirm && confirmConfirmButton) {
      confirmConfirmButton.focus();
    } else if (!defaultConfirm && confirmCancelButton) {
      confirmCancelButton.focus();
    }
  });
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
    // 根据默认按钮决定结果
    const isDefaultConfirm =
      confirmConfirmButton?.classList.contains("default");
    sendConfirmResult(!!isDefaultConfirm);
  } else if (event.key === "y" || event.key === "Y") {
    event.preventDefault();
    sendConfirmResult(true);
  } else if (event.key === "n" || event.key === "N") {
    event.preventDefault();
    sendConfirmResult(false);
  } else if (event.key === "Escape") {
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
    if (data.type === "historyLoaded") {
      const payload = data.payload || {};
      if (isLoadingHistory && payload.messages && payload.messages.length > 0) {
        handleHistoryLoaded(payload.messages);
      }
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

    // 检查是否是历史消息加载响应
    if (isLoadingHistory && payload.messages && payload.messages.length > 0) {
      handleHistoryLoaded(payload.messages);
    } else {
      // 正常的状态更新
      renderMessages(payload.messages || [], currentSelectedAgentId, true);
    }
    if (messages && isRunningIndicatorVisible && !wasRunningIndicatorVisible) {
      requestAnimationFrame(() => {
        messages.scrollTop = messages.scrollHeight;
      });
    }
    wasRunningIndicatorVisible = isRunningIndicatorVisible;

    // 更新缓冲区 UI
    updateBufferUI();

    // 当状态变为 waiting_multi 时，检查是否有缓冲区内容需要自动发送
    if (isWaitingMulti && hasBufferedInput()) {
      const bufferedText = inputBuffers.get(currentSelectedAgentId) || "";
      // 完成信号只发送给多行输入
      const isCompletionSignal = bufferedText === "__CTRL_C_PRESSED__";
      if (!isCompletionSignal || payload.inputMode === "multi") {
        console.log("[BUFFER] Auto-sending buffered input");
        inputBuffers.delete(currentSelectedAgentId);
        updateBufferUI();
        vscode.postMessage({ type: "sendMessage", text: bufferedText });
      } else {
        // 完成信号不能发送给单行输入，清空缓冲区
        console.log(
          "[BUFFER] Completion signal in buffer but request is single-line, discarding",
        );
        inputBuffers.delete(currentSelectedAgentId);
        updateBufferUI();
      }
    }
  },
);

// 初始化：加载输入历史
loadInputHistoryFromStorage();

// ========== 缓冲区功能 ==========

// 检查当前 Agent 是否有缓冲区内容
function hasBufferedInput(): boolean {
  return currentSelectedAgentId
    ? inputBuffers.has(currentSelectedAgentId)
    : false;
}

// 更新缓冲区内容
function updateInputBuffer(agentId: string, nextValue: string): void {
  inputBuffers.set(agentId, nextValue);
  if (currentSelectedAgentId === agentId) {
    bufferEditText = nextValue;
  }
  updateBufferUI();
}

// 追加内容到缓冲区
function appendToInputBuffer(agentId: string, text: string): void {
  const existingText = inputBuffers.get(agentId) || "";
  const nextValue = existingText ? `${existingText}\n${text}` : text;
  updateInputBuffer(agentId, nextValue);
}

// 清空缓冲区
function clearBuffer(): void {
  if (!currentSelectedAgentId) return;
  inputBuffers.delete(currentSelectedAgentId);
  updateBufferUI();
  // 发送系统消息
  vscode.postMessage({
    type: "bufferCleared",
    text: "🗑️ 缓冲区已清空",
  });
}

// 加载缓冲区内容到输入框
function loadBufferToInput(): void {
  if (!currentSelectedAgentId || !inputBuffers.has(currentSelectedAgentId))
    return;
  const bufferedText = inputBuffers.get(currentSelectedAgentId) || "";
  const inputElement = getActiveInputElement();
  if (inputElement) {
    inputElement.value = bufferedText;
    inputElement.focus();
  }
  closeBufferPanel();
}

// 保存缓冲区编辑
function saveBufferEdit(): void {
  if (!currentSelectedAgentId || !bufferEditText.trim()) return;
  updateInputBuffer(currentSelectedAgentId, bufferEditText.trim());
  closeBufferPanel();
}

// 发送缓冲区内容
function sendBufferedInput(): void {
  if (!currentSelectedAgentId || !inputBuffers.has(currentSelectedAgentId))
    return;
  const bufferedText = inputBuffers.get(currentSelectedAgentId) || "";
  inputBuffers.delete(currentSelectedAgentId);
  updateBufferUI();
  vscode.postMessage({ type: "sendMessage", text: bufferedText });
}

// 打开缓冲区管理面板
function openBufferPanel(): void {
  if (!hasBufferedInput()) return;
  bufferEditText = inputBuffers.get(currentSelectedAgentId) || "";
  showBufferPanel = true;
  renderBufferPanel();
}

// 关闭缓冲区管理面板
function closeBufferPanel(): void {
  showBufferPanel = false;
  renderBufferPanel();
}

// 更新缓冲区 UI 状态
function updateBufferUI(): void {
  const hasBuffer = hasBufferedInput();
  const isNotWaitingMulti = currentExecutionStatus !== "waiting_multi";
  const shouldShowIndicator = hasBuffer && isNotWaitingMulti;

  // 更新缓冲区指示器
  const bufferIndicator = document.getElementById("bufferIndicator");
  if (bufferIndicator) {
    bufferIndicator.style.display = shouldShowIndicator ? "flex" : "none";
  }

  // 更新清空缓冲区按钮
  const clearBufferBtn = document.getElementById("clearBufferBtn");
  if (clearBufferBtn) {
    (clearBufferBtn as HTMLButtonElement).style.display = shouldShowIndicator
      ? "inline-flex"
      : "none";
  }

  // 更新发送按钮文本
  const sendBtn = sendButton || sendSingleButton;
  if (sendBtn) {
    sendBtn.textContent = shouldShowIndicator ? "发送缓冲区" : "发送";
  }
}

// 渲染缓冲区管理面板
function renderBufferPanel(): void {
  let overlay = document.getElementById("bufferPanelOverlay");

  if (!showBufferPanel) {
    if (overlay) {
      overlay.remove();
    }
    return;
  }

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "bufferPanelOverlay";
    overlay.className = "modal-overlay visible";
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeBufferPanel();
    });
    document.body.appendChild(overlay);
  }

  overlay.innerHTML = `
    <div class="modal buffer-modal">
      <div class="buffer-panel-header">
        <span class="buffer-panel-title">📝 输入缓存</span>
        <div class="buffer-panel-actions">
          <button class="buffer-panel-btn" id="loadBufferBtn" title="加载到输入框">↙ 加载</button>
          <button class="buffer-panel-btn" id="clearBufferPanelBtn" title="清空缓存">🗑️</button>
          <button class="buffer-panel-btn close-btn" id="closeBufferPanelBtn" title="关闭面板">✕</button>
        </div>
      </div>
      <div class="buffer-panel-content">
        <textarea id="bufferEditTextarea" class="buffer-edit-textarea" placeholder="缓存内容...">${bufferEditText}</textarea>
        <div class="buffer-panel-footer">
          <button class="buffer-save-btn" id="saveBufferBtn">保存修改 (Ctrl+Enter)</button>
        </div>
      </div>
    </div>
  `;

  // 绑定事件
  document
    .getElementById("loadBufferBtn")
    ?.addEventListener("click", loadBufferToInput);
  document
    .getElementById("clearBufferPanelBtn")
    ?.addEventListener("click", () => {
      clearBuffer();
      closeBufferPanel();
    });
  document
    .getElementById("closeBufferPanelBtn")
    ?.addEventListener("click", closeBufferPanel);
  document
    .getElementById("saveBufferBtn")
    ?.addEventListener("click", saveBufferEdit);

  const textarea = document.getElementById(
    "bufferEditTextarea",
  ) as HTMLTextAreaElement;
  if (textarea) {
    textarea.addEventListener("input", () => {
      bufferEditText = textarea.value;
    });
    textarea.addEventListener("keydown", (e) => {
      if (e.ctrlKey && e.key === "Enter") {
        e.preventDefault();
        saveBufferEdit();
      }
    });
    textarea.focus();
  }
}

/**
 * 检查是否接近滚动区域顶部
 */
function isNearTop(element: HTMLElement): boolean {
  const SCROLL_THRESHOLD = 100;
  return element.scrollTop <= SCROLL_THRESHOLD;
}

/**
 * 加载更多历史消息
 */
function loadMoreHistory(): void {
  if (isLoadingHistory || !hasMoreHistory) {
    return;
  }

  isLoadingHistory = true;
  console.log("[HISTORY] Loading more history, offset:", historyOffset);

  // 请求加载更多历史消息
  vscode.postMessage({
    type: "loadMoreHistory",
    payload: {
      offset: historyOffset,
      limit: MESSAGES_PER_PAGE,
    },
  });
}

/**
 * 处理历史消息加载结果
 */
function handleHistoryLoaded(newMessages: ChatMessageItem[]): void {
  if (newMessages.length === 0) {
    hasMoreHistory = false;
    isLoadingHistory = false;
    console.log("[HISTORY] No more history messages");
    return;
  }

  // 保存当前的滚动位置
  let scrollPosition = 0;
  if (messages) {
    scrollPosition = messages.scrollHeight - messages.scrollTop;
  }

  // 将新消息插入到当前消息列表的开头
  currentMessages = [...newMessages, ...currentMessages];

  // 更新偏移量
  historyOffset += newMessages.length;

  // 重新渲染消息（不是初始加载）
  renderMessages(currentMessages, currentSelectedAgentId, false);

  // 恢复滚动位置
  if (messages) {
    requestAnimationFrame(() => {
      const newScrollHeight = messages.scrollHeight;
      messages.scrollTop = newScrollHeight - scrollPosition;
      console.log("[HISTORY] Scroll position restored");
    });
  }

  isLoadingHistory = false;
  console.log(
    "[HISTORY] Loaded",
    newMessages.length,
    "more messages, total loaded:",
    historyOffset,
  );
}

/**
 * 初始化分页加载
 */
function initPagination(): void {
  if (!messages) {
    return;
  }

  // 添加滚动事件监听
  messages.addEventListener("scroll", () => {
    if (isNearTop(messages) && !isLoadingHistory && hasMoreHistory) {
      console.log("[HISTORY] Scrolled to top, loading more history");
      loadMoreHistory();
    }
  });

  console.log("[HISTORY] Pagination initialized");
}

// 初始化分页加载
initPagination();
