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

function renderExecutionMessage(
  item: ChatMessageItem,
  _agentId: string,
): HTMLDivElement {
  const wrapper = document.createElement("div");
  wrapper.className = "message execution";

  const header = document.createElement("div");
  header.className = "message-header";
  header.textContent = item.text || "执行中";
  wrapper.appendChild(header);

  const hint = document.createElement("div");
  hint.className = "execution-hint";
  const executionId = String(item.executionId || "").trim();
  hint.textContent = executionId
    ? `真实终端已在 VS Code Terminal 面板中打开（execution: ${executionId}）`
    : "真实终端已在 VS Code Terminal 面板中打开";
  wrapper.appendChild(hint);

  if (item.finished) {
    const finishedNode = document.createElement("div");
    finishedNode.className = "execution-finished";
    finishedNode.textContent = "执行已结束";
    wrapper.appendChild(finishedNode);
  }

  return wrapper;
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
