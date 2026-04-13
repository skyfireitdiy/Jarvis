import * as vscode from "vscode";
import WebSocket, { RawData } from "ws";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";

// 节流函数：在指定时间间隔内最多执行一次
function throttle<T extends Function>(func: T, delay: number): T {
  let lastCall = 0;
  let timeoutId: NodeJS.Timeout | null = null;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function (this: unknown, ...args: any[]) {
    const now = Date.now();
    const remaining = delay - (now - lastCall);

    if (remaining <= 0) {
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
      lastCall = now;
      return (func as Function).apply(this, args);
    } else if (!timeoutId) {
      timeoutId = setTimeout(() => {
        lastCall = Date.now();
        timeoutId = null;
        (func as Function).apply(this, args);
      }, remaining);
    }
  } as unknown as T;
}

// 防抖函数：在指定时间间隔内多次调用只执行最后一次
function debounce<T extends Function>(func: T, delay: number): T {
  let timeoutId: NodeJS.Timeout | null = null;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function (this: unknown, ...args: any[]) {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    timeoutId = setTimeout(() => {
      timeoutId = null;
      (func as Function).apply(this, args);
    }, delay);
  } as unknown as T;
}

interface AgentListItem {
  id: string;
  name?: string;
  displayName: string;
  statusText: string;
  statusClass: "running" | "waiting_multi" | "waiting_single" | "stopped";
  agentType: "agent" | "codeagent";
  workingDir: string;
  llmGroup: string;
  worktree: boolean;
  nodeId: string;
  quickMode?: boolean;
}

interface GatewayAddress {
  host: string;
  port: string;
}

interface ChatMessageItem {
  text: string;
  variant: "system" | "error" | "output" | "stream" | "execution" | "DIFF";
  lang?: "markdown" | "diff" | "text";
  streamId?: string;
  executionId?: string;
  executionBuffer?: string;
  finished?: boolean;
}

interface AgentStatus {
  connection_status: "connected" | "disconnected" | "connecting" | "error";
  execution_status: "running" | "waiting_single" | "waiting_multi" | "stopped";
  input_mode: "single" | "multi";
  input_tip: string;
  terminal_output: string;
  connection_status_text: string;
  has_connection_error: boolean;
  messages: ChatMessageItem[];
  pending_request_id?: string;
  pending_stream_text: string;
  active_streaming_message_id?: string;
  active_execution_id?: string;
  execution_buffers: Record<string, string>;
  last_execution_id?: string;
  last_buffer: string;
  closed: boolean;
}

interface ExecutionTerminalSession {
  agentId: string;
  executionId: string;
  lastBuffer: string;
  closed: boolean;
}

interface IndependentTerminalSession {
  terminalId: string;
  nodeId: string;
  interpreter: string;
  workingDir: string;
  vscodeTerminal: vscode.Terminal | undefined;
  pty: vscode.Pseudoterminal | undefined;
  writeEmitter: vscode.EventEmitter<string> | undefined;
  closed: boolean;
}

interface ChatPanelState {
  gatewayUrl: string;
  password: string;
  token: string;
  selectedAgentId?: string;
  gatewaySocket?: WebSocket;
  gatewayConnectionStatusText: string;
  gatewayHasConnectionError: boolean;
  connectionLockEnabled: boolean;
  restartNodeId?: string;
  restartFrontendService?: boolean;
  isRestartingService?: boolean;
}

interface CompletionItem {
  value?: string;
  display?: string;
  description?: string;
  type?: string;
}

interface RemoteDirectoryItem {
  name: string;
  path: string;
  type: string;
}

// 文件树节点
interface FileTreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  expanded?: boolean;
  loaded?: boolean;
  children?: FileTreeNode[];
}

interface RemoteDirectoryBrowserState {
  isVisible: boolean;
  currentPath: string;
  selectedPath: string;
  selectedIndex: number;
  searchText: string;
  items: RemoteDirectoryItem[];
  isLoading: boolean;
  errorMessage: string;
}

interface CreateAgentFormState {
  isVisible: boolean;
  agentType: "agent" | "codeagent";
  workingDir: string;
  name: string;
  llmGroup: string;
  nodeId: string;
  useWorktree: boolean;
  quickMode: boolean;
  isSubmitting: boolean;
  errorMessage: string;
}

interface NodeOptionItem {
  nodeId: string;
  status?: string;
}

interface LeftViewLoginState {
  errorMessage: string;
  isSubmitting: boolean;
}

interface ModelGroupItem {
  name: string;
  smartModel: string;
  normalModel: string;
  cheapModel: string;
}

interface AgentListViewMessage {
  type?: string;
  agentId?: string;
  agentType?: string;
  gatewayUrl?: string;
  password?: string;
  workingDir?: string;
  name?: string;
  llmGroup?: string;
  nodeId?: string;
  useWorktree?: boolean;
  quickMode?: boolean;
  enabled?: boolean;
  path?: string;
  searchText?: string;
  key?: string;
  nodePath?: string;
  filePath?: string;
}

interface SavedConnectionInfo {
  gatewayUrl?: string;
  connectionLockEnabled?: boolean;
}

interface PersistedChatMessageItem {
  text: string;
  variant: "system" | "error" | "output" | "execution" | "DIFF";
  lang?: "markdown" | "diff" | "text";
  executionId?: string;
  executionBuffer?: string;
  finished?: boolean;
}

const SAVED_CONNECTION_INFO_KEY = "jarvis.savedConnectionInfo";
const AGENT_CHAT_HISTORY_KEY = "jarvis.agentChatHistory";
const MAX_PERSISTED_MESSAGES_PER_AGENT = 1000;
const MAX_PERSISTED_EXECUTION_BUFFER_LENGTH = 50000;
const AGENT_CONNECTION_MAX_RETRIES = 12;
const AGENT_CONNECTION_RETRY_DELAY_MS = 2000;
const AGENT_CONNECTION_TIMEOUT_MS = 10000;
const AGENT_LIST_REFRESH_INTERVAL_MS = 3000;

class JarvisAgentListViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "jarvis.agentListView";

  private currentPanel: vscode.WebviewPanel | undefined;
  private agentItems: AgentListItem[] = [
    {
      id: "default-agent",
      name: "default-agent",
      displayName: "default-agent",
      statusText: "示例 Agent（MVP 占位）",
      statusClass: "running",
      agentType: "agent",
      workingDir: "~",
      llmGroup: "",
      worktree: false,
      nodeId: "master",
    },
  ];
  private currentView: vscode.WebviewView | undefined;
  private readonly panelState: ChatPanelState = {
    gatewayUrl: "127.0.0.1:8000",
    password: "",
    token: "",
    selectedAgentId: undefined,
    gatewaySocket: undefined,
    gatewayConnectionStatusText: "未连接",
    gatewayHasConnectionError: false,
    connectionLockEnabled: false,
  };
  private readonly agentStatuses = new Map<string, AgentStatus>();
  private readonly agentSockets = new Map<string, WebSocket>();
  private readonly agentConnectionAttempts = new Map<string, Promise<void>>();
  private agentListRefreshTimer: NodeJS.Timeout | undefined;
  private readonly executionTerminalSessions = new Map<
    string,
    ExecutionTerminalSession
  >();
  private readonly independentTerminalSessions = new Map<
    string,
    IndependentTerminalSession
  >();
  // 文件树状态：agentId -> FileTreeNode[]
  private readonly fileTreeState = new Map<string, FileTreeNode[]>();
  // 文件树展开状态：agentId -> Set<expandedPaths>
  private readonly fileTreeExpanded = new Map<string, Set<string>>();
  // 远端文件编辑：本地临时文件路径 -> { agentId, remotePath, nodeId, mtimeNs, fileSize, readOnly }
  private readonly remoteFileEditors = new Map<
    string,
    {
      agentId: string;
      remotePath: string;
      nodeId: string;
      mtimeNs?: number;
      fileSize?: number;
      readOnly: boolean;
    }
  >();
  // 远端文件心跳检查定时器
  private remoteFileHeartbeatTimer: NodeJS.Timeout | undefined;
  // 远端文件只读状态栏
  private readOnlyStatusBarItem: vscode.StatusBarItem | undefined;
  private readonly createAgentFormState: CreateAgentFormState = {
    isVisible: false,
    agentType: "agent",
    workingDir: "~",
    name: "通用Agent",
    llmGroup: "default",
    nodeId: "",
    useWorktree: false,
    quickMode: false,
    isSubmitting: false,
    errorMessage: "",
  };
  private readonly leftViewLoginState: LeftViewLoginState = {
    errorMessage: "",
    isSubmitting: false,
  };
  private readonly remoteDirectoryBrowserState: RemoteDirectoryBrowserState = {
    isVisible: false,
    currentPath: "~",
    selectedPath: "~",
    selectedIndex: -1,
    searchText: "",
    items: [],
    isLoading: false,
    errorMessage: "",
  };
  private modelGroups: ModelGroupItem[] = [];
  private availableNodeOptions: NodeOptionItem[] = [];
  private defaultLlmGroup = "";
  private lastAgentItemsJson: string = "";
  private isSettingsPanelVisible = false;
  // 重启服务状态
  private restartNodeId = ""; // 空字符串表示本节点(master)
  private restartFrontendService = false;
  private isRestartingService = false;
  // 批量选择状态
  private selectedAgents = new Set<string>();
  private isBatchMode = false;

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly globalState: vscode.Memento,
  ) {
    this.restoreSavedConnectionInfo();
  }

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.currentView = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
    };

    webviewView.webview.html = this.getAgentListHtml();

    webviewView.webview.onDidReceiveMessage(
      async (message: AgentListViewMessage) => {
        if (message?.type === "openAgent") {
          await this.openChatPanel(message.agentId);
          return;
        }
        if (message?.type === "connect") {
          await this.connectFromLeftView(message);
          return;
        }
        if (message?.type === "toggleCreateAgentForm") {
          this.toggleCreateAgentForm();
          return;
        }
        if (message?.type === "toggleSettingsPanel") {
          this.isSettingsPanelVisible = !this.isSettingsPanelVisible;
          this.renderAgentListView();
          return;
        }
        if (message?.type === "pickWorkingDirectory") {
          await this.pickWorkingDirectory();
          return;
        }
        if (message?.type === "browseRemoteDirectory") {
          await this.loadRemoteDirectories(message.path);
          return;
        }
        if (message?.type === "browseRemoteDirectoryParent") {
          await this.loadRemoteDirectories(this.getParentDirectoryPath());
          return;
        }
        if (message?.type === "selectRemoteDirectory") {
          this.selectRemoteDirectory(message.path);
          return;
        }
        if (message?.type === "updateRemoteDirectorySearch") {
          this.updateRemoteDirectorySearch(message.searchText);
          return;
        }
        if (message?.type === "handleRemoteDirectoryKeydown") {
          await this.handleRemoteDirectoryKeydown(message.key);
          return;
        }
        if (message?.type === "confirmRemoteDirectory") {
          this.confirmRemoteDirectorySelection();
          return;
        }
        if (message?.type === "cancelRemoteDirectory") {
          this.closeRemoteDirectoryBrowser();
          return;
        }
        if (message?.type === "changeNodeId") {
          const newNodeId = String(message.nodeId || "").trim();
          this.createAgentFormState.nodeId = newNodeId;
          try {
            await this.loadModelGroups(newNodeId || undefined);
          } catch {
            // keep current model groups on failure
          }
          this.renderAgentListView();
          return;
        }
        if (message?.type === "changeAgentType") {
          const agentType = String(message.agentType || "agent").trim();
          this.updateCreateAgentDefaults(agentType as "agent" | "codeagent");
          this.renderAgentListView();
          return;
        }
        if (message?.type === "cancelCreateAgent") {
          this.resetCreateAgentForm();
          this.renderAgentListView();
          return;
        }
        if (message?.type === "createAgent") {
          await this.createAgent(message);
          return;
        }
        if (message?.type === "copyAgent") {
          await this.copyAgent(message.agentId);
          return;
        }
        if (message?.type === "deleteAgent") {
          await this.deleteAgent(message.agentId);
          return;
        }
        // 批量操作消息处理
        if (message?.type === "toggleBatchMode") {
          this.toggleBatchMode();
          return;
        }
        if (message?.type === "toggleSelectAgent") {
          this.toggleSelectAgent(message.agentId || "");
          return;
        }
        if (message?.type === "toggleSelectAll") {
          this.toggleSelectAll();
          return;
        }
        if (message?.type === "batchCopyAgents") {
          await this.batchCopyAgents();
          return;
        }
        if (message?.type === "batchDeleteAgents") {
          await this.batchDeleteAgents();
          return;
        }
        if (message?.type === "createTerminal") {
          await this.createTerminalForAgent(message.agentId);
          return;
        }
        if (message?.type === "toggleFileTree") {
          await this.handleToggleFileTree(
            message.agentId || "",
            message.workingDir || "",
            message.nodeId,
          );
          return;
        }
        if (message?.type === "toggleFileTreeNode") {
          await this.handleToggleFileTreeNode(
            message.agentId || "",
            message.nodePath || "",
          );
          return;
        }
        if (message?.type === "openRemoteFile") {
          await this.handleOpenRemoteFile(
            message.agentId || "",
            message.filePath || "",
          );
          return;
        }
        if (message?.type === "toggleConnectionLock") {
          await this.setConnectionLockEnabled(Boolean(message.enabled));
          return;
        }
        if (message?.type === "updateRestartNodeId") {
          this.panelState.restartNodeId = String(message.nodeId || "");
          this.renderAgentListView();
          return;
        }
        if (message?.type === "updateRestartFrontend") {
          this.panelState.restartFrontendService = Boolean(message.enabled);
          return;
        }
        if (message?.type === "restartNodeService") {
          await this.restartNodeService();
          return;
        }
      },
    );
  }

  async openChatPanel(agentId?: string): Promise<void> {
    if (agentId) {
      this.panelState.selectedAgentId = agentId;
      // 切换Agent时重置输入模式为多行
      const agentState = this.getAgentState(agentId);
      agentState.input_mode = "multi";
    }

    if (!this.currentPanel) {
      this.currentPanel = vscode.window.createWebviewPanel(
        "jarvis.chatPanel",
        this.getChatPanelTitle(),
        { viewColumn: vscode.ViewColumn.Three, preserveFocus: false },
        {
          enableScripts: true,
          retainContextWhenHidden: true,
        },
      );

      this.currentPanel.webview.onDidReceiveMessage(
        async (message: ChatPanelMessage) => {
          await this.handleChatPanelMessage(message);
        },
      );

      this.currentPanel.onDidDispose(() => {
        this.currentPanel = undefined;
      });
    }

    this.currentPanel.title = this.getChatPanelTitle();
    this.currentPanel.webview.html = this.getChatPanelHtml(
      this.panelState.selectedAgentId,
    );
    // 延迟发送状态，确保WebView加载完成
    setTimeout(() => {
      this.postPanelState();
    }, 100);
    await this.currentPanel.reveal(vscode.ViewColumn.Beside, false);
  }

  private getAgentListHtml(): string {
    const nonce = createNonce();
    if (!this.panelState.token) {
      return this.getLeftLoginHtml(nonce);
    }

    const createButtonLabel = this.createAgentFormState.isVisible
      ? "收起创建"
      : "创建 Agent";
    const createButtonDisabled = this.createAgentFormState.isSubmitting
      ? "disabled"
      : "";
    const submitButtonDisabled = this.createAgentFormState.isSubmitting
      ? "disabled"
      : "";
    const worktreeChecked = this.createAgentFormState.useWorktree
      ? "checked"
      : "";
    const quickModeChecked = this.createAgentFormState.quickMode
      ? "checked"
      : "";
    const worktreeDisabled =
      this.createAgentFormState.agentType === "codeagent" ? "" : "disabled";
    const createAgentErrorMarkup = this.createAgentFormState.errorMessage
      ? `<div class="form-error">${escapeHtml(this.createAgentFormState.errorMessage)}</div>`
      : "";
    const llmGroupSelectOptions = this.modelGroups
      .map((group) => {
        const selected =
          group.name === this.createAgentFormState.llmGroup ? "selected" : "";
        return `<option value="${escapeHtml(group.name)}" ${selected}>${escapeHtml(group.name)}</option>`;
      })
      .join("");
    const llmGroupFieldMarkup =
      this.modelGroups.length > 0
        ? `
    <div class="form-group">
      <label for="llmGroup">模型组</label>
      <select id="llmGroup">${llmGroupSelectOptions}</select>
    </div>`
        : `
    <div class="form-group">
      <label for="llmGroup">模型组</label>
      <input id="llmGroup" value="${escapeHtml(this.createAgentFormState.llmGroup)}" placeholder="${escapeHtml(this.defaultLlmGroup || "请输入模型组")}" />
    </div>`;
    const nodeSelectOptions = [`<option value="">默认主节点（master）</option>`]
      .concat(
        this.availableNodeOptions.map((node) => {
          const selected =
            node.nodeId === this.createAgentFormState.nodeId ? "selected" : "";
          const label = node.status
            ? `${node.nodeId} (${node.status})`
            : node.nodeId;
          return `<option value="${escapeHtml(node.nodeId)}" ${selected}>${escapeHtml(label)}</option>`;
        }),
      )
      .join("");
    const nodeFieldMarkup = `
    <div class="form-group">
      <label for="nodeId">目标节点</label>
      <select id="nodeId">${nodeSelectOptions}</select>
    </div>`;
    const remoteDirectoryErrorMarkup = this.remoteDirectoryBrowserState
      .errorMessage
      ? `<div class="form-error">${escapeHtml(this.remoteDirectoryBrowserState.errorMessage)}</div>`
      : "";
    const remoteDirectorySearchText =
      this.remoteDirectoryBrowserState.searchText.toLowerCase().trim();
    const filteredRemoteDirectoryItems = remoteDirectorySearchText
      ? this.remoteDirectoryBrowserState.items.filter(
          (item) =>
            item.name.toLowerCase().includes(remoteDirectorySearchText) ||
            item.path.toLowerCase().includes(remoteDirectorySearchText),
        )
      : this.remoteDirectoryBrowserState.items;
    const remoteDirectorySelectedIndex =
      this.remoteDirectoryBrowserState.selectedIndex >= 0 &&
      this.remoteDirectoryBrowserState.selectedIndex <
        filteredRemoteDirectoryItems.length
        ? this.remoteDirectoryBrowserState.selectedIndex
        : -1;
    const remoteDirectoryItemsMarkup = filteredRemoteDirectoryItems
      .map(
        (item, index) => `
      <li class="remote-directory-item ${item.path === this.remoteDirectoryBrowserState.selectedPath || index === remoteDirectorySelectedIndex ? "selected" : ""}" data-remote-directory-path="${escapeHtml(item.path)}">
        <div class="remote-directory-name">📁 ${escapeHtml(item.name || item.path)}</div>
        <div class="remote-directory-path">${escapeHtml(item.path)}</div>
      </li>`,
      )
      .join("");
    const remoteDirectoryEmptyMarkup =
      !this.remoteDirectoryBrowserState.isLoading &&
      !this.remoteDirectoryBrowserState.errorMessage &&
      filteredRemoteDirectoryItems.length === 0
        ? `<div class="remote-directory-empty">${this.remoteDirectoryBrowserState.searchText.trim() ? "没有匹配的目录" : "该目录下没有子目录"}</div>`
        : "";
    const remoteDirectoryBrowserMarkup = this.remoteDirectoryBrowserState
      .isVisible
      ? `
  <div class="remote-directory-browser">
    <div class="remote-directory-header">
      <strong>选择远端工作目录</strong>
      <div class="remote-directory-actions-inline">
        <button id="refreshRemoteDirectoryButton" type="button" ${createButtonDisabled}>刷新</button>
        <button id="goParentRemoteDirectoryButton" type="button" ${createButtonDisabled}>上一级</button>
      </div>
    </div>
    <div class="remote-directory-current-path">${escapeHtml(this.remoteDirectoryBrowserState.currentPath)}</div>
    <div class="form-group">
      <input id="remoteDirectorySearchInput" value="${escapeHtml(this.remoteDirectoryBrowserState.searchText)}" placeholder="🔍 搜索目录..." />
    </div>
    ${remoteDirectoryErrorMarkup}
    <ul class="remote-directory-list">${remoteDirectoryItemsMarkup}</ul>
    ${this.remoteDirectoryBrowserState.isLoading ? '<div class="remote-directory-empty">目录加载中...</div>' : remoteDirectoryEmptyMarkup}
    <div class="form-actions">
      <button id="cancelRemoteDirectoryButton" type="button" ${createButtonDisabled}>取消</button>
      <button id="confirmRemoteDirectoryButton" type="button" ${createButtonDisabled}>确认</button>
    </div>
  </div>`
      : "";
    const createAgentFormMarkup = this.createAgentFormState.isVisible
      ? `
  <div class="create-agent-panel">
    <div class="panel-section-title create-agent-title">创建 Agent</div>
    ${nodeFieldMarkup}
    <div class="form-group">
      <label for="agentType">Agent 类型</label>
      <select id="agentType">
        <option value="agent" ${this.createAgentFormState.agentType === "agent" ? "selected" : ""}>agent</option>
        <option value="codeagent" ${this.createAgentFormState.agentType === "codeagent" ? "selected" : ""}>codeagent</option>
      </select>
    </div>
    <div class="form-group">
      <label for="workingDir">工作目录</label>
      <div class="path-row">
        <input id="workingDir" value="${escapeHtml(this.createAgentFormState.workingDir)}" placeholder="请输入远端工作目录，例如：~/workspace" />
        <button id="pickWorkingDirButton" type="button" ${createButtonDisabled}>选择目录</button>
      </div>
    </div>
    ${remoteDirectoryBrowserMarkup}
    <div class="form-group">
      <label for="agentName">名称</label>
      <input id="agentName" value="${escapeHtml(this.createAgentFormState.name)}" placeholder="通用Agent" />
    </div>
    ${llmGroupFieldMarkup}
    <label class="checkbox-row">
      <input id="useWorktree" type="checkbox" ${worktreeChecked} ${worktreeDisabled} />
      <span>codeagent 使用 worktree</span>
    </label>
    <label class="checkbox-row">
      <input id="useQuickMode" type="checkbox" ${quickModeChecked} />
      <span>极速模式</span>
    </label>
    ${createAgentErrorMarkup}
    <div class="form-actions">
      <button id="cancelCreateAgentButton" type="button" ${createButtonDisabled}>取消</button>
      <button id="submitCreateAgentButton" type="button" ${submitButtonDisabled}>${this.createAgentFormState.isSubmitting ? "创建中..." : "创建"}</button>
    </div>
  </div>`
      : "";
    const agentListMarkup = this.agentItems
      .map((agentItem) => {
        const hasFileTree = this.fileTreeState.has(agentItem.id);
        const fileTreeHtml = hasFileTree
          ? this.generateFileTreeHtml(agentItem.id)
          : '<div class="file-tree-empty">点击 📂 加载文件树</div>';
        const fileTreeExpanded =
          hasFileTree &&
          (this.fileTreeState.get(agentItem.id)?.length || 0) > 0;
        const isSelected = this.selectedAgents.has(agentItem.id);
        const batchModeClass = this.isBatchMode ? "batch-mode" : "";
        const selectedClass = isSelected ? "selected" : "";
        const checkboxMarkup = this.isBatchMode
          ? `<input type="checkbox" class="agent-checkbox" data-select-agent-id="${agentItem.id}" ${isSelected ? "checked" : ""} />`
          : "";
        return `
    <li data-agent-id="${agentItem.id}" class="agent-item ${agentItem.statusClass} ${batchModeClass} ${selectedClass}">
      <div class="agent-row">
        ${checkboxMarkup}
        <div class="agent-main">
          <div class="agent-title-row">
            <div class="agent-name">${escapeHtml(agentItem.displayName)}</div>
            <div class="agent-status-dot ${agentItem.statusClass}" title="${escapeHtml(agentItem.statusText)}"></div>
            ${agentItem.llmGroup ? `<div class="agent-llm-group" title="模型组">🔹 ${escapeHtml(agentItem.llmGroup)}</div>` : ""}
            ${agentItem.nodeId ? `<div class="agent-llm-group" title="节点">🧭 ${escapeHtml(agentItem.nodeId)}</div>` : ""}
            ${agentItem.worktree ? '<div class="agent-worktree" title="已启用 worktree">🌿</div>' : ""}
            ${agentItem.quickMode ? '<div class="agent-quick-mode" title="极速模式">⚡</div>' : ""}
          </div>
          <div class="agent-dir">${escapeHtml(agentItem.workingDir || "未提供工作目录")}</div>
        </div>
        <div class="agent-actions">
          <button class="icon-button" type="button" data-filetree-agent-id="${agentItem.id}" data-working-dir="${escapeHtml(agentItem.workingDir || "")}" data-node-id="${escapeHtml(agentItem.nodeId || "")}" title="文件树">📂</button>
          <button class="icon-button" type="button" data-terminal-agent-id="${agentItem.id}" title="创建终端">💻</button>
          <button class="icon-button" type="button" data-copy-agent-id="${agentItem.id}" title="复制 Agent">📋</button>
          <button class="icon-button" type="button" data-delete-agent-id="${agentItem.id}" title="删除 Agent">🗑</button>
        </div>
      </div>
      <div class="file-tree-container ${fileTreeExpanded ? "expanded" : ""}" data-agent-id="${agentItem.id}">
        <div class="file-tree-content">
          ${fileTreeHtml}
        </div>
      </div>
    </li>`;
      })
      .join("");
    const batchToolbarMarkup = this.isBatchMode
      ? `
  <div class="batch-toolbar">
    <span class="batch-toolbar-info">已选择 ${this.selectedAgents.size} 个</span>
    <div class="batch-toolbar-actions">
      <button id="toggleSelectAllButton">${this.isAllSelected() ? "取消全选" : "全选"}</button>
      <button id="batchCopyButton" class="batch-copy-btn" ${this.selectedAgents.size === 0 ? "disabled" : ""}>批量复制</button>
      <button id="batchDeleteButton" class="batch-delete-btn" ${this.selectedAgents.size === 0 ? "disabled" : ""}>批量删除</button>
      <button id="exitBatchModeButton">退出</button>
    </div>
  </div>`
      : "";
    const agentListSectionMarkup = `
  <div class="agents-list-panel">
    <div class="panel-section-title agents-list-title">Agents 列表</div>
    ${batchToolbarMarkup}
    <ul>${agentListMarkup}</ul>
  </div>`;
    const connectionStatusClass = this.panelState.gatewayHasConnectionError
      ? "status-banner error"
      : "status-banner";
    const connectionLockChecked = this.panelState.connectionLockEnabled
      ? "checked"
      : "";
    const settingsButtonLabel = this.isSettingsPanelVisible
      ? "关闭设置"
      : "设置";
    const settingsPanelMarkup = this.isSettingsPanelVisible
      ? `
  <div class="settings-panel">
    <div class="settings-panel-header">
      <div>
        <div class="settings-panel-title">设置</div>
        <div class="settings-panel-subtitle">连接设置和服务管理功能。</div>
      </div>
      <button id="closeSettingsPanelButton" type="button">关闭</button>
    </div>
    <div class="settings-card">
      <div class="settings-card-title">连接设置</div>
      <label class="toggle-switch-row" for="connectionLockToggle">
        <input id="connectionLockToggle" type="checkbox" ${connectionLockChecked} />
        <div class="toggle-switch-text">
          <span class="toggle-switch-label">锁定连接（拒绝新连接）</span>
          <span class="toggle-switch-help">启用后，当已有活跃连接时，新连接将被拒绝；禁用后，新连接会替换旧连接。</span>
        </div>
      </label>
    </div>
    <div class="settings-card">
      <div class="settings-card-title">服务管理</div>
      <div class="restart-service-form">
        <div class="form-group">
          <label>重启节点服务</label>
          <select id="restartNodeSelect">
            <option value="">本节点 (master)</option>
            ${this.availableNodeOptions.map((node) => `<option value="${escapeHtml(node.nodeId)}" ${this.panelState.restartNodeId === node.nodeId ? "selected" : ""}>${escapeHtml(node.nodeId)}${node.status ? ` (${escapeHtml(node.status)})` : ""}</option>`).join("")}
          </select>
          <span class="form-help">选择要重启服务的节点，默认为本节点</span>
        </div>
        <div class="form-group" ${this.panelState.restartNodeId && this.panelState.restartNodeId !== "master" ? 'style="display:none"' : ""}>
          <label class="checkbox-label">
            <input type="checkbox" id="restartFrontendCheckbox" ${this.panelState.restartFrontendService ? "checked" : ""} />
            <span>同时重启前端服务</span>
          </label>
          <span class="form-help">前端服务重启时间较长，通常只需重启后端</span>
        </div>
        <button id="restartNodeServiceButton" type="button" ${this.panelState.isRestartingService ? "disabled" : ""}>
          ${this.panelState.isRestartingService ? "请稍候..." : this.panelState.restartNodeId ? `重启节点 ${escapeHtml(this.panelState.restartNodeId)} 服务` : "重启本节点服务"}
        </button>
      </div>
    </div>
    <div class="settings-card">
      <div class="settings-card-title">连接管理</div>
      <div class="settings-card-row">
        <span class="settings-card-help">断开当前连接并清空认证信息，用于切换网关服务器</span>
        <button id="disconnectButton" type="button" class="settings-action-button" style="background-color: #dc2626;">
          断开连接
        </button>
      </div>
    </div>
  </div>`
      : "";

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Jarvis Agents</title>
  <style>
    body { font-family: var(--vscode-font-family); padding: 12px; color: var(--vscode-foreground); }
    .toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 12px; }
    .toolbar-actions { display: flex; gap: 8px; }
    .settings-panel { border: 1px solid rgba(59, 130, 246, 0.35); border-radius: 10px; padding: 12px; margin-bottom: 12px; background: rgba(59, 130, 246, 0.08); display: flex; flex-direction: column; gap: 12px; box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.08); }
    .settings-panel-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
    .settings-panel-title { font-size: 13px; font-weight: 700; margin-bottom: 4px; color: #93c5fd; }
    .settings-panel-subtitle { font-size: 12px; opacity: 0.75; line-height: 1.45; }
    .settings-card { border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 10px 12px; background: var(--vscode-editor-background); }
    .settings-card-title { font-size: 12px; font-weight: 600; margin-bottom: 8px; opacity: 0.9; }
    .settings-card-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .settings-card-help { font-size: 12px; opacity: 0.75; line-height: 1.45; }
    .restart-service-form { display: flex; flex-direction: column; gap: 10px; }
    .restart-service-form .form-group { display: flex; flex-direction: column; gap: 4px; }
    .restart-service-form label { font-size: 12px; font-weight: 600; }
    .restart-service-form .form-help { font-size: 11px; opacity: 0.7; }
    .restart-service-form .checkbox-label { display: flex; align-items: center; gap: 6px; font-weight: normal; cursor: pointer; }
    .restart-service-form .checkbox-label input { width: auto; margin: 0; }
    .settings-action-button { width: 100%; justify-content: center; font-weight: 600; }
    .toggle-switch-row { display: flex; align-items: center; gap: 10px; }
    .toggle-switch-row input { width: auto; margin: 0; }
    .toggle-switch-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
    .toggle-switch-label { font-size: 12px; font-weight: 600; }
    .toggle-switch-help { font-size: 12px; opacity: 0.75; line-height: 1.4; }
    button, select, input { border: 1px solid var(--vscode-input-border, var(--vscode-panel-border)); border-radius: 4px; }
    button { background: var(--vscode-button-background); color: var(--vscode-button-foreground); padding: 6px 10px; cursor: pointer; }
    input, select { width: 100%; padding: 6px 8px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); box-sizing: border-box; }
    ul { list-style: none; padding: 0; margin: 0; }
    li { border: 1px solid var(--vscode-panel-border); border-radius: 6px; margin-bottom: 8px; padding: 8px; cursor: pointer; }
    .agent-item.running { background: rgba(76, 175, 80, 0.12); }
    .agent-item.waiting_multi { background: rgba(255, 193, 7, 0.12); }
    .agent-item.waiting_single { background: rgba(255, 152, 0, 0.12); }
    .agent-item.stopped { background: rgba(158, 158, 158, 0.12); }
    .agent-row { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
    .agent-main { min-width: 0; flex: 1; }
    .agent-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .agent-name { font-weight: 600; }
    .agent-status { font-size: 12px; padding: 2px 8px; border-radius: 999px; border: 1px solid transparent; }
    .agent-status.running { background: rgba(76, 175, 80, 0.18); color: #2e7d32; border-color: rgba(76, 175, 80, 0.28); }
    .agent-status.waiting_multi { background: rgba(255, 193, 7, 0.18); color: #8a6d00; border-color: rgba(255, 193, 7, 0.28); }
    .agent-status.waiting_single { background: rgba(255, 152, 0, 0.18); color: #a85d00; border-color: rgba(255, 152, 0, 0.28); }
    .agent-status.stopped { background: rgba(158, 158, 158, 0.18); color: #666; border-color: rgba(158, 158, 158, 0.28); }
    .agent-status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-left: 8px; flex-shrink: 0; }
    .agent-status-dot.running { background: #4caf50; box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.2); }
    .agent-status-dot.waiting_multi { background: #ffc107; box-shadow: 0 0 0 2px rgba(255, 193, 7, 0.2); }
    .agent-status-dot.waiting_single { background: #ff9800; box-shadow: 0 0 0 2px rgba(255, 152, 0, 0.2); }
    .agent-status-dot.stopped { background: #f44336; box-shadow: 0 0 0 2px rgba(244, 67, 54, 0.2); }
    .agent-llm-group { font-size: 12px; opacity: 0.9; }
    .agent-worktree { font-size: 13px; }
    .agent-dir { opacity: 0.8; font-size: 12px; margin-top: 6px; word-break: break-all; }
    .agent-actions { display: flex; gap: 6px; }
    .icon-button { padding: 4px 6px; min-width: auto; }
    .file-tree-container { max-height: 0; overflow: hidden; transition: max-height 0.2s ease-out; border-top: none; margin-top: 0; }
    .file-tree-container.expanded { max-height: 300px; overflow-y: auto; border-top: 1px solid var(--vscode-panel-border); margin-top: 8px; padding-top: 8px; }
    .file-tree-content { font-size: 12px; }
    .file-tree-empty { padding: 8px; opacity: 0.6; font-size: 12px; }
    .file-tree-node { display: flex; align-items: center; padding: 3px 4px; cursor: pointer; border-radius: 3px; }
    .file-tree-node:hover { background: var(--vscode-list-hoverBackground, rgba(255,255,255,0.06)); }
    .expand-arrow { width: 16px; font-size: 10px; opacity: 0.7; flex-shrink: 0; }
    .expand-arrow-placeholder { width: 16px; flex-shrink: 0; }
    .file-icon { margin-right: 4px; }
    .file-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .create-agent-panel { border: 1px solid rgba(34, 197, 94, 0.35); border-radius: 10px; padding: 10px; margin-bottom: 12px; background: rgba(34, 197, 94, 0.07); box-shadow: inset 0 0 0 1px rgba(34, 197, 94, 0.08); }
    .panel-section-title { font-size: 13px; font-weight: 700; margin-bottom: 10px; letter-spacing: 0.01em; }
    .create-agent-title { color: #86efac; }
    .agents-list-panel { border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 10px; padding: 10px; margin-top: 12px; background: rgba(168, 85, 247, 0.06); box-shadow: inset 0 0 0 1px rgba(168, 85, 247, 0.08); }
    .agents-list-title { color: #d8b4fe; }
    .form-group { margin-bottom: 10px; }
    .form-group label { display: block; font-size: 12px; margin-bottom: 4px; opacity: 0.9; }
    .path-row { display: flex; gap: 8px; align-items: center; }
    .path-row input { flex: 1; }
    .path-row button { white-space: nowrap; }
    .remote-directory-browser { margin-bottom: 10px; border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 10px; background: var(--vscode-editor-background); }
    .remote-directory-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; }
    .remote-directory-actions-inline { display: flex; gap: 8px; }
    .remote-directory-current-path { font-size: 12px; opacity: 0.8; margin-bottom: 8px; word-break: break-all; }
    .remote-directory-list { max-height: 220px; overflow: auto; border: 1px solid var(--vscode-panel-border); border-radius: 6px; }
    .remote-directory-item { padding: 8px 10px; border-bottom: 1px solid rgba(127, 127, 127, 0.12); cursor: pointer; }
    .remote-directory-item:last-child { border-bottom: none; }
    .remote-directory-item.selected, .remote-directory-item:hover { background: var(--vscode-list-hoverBackground, rgba(255,255,255,0.06)); }
    .remote-directory-name { font-size: 12px; font-weight: 600; }
    .remote-directory-path { font-size: 11px; opacity: 0.75; margin-top: 2px; word-break: break-all; }
    .remote-directory-empty { padding: 10px 0; font-size: 12px; opacity: 0.75; }
    .checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 12px; }
    .checkbox-row input { width: auto; }
    .form-actions { display: flex; justify-content: flex-end; gap: 8px; }
    .form-error { color: var(--vscode-errorForeground); font-size: 12px; margin-bottom: 10px; }
    .status-banner { margin-bottom: 12px; padding: 8px 10px; border: 1px solid var(--vscode-panel-border); border-radius: 6px; font-size: 12px; opacity: 0.9; }
    .status-banner.error { color: var(--vscode-errorForeground); border-color: var(--vscode-errorForeground); }
    /* 批量选择样式 */
    .batch-mode-btn { min-width: auto; padding: 6px 8px; }
    .batch-mode-btn.active { background: rgba(59, 130, 246, 0.2); border-color: rgba(59, 130, 246, 0.5); }
    .batch-toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 10px; margin-bottom: 12px; border: 1px solid rgba(59, 130, 246, 0.35); border-radius: 6px; background: rgba(59, 130, 246, 0.08); flex-wrap: wrap; }
    .batch-toolbar-info { font-size: 12px; font-weight: 600; color: #60a5fa; }
    .batch-toolbar-actions { display: flex; gap: 6px; margin-left: auto; }
    .batch-toolbar button { padding: 4px 10px; font-size: 12px; }
    .batch-toolbar .batch-delete-btn { background: rgba(239, 68, 68, 0.15); color: #f87171; border-color: rgba(239, 68, 68, 0.3); }
    .batch-toolbar .batch-copy-btn { background: rgba(34, 197, 94, 0.15); color: #4ade80; border-color: rgba(34, 197, 94, 0.3); }
    .agent-checkbox { width: 16px; height: 16px; margin-right: 8px; cursor: pointer; flex-shrink: 0; }
    .agent-item.batch-mode { cursor: default; }
    .agent-item.batch-mode .agent-row { cursor: pointer; }
    .agent-item.selected { background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.4); }
  </style>
</head>
<body>
  <div class="toolbar">
    <strong>Agents</strong>
    <div class="toolbar-actions">
      <button id="toggleBatchModeButton" class="batch-mode-btn ${this.isBatchMode ? "active" : ""}" title="批量选择">☑</button>
      <button id="toggleSettingsPanelButton">${settingsButtonLabel}</button>
      <button id="toggleCreateAgentButton" ${createButtonDisabled}>${createButtonLabel}</button>
    </div>
  </div>
  ${settingsPanelMarkup}
  <div class="${connectionStatusClass}">当前连接状态：${escapeHtml(this.panelState.gatewayConnectionStatusText)}</div>
  ${createAgentFormMarkup}
  ${agentListSectionMarkup}
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const toggleSettingsPanelButton = document.getElementById('toggleSettingsPanelButton');
    if (toggleSettingsPanelButton) {
      toggleSettingsPanelButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'toggleSettingsPanel' });
      });
    }
    const closeSettingsPanelButton = document.getElementById('closeSettingsPanelButton');
    if (closeSettingsPanelButton) {
      closeSettingsPanelButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'toggleSettingsPanel' });
      });
    }
    const toggleCreateAgentButton = document.getElementById('toggleCreateAgentButton');
    if (toggleCreateAgentButton) {
      toggleCreateAgentButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'toggleCreateAgentForm' });
      });
    }
    const connectionLockToggle = document.getElementById('connectionLockToggle');
    if (connectionLockToggle) {
      connectionLockToggle.addEventListener('change', () => {
        vscode.postMessage({ type: 'toggleConnectionLock', enabled: Boolean(connectionLockToggle.checked) });
      });
    }
    const restartNodeSelect = document.getElementById('restartNodeSelect');
    if (restartNodeSelect) {
      restartNodeSelect.addEventListener('change', () => {
        vscode.postMessage({ type: 'updateRestartNodeId', nodeId: restartNodeSelect.value });
      });
    }
    const restartFrontendCheckbox = document.getElementById('restartFrontendCheckbox');
    if (restartFrontendCheckbox) {
      restartFrontendCheckbox.addEventListener('change', () => {
        vscode.postMessage({ type: 'updateRestartFrontend', enabled: restartFrontendCheckbox.checked });
      });
    }
    const restartNodeServiceButton = document.getElementById('restartNodeServiceButton');
    if (restartNodeServiceButton) {
      restartNodeServiceButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'restartNodeService' });
      });
    }
    const disconnectButton = document.getElementById('disconnectButton');
    if (disconnectButton) {
      disconnectButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'disconnect' });
      });
    }
    const pickWorkingDirButton = document.getElementById('pickWorkingDirButton');
    if (pickWorkingDirButton) {
      pickWorkingDirButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'pickWorkingDirectory' });
      });
    }
    const refreshRemoteDirectoryButton = document.getElementById('refreshRemoteDirectoryButton');
    if (refreshRemoteDirectoryButton) {
      refreshRemoteDirectoryButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'browseRemoteDirectory' });
      });
    }
    const goParentRemoteDirectoryButton = document.getElementById('goParentRemoteDirectoryButton');
    if (goParentRemoteDirectoryButton) {
      goParentRemoteDirectoryButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'browseRemoteDirectoryParent' });
      });
    }
    const cancelRemoteDirectoryButton = document.getElementById('cancelRemoteDirectoryButton');
    if (cancelRemoteDirectoryButton) {
      cancelRemoteDirectoryButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'cancelRemoteDirectory' });
      });
    }
    const confirmRemoteDirectoryButton = document.getElementById('confirmRemoteDirectoryButton');
    if (confirmRemoteDirectoryButton) {
      confirmRemoteDirectoryButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'confirmRemoteDirectory' });
      });
    }
    const remoteDirectorySearchInput = document.getElementById('remoteDirectorySearchInput');
    if (remoteDirectorySearchInput) {
      let searchDebounceTimer = undefined;
      remoteDirectorySearchInput.addEventListener('input', () => {
        if (searchDebounceTimer) {
          clearTimeout(searchDebounceTimer);
        }
        searchDebounceTimer = setTimeout(() => {
          vscode.postMessage({ type: 'updateRemoteDirectorySearch', searchText: remoteDirectorySearchInput.value });
        }, 300);
      });
      remoteDirectorySearchInput.addEventListener('keydown', (event) => {
        const supportedKeys = ['ArrowDown', 'ArrowUp', 'Enter', 'Escape'];
        if (!supportedKeys.includes(event.key)) {
          return;
        }
        event.preventDefault();
        vscode.postMessage({ type: 'handleRemoteDirectoryKeydown', key: event.key });
      });
    }
    document.querySelectorAll('[data-remote-directory-path]').forEach((item) => {
      item.addEventListener('click', () => {
        const path = item.getAttribute('data-remote-directory-path');
        vscode.postMessage({ type: 'selectRemoteDirectory', path });
        vscode.postMessage({ type: 'browseRemoteDirectory', path });
      });
    });
    const nodeIdSelect = document.getElementById('nodeId');
    if (nodeIdSelect) {
      nodeIdSelect.addEventListener('change', () => {
        vscode.postMessage({ type: 'changeNodeId', nodeId: nodeIdSelect.value });
      });
    }
    const agentTypeSelect = document.getElementById('agentType');
    if (agentTypeSelect) {
      agentTypeSelect.addEventListener('change', () => {
        vscode.postMessage({ type: 'changeAgentType', agentType: agentTypeSelect.value });
      });
    }
    const submitCreateAgentButton = document.getElementById('submitCreateAgentButton');
    if (submitCreateAgentButton) {
      submitCreateAgentButton.addEventListener('click', () => {
        const agentType = document.getElementById('agentType');
        const workingDir = document.getElementById('workingDir');
        const agentName = document.getElementById('agentName');
        const llmGroup = document.getElementById('llmGroup');
        const nodeId = document.getElementById('nodeId');
        const useWorktree = document.getElementById('useWorktree');
        const useQuickMode = document.getElementById('useQuickMode');
        vscode.postMessage({
          type: 'createAgent',
          agentType: agentType ? agentType.value : 'agent',
          workingDir: workingDir ? workingDir.value : '',
          name: agentName ? agentName.value : '',
          llmGroup: llmGroup ? llmGroup.value : '',
          nodeId: nodeId ? nodeId.value : '',
          useWorktree: Boolean(useWorktree && useWorktree.checked),
          quickMode: Boolean(useQuickMode && useQuickMode.checked)
        });
      });
    }
    const cancelCreateAgentButton = document.getElementById('cancelCreateAgentButton');
    if (cancelCreateAgentButton) {
      cancelCreateAgentButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'cancelCreateAgent' });
      });
    }
    document.querySelectorAll('[data-terminal-agent-id]').forEach((item) => {
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        vscode.postMessage({ type: 'createTerminal', agentId: item.getAttribute('data-terminal-agent-id') });
      });
    });
    document.querySelectorAll('[data-copy-agent-id]').forEach((item) => {
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        vscode.postMessage({ type: 'copyAgent', agentId: item.getAttribute('data-copy-agent-id') });
      });
    });
    document.querySelectorAll('[data-delete-agent-id]').forEach((item) => {
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        vscode.postMessage({ type: 'deleteAgent', agentId: item.getAttribute('data-delete-agent-id') });
      });
    });
    // 文件树按钮点击
    document.querySelectorAll('[data-filetree-agent-id]').forEach((item) => {
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        const agentId = item.getAttribute('data-filetree-agent-id');
        const workingDir = item.getAttribute('data-working-dir');
        const nodeId = item.getAttribute('data-node-id');
        vscode.postMessage({ type: 'toggleFileTree', agentId, workingDir, nodeId });
      });
    });
    // 文件树节点点击
    document.querySelectorAll('.file-tree-node').forEach((item) => {
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        const nodePath = item.getAttribute('data-path');
        const nodeType = item.getAttribute('data-type');
        const agentId = item.getAttribute('data-agent-id');
        if (nodeType === 'directory') {
          vscode.postMessage({ type: 'toggleFileTreeNode', agentId, nodePath });
        } else {
          vscode.postMessage({ type: 'openRemoteFile', agentId, filePath: nodePath });
        }
      });
    });
    document.querySelectorAll('[data-agent-id]').forEach((item) => {
      item.addEventListener('click', () => {
        vscode.postMessage({ type: 'openAgent', agentId: item.getAttribute('data-agent-id') });
      });
    });
    // 批量选择模式按钮
    const toggleBatchModeButton = document.getElementById('toggleBatchModeButton');
    if (toggleBatchModeButton) {
      toggleBatchModeButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'toggleBatchMode' });
      });
    }
    // 全选按钮
    const toggleSelectAllButton = document.getElementById('toggleSelectAllButton');
    if (toggleSelectAllButton) {
      toggleSelectAllButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'toggleSelectAll' });
      });
    }
    // 批量复制按钮
    const batchCopyButton = document.getElementById('batchCopyButton');
    if (batchCopyButton) {
      batchCopyButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'batchCopyAgents' });
      });
    }
    // 批量删除按钮
    const batchDeleteButton = document.getElementById('batchDeleteButton');
    if (batchDeleteButton) {
      batchDeleteButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'batchDeleteAgents' });
      });
    }
    // 退出批量模式按钮
    const exitBatchModeButton = document.getElementById('exitBatchModeButton');
    if (exitBatchModeButton) {
      exitBatchModeButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'toggleBatchMode' });
      });
    }
    // Agent checkbox 点击
    document.querySelectorAll('[data-select-agent-id]').forEach((item) => {
      item.addEventListener('click', (event) => {
        event.stopPropagation();
        vscode.postMessage({ type: 'toggleSelectAgent', agentId: item.getAttribute('data-select-agent-id') });
      });
    });
    // 恢复搜索框焦点（如果正在搜索）
    const searchInput = document.getElementById('remoteDirectorySearchInput');
    if (searchInput && searchInput.value) {
      searchInput.focus();
      searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
    }
  </script>
</body>
</html>`;
  }

  private getLeftLoginHtml(nonce: string): string {
    const connectButtonDisabled = this.leftViewLoginState.isSubmitting
      ? "disabled"
      : "";
    const loginErrorMarkup = this.leftViewLoginState.errorMessage
      ? `<div class="form-error">${escapeHtml(this.leftViewLoginState.errorMessage)}</div>`
      : "";

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Jarvis Login</title>
  <style>
    body { font-family: var(--vscode-font-family); padding: 12px; color: var(--vscode-foreground); }
    .login-panel { border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 12px; }
    .panel-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
    .form-group { margin-bottom: 10px; }
    .form-group label { display: block; font-size: 12px; margin-bottom: 4px; opacity: 0.9; }
    input { width: 100%; padding: 6px 8px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border, var(--vscode-panel-border)); border-radius: 4px; box-sizing: border-box; }
    button { width: 100%; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: 1px solid var(--vscode-input-border, var(--vscode-panel-border)); border-radius: 4px; padding: 8px 12px; cursor: pointer; }
    .form-error { color: var(--vscode-errorForeground); font-size: 12px; margin-bottom: 10px; }
    .help-text { font-size: 12px; opacity: 0.8; margin-top: 10px; }
    .status-text { font-size: 12px; margin-bottom: 10px; opacity: 0.85; }
    .status-text.error { color: var(--vscode-errorForeground); }
  </style>
</head>
<body>
  <div class="login-panel">
    <div class="panel-title">连接到 Jarvis</div>
    <div class="status-text ${this.panelState.gatewayHasConnectionError ? "error" : ""}">当前连接状态：${escapeHtml(this.panelState.gatewayConnectionStatusText)}</div>
    ${loginErrorMarkup}
    <div class="form-group">
      <label for="gatewayUrl">网关地址</label>
      <input id="gatewayUrl" value="${escapeHtml(this.panelState.gatewayUrl)}" placeholder="127.0.0.1:8000" />
    </div>
    <div class="form-group">
      <label for="password">密码</label>
      <input id="password" type="password" value="${escapeHtml(this.panelState.password)}" placeholder="可选" />
    </div>
    <button id="connectButton" ${connectButtonDisabled}>${this.leftViewLoginState.isSubmitting ? "连接中..." : "连接"}</button>
    <div class="help-text">登录成功后将自动切换到 Agent 列表。</div>
  </div>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const connectButton = document.getElementById('connectButton');
    if (connectButton) {
      connectButton.addEventListener('click', () => {
        const gatewayUrl = document.getElementById('gatewayUrl');
        const password = document.getElementById('password');
        vscode.postMessage({
          type: 'connect',
          gatewayUrl: gatewayUrl ? gatewayUrl.value : '',
          password: password ? password.value : ''
        });
      });
    }
    const passwordInput = document.getElementById('password');
    if (passwordInput) {
      passwordInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          const gatewayUrl = document.getElementById('gatewayUrl');
          const password = document.getElementById('password');
          vscode.postMessage({
            type: 'connect',
            gatewayUrl: gatewayUrl ? gatewayUrl.value : '',
            password: password ? password.value : ''
          });
        }
      });
    }
  </script>
</body>
</html>`;
  }

  private getChatPanelHtml(agentId?: string): string {
    const nonce = createNonce();
    const selectedAgentLabel = this.getAgentDisplayLabel(agentId);
    const webview = this.currentPanel?.webview;
    const xtermCssUri = webview
      ? webview.asWebviewUri(
          vscode.Uri.joinPath(
            this.extensionUri,
            "node_modules",
            "xterm",
            "css",
            "xterm.css",
          ),
        )
      : "";
    const chatPanelJsUri = webview
      ? webview.asWebviewUri(
          vscode.Uri.joinPath(this.extensionUri, "media", "chatPanel.js"),
        )
      : "";
    const cspSource = webview?.cspSource || "";
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' ${cspSource}; script-src 'nonce-${nonce}' ${cspSource}; img-src 'self' https: data:;">
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="${xtermCssUri}">
  <title>Jarvis Chat</title>
  <style>
    body { font-family: var(--vscode-font-family); padding: 0; margin: 0; color: var(--vscode-foreground); background: var(--vscode-editor-background); }
    .layout { display: grid; grid-template-rows: auto 1fr auto; height: 100vh; }
    .section { padding: 12px; border-bottom: 1px solid var(--vscode-panel-border); }
    .input-section { position: relative; }
    .messages { overflow: auto; padding: 12px; }
    .message { margin-bottom: 12px; padding: 10px; border-radius: 8px; background: var(--vscode-sideBar-background); white-space: normal; overflow-wrap: anywhere; }
    .message.system { background: rgba(59, 130, 246, 0.16); border-left: 3px solid #3b82f6; }
    .message.error { border-left: 3px solid var(--vscode-errorForeground); }
    .message.output { border-left: 3px solid var(--vscode-testing-iconPassed); }
    .message.stream { border-left: 3px solid var(--vscode-charts-blue); }
    .message.execution { border-left: 3px solid var(--vscode-terminal-ansiGreen, var(--vscode-testing-iconPassed)); }
    .message p { margin: 0 0 8px; }
    .message p:last-child { margin-bottom: 0; }
    .message ul, .message ol { margin: 0 0 8px 20px; padding: 0; }
    .message li + li { margin-top: 4px; }
    .message pre { margin: 8px 0; padding: 10px; border-radius: 6px; overflow: auto; background: var(--vscode-textCodeBlock-background, rgba(255,255,255,0.06)); }
    .message code { font-family: var(--vscode-editor-font-family); font-size: 12px; }
    .message :not(pre) > code { padding: 2px 4px; border-radius: 4px; background: var(--vscode-textCodeBlock-background, rgba(255,255,255,0.06)); }
    .message blockquote { margin: 8px 0; padding-left: 12px; border-left: 3px solid var(--vscode-panel-border); opacity: 0.9; }
    .message a { color: var(--vscode-textLink-foreground); }
    .message table { width: 100%; border-collapse: collapse; margin: 8px 0; }
    .message th, .message td { border: 1px solid var(--vscode-panel-border); padding: 6px 8px; text-align: left; }
    .message .plantuml-block { margin: 8px 0; padding: 10px; border: 1px solid var(--vscode-panel-border); border-radius: 6px; background: var(--vscode-editor-background); }
    .message .plantuml-notice { margin-bottom: 8px; font-size: 12px; opacity: 0.8; }
    .message .plantuml-link { display: inline-block; text-decoration: none; }
    .message .plantuml-image { max-width: 100%; border-radius: 4px; background: #fff; }
    .message .plantuml-source summary { cursor: pointer; margin-top: 8px; }
    .message-header { font-size: 12px; font-weight: 600; margin-bottom: 8px; opacity: 0.85; }
    .execution-hint { font-size: 12px; opacity: 0.82; margin-bottom: 8px; }
    .execution-terminal { height: 240px; border: 1px solid var(--vscode-panel-border); border-radius: 6px; overflow: hidden; background: var(--vscode-editor-background); }
    .xterm-helpers { position: absolute; left: -9999px; top: -9999px; width: 0; height: 0; overflow: hidden; }
    .execution-finished { margin-top: 8px; font-size: 12px; opacity: 0.75; }
    .row { display: flex; gap: 8px; align-items: center; }
    .input-actions { display: flex; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
    .secondary-button {
      background: var(--vscode-button-secondaryBackground, var(--vscode-button-background));
      color: var(--vscode-button-secondaryForeground, var(--vscode-button-foreground));
      border-radius: 999px;
      min-height: 34px;
      padding: 7px 14px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.01em;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18);
      transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease, background 0.15s ease;
    }
    .secondary-button:hover:not(:disabled) {
      transform: translateY(-1px);
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.18);
      filter: brightness(1.04);
    }
    .secondary-button:active:not(:disabled) {
      transform: translateY(0);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
      filter: brightness(0.98);
    }
    .secondary-button:disabled {
      cursor: not-allowed;
      opacity: 0.55;
      box-shadow: none;
      filter: none;
    }
    #completionButton {
      background: rgba(59, 130, 246, 0.16);
      color: #60a5fa;
      border-color: rgba(59, 130, 246, 0.32);
      min-width: 42px;
      padding-left: 12px;
      padding-right: 12px;
    }
    #completeButton {
      background: rgba(34, 197, 94, 0.14);
      color: #4ade80;
      border-color: rgba(34, 197, 94, 0.28);
    }
    #manualInterruptButton {
      background: rgba(245, 158, 11, 0.14);
      color: #fbbf24;
      border-color: rgba(245, 158, 11, 0.3);
    }
    #clearBufferBtn {
      background: rgba(239, 68, 68, 0.14);
      color: #f87171;
      border-color: rgba(239, 68, 68, 0.28);
      display: none;
    }
    .buffer-indicator {
      display: none;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: rgba(251, 191, 36, 0.12);
      border: 1px solid rgba(251, 191, 36, 0.3);
      border-radius: 6px;
      font-size: 12px;
      color: #fbbf24;
      cursor: pointer;
      margin-bottom: 8px;
      transition: background 0.15s ease;
    }
    .buffer-indicator:hover {
      background: rgba(251, 191, 36, 0.2);
    }
    .buffer-indicator .buffer-icon { font-size: 14px; }
    .buffer-indicator .buffer-text { opacity: 0.9; }
    .buffer-modal {
      width: 90%;
      max-width: 500px;
      background: var(--vscode-editor-background);
      border: 1px solid var(--vscode-panel-border);
      border-radius: 8px;
      overflow: hidden;
    }
    .buffer-panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 16px;
      background: var(--vscode-sideBar-background);
      border-bottom: 1px solid var(--vscode-panel-border);
    }
    .buffer-panel-title { font-weight: 600; font-size: 14px; }
    .buffer-panel-actions { display: flex; gap: 8px; }
    .buffer-panel-btn {
      padding: 4px 10px;
      font-size: 12px;
      border-radius: 4px;
      background: var(--vscode-button-secondaryBackground);
      color: var(--vscode-button-secondaryForeground);
      border: 1px solid var(--vscode-panel-border);
      cursor: pointer;
    }
    .buffer-panel-btn:hover { filter: brightness(1.1); }
    .buffer-panel-btn.close-btn { background: rgba(239, 68, 68, 0.14); color: #f87171; }
    .buffer-panel-content { padding: 16px; }
    .buffer-edit-textarea {
      width: 100%;
      min-height: 150px;
      padding: 10px;
      font-family: var(--vscode-editor-font-family);
      font-size: 13px;
      resize: vertical;
      box-sizing: border-box;
    }
    .buffer-panel-footer { margin-top: 12px; text-align: right; }
    .buffer-save-btn {
      padding: 8px 16px;
      background: linear-gradient(135deg, rgba(34, 197, 94, 0.9), rgba(22, 163, 74, 0.9));
      color: #fff;
      border: none;
      border-radius: 6px;
      font-weight: 600;
      cursor: pointer;
    }
    .buffer-save-btn:hover { filter: brightness(1.05); }
    .buffer-save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    #sendButton,
    #sendSingleButton {
      min-width: 72px;
      min-height: 36px;
      border-radius: 999px;
      padding: 8px 16px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.01em;
      background: linear-gradient(135deg, rgba(59, 130, 246, 0.92), rgba(37, 99, 235, 0.92));
      color: #ffffff;
      border-color: rgba(59, 130, 246, 0.38);
      box-shadow: 0 6px 14px rgba(37, 99, 235, 0.22);
    }
    #sendButton:hover,
    #sendSingleButton:hover {
      transform: translateY(-1px);
      filter: brightness(1.03);
      box-shadow: 0 8px 18px rgba(37, 99, 235, 0.26);
    }
    #sendButton:active,
    #sendSingleButton:active {
      transform: translateY(0);
      filter: brightness(0.98);
      box-shadow: 0 3px 8px rgba(37, 99, 235, 0.22);
    }
    #sendButton:disabled,
    #sendSingleButton:disabled {
      opacity: 0.55;
      cursor: not-allowed;
      box-shadow: none;
      filter: none;
    }
    input, textarea { flex: 1; padding: 8px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border, var(--vscode-panel-border)); box-sizing: border-box; }
    textarea { min-height: 84px; resize: vertical; }
    button { border: 1px solid var(--vscode-button-border, transparent); background: var(--vscode-button-background); color: var(--vscode-button-foreground); padding: 8px 12px; cursor: pointer; transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease; }
    .status { font-size: 12px; opacity: 0.8; }
    .status.error { color: var(--vscode-errorForeground); }
    .hint { font-size: 12px; opacity: 0.75; }
    .meta { display: flex; flex-direction: column; gap: 6px; }
    
    /* Diff styles */
    .diff-side-by-side { margin: 8px 0; border-radius: 6px; overflow: hidden; background: var(--vscode-editor-background); }
    .diff-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: var(--vscode-sideBar-background); font-size: 12px; }
    .diff-file-path { font-weight: 600; }
    .diff-stats { font-size: 11px; opacity: 0.8; }
    .diff-additions { color: var(--vscode-testing-iconPassed); }
    .diff-deletions { color: var(--vscode-errorForeground); }
    .diff-table { width: 100%; border-collapse: collapse; font-family: var(--vscode-editor-font-family); font-size: 12px; table-layout: fixed; }
    .diff-table td { border-top: none; border-bottom: none; }
    .diff-old-content, .diff-new-content { width: calc(50% - 40px); }
    .diff-old-num, .diff-new-num { width: 40px; }

    .diff-line-num { width: 40px; padding: 4px 8px; text-align: right; background: var(--vscode-sideBar-background); color: var(--vscode-descriptionForeground); font-size: 11px; user-select: none; }
    .diff-content { padding: 4px 8px; white-space: pre-wrap; font-family: var(--vscode-editor-font-family); }

    .diff-added { background: rgba(76, 175, 80, 0.15); }
    .diff-deleted { background: rgba(244, 67, 54, 0.15); }
    .diff-error { padding: 10px; text-align: center; color: var(--vscode-errorForeground); font-size: 12px; }
    .running-indicator { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 6px; margin-top: 4px; margin-bottom: 8px; animation: fadeIn 0.3s ease-in-out; position: sticky; bottom: 0; z-index: 1; backdrop-filter: blur(2px); }
    .running-spinner { width: 16px; height: 16px; border: 2px solid rgba(59, 130, 246, 0.3); border-top-color: #3b82f6; border-radius: 50%; animation: spin 1s linear infinite; flex-shrink: 0; }
    .running-text { font-size: 13px; color: #3b82f6; font-weight: 500; }
    .modal-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.38); display: none; align-items: center; justify-content: center; z-index: 20; }
    .modal-overlay.visible { display: flex; }
    .completions-modal { width: min(720px, calc(100vw - 32px)); max-height: min(70vh, 640px); display: flex; flex-direction: column; background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); border: 1px solid var(--vscode-panel-border, rgba(255,255,255,0.12)); border-radius: 10px; box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35); overflow: hidden; }
    .modal-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-bottom: 1px solid var(--vscode-panel-border, rgba(255,255,255,0.1)); }
    .modal-title { font-size: 14px; font-weight: 600; }
    .icon-button { border: 1px solid var(--vscode-button-border, transparent); background: transparent; color: inherit; padding: 6px 10px; cursor: pointer; }
    .completions-search { padding: 12px 14px; border-bottom: 1px solid var(--vscode-panel-border, rgba(255,255,255,0.08)); }
    .completions-search input { width: 100%; }
    .completions-list { overflow: auto; padding: 6px 0; }
    .completion-item { padding: 10px 14px; cursor: pointer; border-bottom: 1px solid rgba(127, 127, 127, 0.08); }
    .completion-item:hover, .completion-item.selected { background: var(--vscode-list-hoverBackground, rgba(255,255,255,0.08)); }
    .completion-value { font-size: 13px; font-weight: 600; }
    .completion-desc { font-size: 12px; opacity: 0.78; margin-top: 2px; }
    .completion-empty { padding: 18px 14px; font-size: 12px; opacity: 0.75; }
    .completion-status { padding: 8px 14px; font-size: 12px; opacity: 0.82; border-bottom: 1px solid rgba(127, 127, 127, 0.08); }
    .completion-status.error { color: var(--vscode-errorForeground); }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
    /* Confirm dialog styles */
    .confirm-dialog { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5); display: none; align-items: center; justify-content: center; z-index: 30; }
    .confirm-dialog.visible { display: flex; }
    .confirm-box { background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); border: 1px solid var(--vscode-panel-border, rgba(255,255,255,0.12)); border-radius: 10px; box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35); padding: 20px; min-width: 320px; max-width: 480px; }
    .confirm-message { font-size: 14px; margin-bottom: 16px; line-height: 1.5; }
    .confirm-actions { display: flex; gap: 10px; justify-content: flex-end; }
    .confirm-btn { order: 0; }
    .confirm-btn.default { order: 1; }
    .confirm-btn { padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid var(--vscode-button-border, transparent); background: var(--vscode-button-background); color: var(--vscode-button-foreground); transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease; }
    .confirm-btn:hover { background: var(--vscode-button-hoverBackground); }
    .confirm-btn.default { background: linear-gradient(135deg, rgba(59, 130, 246, 0.92), rgba(37, 99, 235, 0.92)); color: #ffffff; border-color: rgba(59, 130, 246, 0.38); }
    .confirm-btn.default:hover { filter: brightness(1.03); }
  </style>
</head>
<body>
  <div class="layout">
    <div class="section meta">
      <div><strong>当前 Agent：</strong><span id="selectedAgentLabel">${selectedAgentLabel}</span></div>
      <div class="status" id="connectionStatus">未连接</div>
      <div class="hint" id="executionStatusHint">执行状态：${this.getExecutionStatusLabel(this.getSelectedAgentStatus()?.execution_status || "running")}</div>
      <div class="hint" id="inputTip">当前为多行输入模式，按 Ctrl+Enter 发送</div>
      <div class="hint">连接与 Agent 管理请在左侧边栏完成；执行终端将在当前 Chat Panel 中以内嵌终端显示。</div>
    </div>
    <div class="messages" id="messages"></div>
    <div class="section input-section">
      <div class="running-indicator" id="runningIndicator" style="display:none;">
        <div class="running-spinner"></div>
        <span class="running-text">Agent 正在执行中...</span>
      </div>
      <div class="buffer-indicator" id="bufferIndicator">
        <span class="buffer-icon">📝</span>
        <span class="buffer-text">缓冲区有内容，点击管理</span>
      </div>
      <div class="input-actions">
        <button id="clearBufferBtn" class="secondary-button" title="清空缓冲区">清空</button>
        <button id="completionButton" class="secondary-button" title="插入 @">@</button>
        <button id="completeButton" class="secondary-button" title="完成（发送完成信号）">完成</button>
        <button id="manualInterruptButton" class="secondary-button" title="人工干预" style="display:none;">人工干预</button>
      </div>
      <div class="row" id="singleInputRow" style="display:none;">
        <input id="singleMessageInput" placeholder="输入单行内容，按 Ctrl+Enter 发送..." />
        <button id="sendSingleButton">发送</button>
      </div>
      <div id="multiInputRow">
        <div class="row">
          <textarea id="messageInput" placeholder="输入消息，按 Ctrl+Enter 发送..."></textarea>
          <button id="sendButton">发送</button>
        </div>
      </div>
    </div>
  </div>
  <div class="modal-overlay" id="completionModalOverlay">
    <div class="completions-modal" role="dialog" aria-modal="true" aria-label="插入补全">
      <div class="modal-header">
        <div class="modal-title">插入补全</div>
        <button id="closeCompletionModalButton" class="icon-button" title="关闭">✕</button>
      </div>
      <div class="completions-search">
        <input id="completionSearchInput" type="text" placeholder="搜索补全..." />
      </div>
      <div id="completionStatus" class="completion-status" style="display:none;"></div>
      <div id="completionList" class="completions-list"></div>
    </div>
  </div>
  <div class="confirm-dialog" id="confirmDialog">
    <div class="confirm-box">
      <p class="confirm-message" id="confirmMessage"></p>
      <div class="confirm-actions">
        <button id="confirmCancelButton" class="confirm-btn">取消</button>
        <button id="confirmConfirmButton" class="confirm-btn default">确认</button>
      </div>
    </div>
  </div>
  <script nonce="${nonce}" src="${chatPanelJsUri}"></script>
</body>
</html>`;
  }

  private async handleChatPanelMessage(
    message: ChatPanelMessage,
  ): Promise<void> {
    if (message.type === "disconnect") {
      await this.disconnectAll();
      return;
    }
    if (message.type === "sendMessage") {
      await this.sendAgentMessage(message.text ?? "");
      return;
    }
    if (message.type === "sendCompletionSignal") {
      await this.sendCompletionSignal();
      return;
    }
    if (message.type === "sendManualInterrupt") {
      await this.sendManualInterrupt();
      return;
    }
    if (message.type === "openCompletions") {
      await this.openCompletions();
      return;
    }
    if (message.type === "searchCompletions") {
      await this.searchCompletions(String(message.query || ""));
      return;
    }
    if (message.type === "sendTerminalInput") {
      await this.sendTerminalInput(message.text ?? "", message.executionId);
      return;
    }
    if (message.type === "terminalResize") {
      await this.sendTerminalResize(
        message.executionId,
        message.cols,
        message.rows,
      );
      return;
    }
    if (message.type === "confirmResult") {
      const agentId = String(
        message.agentId || this.panelState.selectedAgentId || "",
      ).trim();
      if (!agentId) {
        this.appendPanelMessage("无法确定 Agent ID", "error");
        return;
      }
      await this.sendConfirmResult(agentId, Boolean(message.confirmed));
    }
    if (message.type === "loadMoreHistory") {
      await this.loadMoreHistory(
        message.payload?.offset || 0,
        message.payload?.limit || 50,
      );
    }
  }

  private async loadMoreHistory(offset: number, limit: number): Promise<void> {
    const agentId = this.panelState.selectedAgentId;
    if (!agentId) {
      console.log("[HISTORY] No active agent, skip loading more history");
      return;
    }

    console.log(
      "[HISTORY] Loading more history for agent:",
      agentId,
      "offset:",
      offset,
      "limit:",
      limit,
    );

    // 获取持久化的历史消息
    const allHistory = this.getPersistedAgentChatHistory();
    const agentHistory = allHistory[agentId] || [];

    // 计算要加载的消息范围（从旧到新）
    // offset 是已经加载的消息数量，我们要加载 offset 之前的 limit 条消息
    // 确保偏移量不超过总消息数
    const effectiveOffset = Math.min(offset, agentHistory.length);
    const startIndex = Math.max(
      0,
      agentHistory.length - effectiveOffset - limit,
    );
    const endIndex = Math.max(0, agentHistory.length - effectiveOffset);
    const historyMessages = agentHistory.slice(startIndex, endIndex);

    console.log(
      "[HISTORY] History range: total=",
      agentHistory.length,
      "offset=",
      offset,
      "start=",
      startIndex,
      "end=",
      endIndex,
    );

    console.log(
      "[HISTORY] Found",
      historyMessages.length,
      "messages from",
      startIndex,
      "to",
      endIndex,
    );

    // 将持久化消息转换为聊天消息格式
    const chatMessages: ChatMessageItem[] = historyMessages.map((msg) => ({
      text: msg.text,
      variant: msg.variant,
      lang: msg.lang,
    }));

    // 发送历史消息到前端（使用特定类型标识历史加载）
    if (this.currentPanel?.webview) {
      this.currentPanel.webview.postMessage({
        type: "historyLoaded",
        payload: {
          messages: chatMessages,
        },
      });
    }
  }

  private async disconnectAll(): Promise<void> {
    // 断开所有WebSocket连接
    this.stopAgentListRefresh();
    this.disposeSocket("gatewaySocket");

    // 关闭所有Agent WebSocket连接
    for (const socket of this.agentSockets.values()) {
      try {
        socket.close();
      } catch {
        // ignore close error
      }
    }
    this.agentSockets.clear();
    this.agentConnectionAttempts.clear();

    // 清空token和连接状态
    this.panelState.token = "";
    this.panelState.selectedAgentId = undefined;
    this.panelState.gatewaySocket = undefined;

    // 清理所有agent状态
    this.agentStatuses.clear();

    // 关闭右侧Chat Panel
    if (this.currentPanel) {
      this.currentPanel.dispose();
      this.currentPanel = undefined;
    }

    // 重新渲染界面
    this.renderAgentListView();

    // 显示断开连接成功提示
    vscode.window.showInformationMessage("已断开连接，可以切换网关服务器");
  }

  private restoreSavedConnectionInfo(): void {
    const savedConnectionInfo = this.globalState.get<SavedConnectionInfo>(
      SAVED_CONNECTION_INFO_KEY,
    );
    if (!savedConnectionInfo) {
      return;
    }
    const savedGatewayUrl = String(savedConnectionInfo.gatewayUrl || "").trim();
    if (savedGatewayUrl) {
      this.panelState.gatewayUrl = savedGatewayUrl;
    }
    this.panelState.connectionLockEnabled = Boolean(
      savedConnectionInfo.connectionLockEnabled,
    );
  }

  private async saveConnectionInfo(): Promise<void> {
    await this.globalState.update(SAVED_CONNECTION_INFO_KEY, {
      gatewayUrl: this.panelState.gatewayUrl,
      connectionLockEnabled: this.panelState.connectionLockEnabled,
    } satisfies SavedConnectionInfo);
  }

  private getPersistedAgentChatHistory(): Record<
    string,
    PersistedChatMessageItem[]
  > {
    const savedHistory = this.globalState.get<
      Record<string, PersistedChatMessageItem[]>
    >(AGENT_CHAT_HISTORY_KEY);
    if (!savedHistory || typeof savedHistory !== "object") {
      return {};
    }
    return savedHistory;
  }

  private sanitizePersistedExecutionBuffer(
    buffer: unknown,
  ): string | undefined {
    const text = String(buffer || "");
    if (!text) {
      return undefined;
    }
    if (text.length <= MAX_PERSISTED_EXECUTION_BUFFER_LENGTH) {
      return text;
    }
    return text.slice(-MAX_PERSISTED_EXECUTION_BUFFER_LENGTH);
  }

  private toPersistedChatMessage(
    message: ChatMessageItem,
  ): PersistedChatMessageItem | undefined {
    if (message.variant === "stream") {
      return undefined;
    }
    return {
      text: String(message.text || ""),
      variant: message.variant,
      lang: message.lang,
      executionId: message.executionId,
      executionBuffer: this.sanitizePersistedExecutionBuffer(
        message.executionBuffer,
      ),
      finished:
        message.variant === "execution" ? Boolean(message.finished) : undefined,
    };
  }

  private async persistAgentHistoryImmediate(agentId: string): Promise<void> {
    const agentState = this.agentStatuses.get(agentId);
    if (!agentState) {
      return;
    }
    const persistedMessages = agentState.messages
      .map((message) => this.toPersistedChatMessage(message))
      .filter(
        (message): message is PersistedChatMessageItem => message !== undefined,
      )
      .slice(-MAX_PERSISTED_MESSAGES_PER_AGENT);
    const allHistory = this.getPersistedAgentChatHistory();
    allHistory[agentId] = persistedMessages;
    await this.globalState.update(AGENT_CHAT_HISTORY_KEY, allHistory);
  }

  private persistAgentHistory = debounce((agentId: string) => {
    void this.persistAgentHistoryImmediate(agentId);
  }, 500);

  private loadPersistedAgentHistory(agentId: string): void {
    const allHistory = this.getPersistedAgentChatHistory();
    const persistedMessages = Array.isArray(allHistory[agentId])
      ? allHistory[agentId]
      : [];
    if (persistedMessages.length === 0) {
      return;
    }
    const state = this.agentStatuses.get(agentId);
    if (!state || state.messages.length > 0) {
      return;
    }
    const restoredMessages: ChatMessageItem[] = persistedMessages.map(
      (message) => ({
        text: String(message.text || ""),
        variant: message.variant,
        lang: message.lang,
        executionId: message.executionId,
        executionBuffer: this.sanitizePersistedExecutionBuffer(
          message.executionBuffer,
        ),
        finished:
          message.variant === "execution"
            ? Boolean(message.finished)
            : undefined,
      }),
    );
    state.messages = restoredMessages;
    state.execution_buffers = {};
    state.active_execution_id = undefined;
    state.active_streaming_message_id = undefined;
    for (const message of restoredMessages) {
      if (message.variant === "execution" && message.executionId) {
        state.execution_buffers[message.executionId] =
          this.sanitizePersistedExecutionBuffer(message.executionBuffer) || "";
        if (message.finished === false) {
          state.active_execution_id = message.executionId;
        }
      }
    }
  }

  private async clearPersistedAgentHistory(agentId: string): Promise<void> {
    const allHistory = this.getPersistedAgentChatHistory();
    if (!(agentId in allHistory)) {
      return;
    }
    delete allHistory[agentId];
    await this.globalState.update(AGENT_CHAT_HISTORY_KEY, allHistory);
  }

  private startAgentListRefresh(): void {
    this.stopAgentListRefresh();
    this.agentListRefreshTimer = setInterval(() => {
      void this.refreshAgents();
    }, AGENT_LIST_REFRESH_INTERVAL_MS);
    void this.refreshAgents();
  }

  private stopAgentListRefresh(): void {
    if (!this.agentListRefreshTimer) {
      return;
    }
    clearInterval(this.agentListRefreshTimer);
    this.agentListRefreshTimer = undefined;
  }

  private async connectToGateway(
    gatewayUrl: string,
    password: string,
  ): Promise<void> {
    this.panelState.gatewayUrl =
      gatewayUrl.trim() || this.panelState.gatewayUrl;
    this.panelState.password = password;
    this.appendPanelMessage(
      `正在连接 ${this.panelState.gatewayUrl} ...`,
      "system",
    );

    try {
      const token = await this.loginWithPassword(this.panelState.password);
      this.panelState.token = token;
      this.panelState.password = "";
      this.panelState.gatewayConnectionStatusText = "已登录，正在连接主网关";
      this.panelState.gatewayHasConnectionError = false;
      this.leftViewLoginState.errorMessage = "";
      const agentStatus = this.getSelectedAgentStatus();
      if (agentStatus) {
        agentStatus.messages = [];
        agentStatus.terminal_output = "暂无终端输出";
        agentStatus.input_mode = "multi";
        agentStatus.input_tip = "";
        agentStatus.execution_status = "running";
        agentStatus.pending_request_id = undefined;
        agentStatus.pending_stream_text = "";
      }
      await this.saveConnectionInfo();
      await this.loadModelGroups();
      await this.loadNodeOptions();
      this.postPanelState();
      this.connectGatewaySocket();
      this.startAgentListRefresh();
      // 确保WebView收到连接成功后的状态更新
      setTimeout(() => {
        this.postPanelState();
      }, 100);
      this.renderAgentListView();
      this.appendPanelMessage("登录成功", "system");
    } catch (error) {
      const errorMessage = getErrorMessage(error);
      this.panelState.gatewayConnectionStatusText = `连接失败：${errorMessage}`;
      this.panelState.gatewayHasConnectionError = true;
      this.leftViewLoginState.errorMessage = errorMessage;
      this.postPanelState();
      this.renderAgentListView();
      this.appendPanelMessage(`连接失败：${errorMessage}`, "error");
      throw error;
    }
  }

  public async refreshAgents(): Promise<void> {
    if (!this.panelState.token) {
      this.stopAgentListRefresh();
      this.appendPanelMessage("请先连接并登录 Jarvis 网关", "error");
      return;
    }

    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
      const response = await this.fetchWithAuth(
        buildNodeHttpUrl(gatewayAddress, "master", "agents"),
      );
      const result = (await response.json()) as AgentListResponse;
      if (!response.ok || !result.success || !Array.isArray(result.data)) {
        throw new Error(result.error?.message || "获取 Agent 列表失败");
      }

      const newAgentItems: AgentListItem[] = result.data
        .slice()
        .reverse()
        .map((agent) => {
          const statusClass =
            agent.status === "stopped" ? "stopped" : "running";
          const statusText = statusClass === "stopped" ? "已完成" : "运行中";
          return {
            id: agent.agent_id,
            name: agent.name,
            displayName: agent.name || agent.agent_id,
            statusText,
            statusClass: statusClass as AgentListItem["statusClass"],
            agentType: agent.agent_type === "codeagent" ? "codeagent" : "agent",
            workingDir: agent.working_dir || "",
            llmGroup: agent.llm_group || "",
            worktree: Boolean(agent.worktree),
            quickMode: Boolean(agent.quick_mode),
            nodeId: String(agent.node_id || "").trim() || "master",
          };
        });

      for (const agentItem of newAgentItems) {
        if (agentItem.statusClass !== "stopped") {
          continue;
        }
        this.withAgentState(agentItem.id, (state) => {
          state.execution_status = "stopped";
          state.pending_request_id = undefined;
          state.input_tip = "";
          state.active_execution_id = undefined;
        });
      }

      // 检查数据是否有变化，无变化则不重新渲染
      const newAgentItemsJson = JSON.stringify(newAgentItems);
      const hasChanged = this.lastAgentItemsJson !== newAgentItemsJson;

      this.agentItems = newAgentItems;

      if (!this.panelState.selectedAgentId && this.agentItems.length > 0) {
        this.panelState.selectedAgentId = this.agentItems[0].id;
      }

      // 只有在数据变化时才重新渲染左侧列表；右侧 Chat Panel 仅同步状态，避免重建 DOM 抢占焦点
      if (hasChanged) {
        this.lastAgentItemsJson = newAgentItemsJson;
        this.renderAgentListView();
        if (this.currentPanel) {
          this.currentPanel.title = this.getChatPanelTitle();
          this.postPanelState();
        }
      }

      this.postPanelState();
      this.connectAgentSocket();
    } catch (error) {
      const errorMessage = getErrorMessage(error);
      this.appendPanelMessage(`加载 Agent 失败：${errorMessage}`, "error");
    }
  }

  private async sendAgentMessage(text: string): Promise<void> {
    const rawText = String(text ?? "");
    const agentStatus = this.getSelectedAgentStatus();
    const inputMode = agentStatus?.input_mode || "multi";
    const messageText = inputMode === "single" ? rawText : rawText.trim();
    if (inputMode !== "single" && !messageText) {
      return;
    }
    const agentId = this.panelState.selectedAgentId;
    if (!agentId) {
      this.appendPanelMessage("请先在左侧选择 Agent", "error");
      return;
    }
    if (!this.panelState.token) {
      this.appendPanelMessage("请先连接 Jarvis 网关", "error");
      return;
    }
    const agentSocket = this.agentSockets.get(agentId);
    if (!agentSocket || agentSocket.readyState !== WebSocket.OPEN) {
      this.appendPanelMessage(
        "当前 Agent WebSocket 未连接，无法发送消息",
        "error",
      );
      return;
    }

    this.appendPanelMessage(`我：${messageText}`, "system", agentId);
    const pendingRequestId = agentStatus?.pending_request_id;
    agentSocket.send(
      JSON.stringify({
        type: "input_result",
        payload: {
          text: messageText,
          request_id: pendingRequestId,
        },
      }),
    );
    if (agentStatus) {
      agentStatus.pending_request_id = undefined;
      agentStatus.input_tip = "";
      agentStatus.input_mode = "multi";
      agentStatus.execution_status = "running";
    }
    this.postPanelState();
  }

  private async sendCompletionSignal(): Promise<void> {
    const agentId = this.panelState.selectedAgentId;
    if (!agentId) {
      this.appendPanelMessage("请先在左侧选择 Agent", "error");
      return;
    }
    const agentSocket = this.agentSockets.get(agentId);
    if (!agentSocket || agentSocket.readyState !== WebSocket.OPEN) {
      this.appendPanelMessage(
        "当前 Agent WebSocket 未连接，无法发送完成信号",
        "error",
        agentId,
      );
      return;
    }
    const agentStatus = this.agentStatuses.get(agentId);
    const pendingRequestId = agentStatus?.pending_request_id;
    this.sendSocketMessage(agentSocket, {
      type: "input_result",
      payload: {
        text: "__CTRL_C_PRESSED__",
        request_id: pendingRequestId,
      },
    });
    this.withAgentState(agentId, (state) => {
      state.pending_request_id = undefined;
      state.input_tip = "";
      state.execution_status = "running";
      state.input_mode = "multi";
    });
    this.postPanelState();
  }

  private async sendManualInterrupt(): Promise<void> {
    const agentId = this.panelState.selectedAgentId;
    if (!agentId) {
      this.appendPanelMessage("请先在左侧选择 Agent", "error");
      return;
    }
    const agentSocket = this.agentSockets.get(agentId);
    if (!agentSocket || agentSocket.readyState !== WebSocket.OPEN) {
      this.appendPanelMessage(
        "当前 Agent WebSocket 未连接，无法发送人工干预",
        "error",
        agentId,
      );
      return;
    }
    this.sendSocketMessage(agentSocket, {
      type: "manual_interrupt",
      payload: {},
    });
    this.appendPanelMessage("已发送人工干预请求", "system", agentId);
  }

  private async openCompletions(): Promise<void> {
    const agentId = String(this.panelState.selectedAgentId || "").trim();
    if (!agentId) {
      this.currentPanel?.webview.postMessage({
        type: "completionsResult",
        payload: {
          items: [],
          error: "请先在左侧选择 Agent",
          query: "",
        },
      });
      return;
    }
    if (!this.panelState.token) {
      this.currentPanel?.webview.postMessage({
        type: "completionsResult",
        payload: {
          items: [],
          error: "请先连接并登录 Jarvis 网关",
          query: "",
        },
      });
      return;
    }
    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
      const agentNodeId =
        this.agentItems.find((item) => item.id === agentId)?.nodeId || "";
      const response = await this.fetchWithAuth(
        buildHttpUrl(
          gatewayAddress,
          `/api/node/${encodeURIComponent(String(agentNodeId || "master").trim() || "master")}/completions/${agentId}`,
        ),
      );
      const result = (await response.json()) as {
        success?: boolean;
        data?: CompletionItem[];
        error?: { message?: string };
      };
      if (!response.ok || !result.success || !Array.isArray(result.data)) {
        throw new Error(result.error?.message || "获取补全列表失败");
      }
      this.currentPanel?.webview.postMessage({
        type: "completionsResult",
        payload: {
          items: result.data,
          query: "",
        },
      });
    } catch (error) {
      this.currentPanel?.webview.postMessage({
        type: "completionsResult",
        payload: {
          items: [],
          error: getErrorMessage(error),
          query: "",
        },
      });
    }
  }

  private async searchCompletions(query: string): Promise<void> {
    const agentId = String(this.panelState.selectedAgentId || "").trim();
    const trimmedQuery = String(query || "").trim();
    if (!agentId || !trimmedQuery) {
      this.currentPanel?.webview.postMessage({
        type: "completionSearchResult",
        payload: {
          items: [],
          query: trimmedQuery,
        },
      });
      return;
    }
    if (!this.panelState.token) {
      this.currentPanel?.webview.postMessage({
        type: "completionSearchResult",
        payload: {
          items: [],
          query: trimmedQuery,
          error: "请先连接并登录 Jarvis 网关",
        },
      });
      return;
    }
    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
      const agentNodeId =
        this.agentItems.find((item) => item.id === agentId)?.nodeId || "";
      const response = await this.fetchWithAuth(
        buildHttpUrl(
          gatewayAddress,
          `/api/node/${encodeURIComponent(String(agentNodeId || "master").trim() || "master")}/completions/${agentId}/search?query=${encodeURIComponent(trimmedQuery)}`,
        ),
      );
      const result = (await response.json()) as {
        success?: boolean;
        data?: CompletionItem[];
        error?: { message?: string };
      };
      if (!response.ok || !result.success || !Array.isArray(result.data)) {
        throw new Error(result.error?.message || "搜索补全失败");
      }
      this.currentPanel?.webview.postMessage({
        type: "completionSearchResult",
        payload: {
          items: result.data,
          query: trimmedQuery,
        },
      });
    } catch (error) {
      this.currentPanel?.webview.postMessage({
        type: "completionSearchResult",
        payload: {
          items: [],
          query: trimmedQuery,
          error: getErrorMessage(error),
        },
      });
    }
  }

  private async sendTerminalInput(
    text: string,
    executionId?: string,
  ): Promise<void> {
    const inputText = String(text ?? "");
    if (!inputText) {
      return;
    }
    const resolvedSession = this.resolveExecutionSession(executionId);
    if (!resolvedSession) {
      this.appendPanelMessage(
        "当前没有可交互的执行会话，无法发送终端输入",
        "error",
      );
      return;
    }
    const agentSocket = this.agentSockets.get(resolvedSession.agentId);
    if (!agentSocket || agentSocket.readyState !== WebSocket.OPEN) {
      this.appendPanelMessage(
        "当前 Agent WebSocket 未连接，无法发送终端输入",
        "error",
        resolvedSession.agentId,
      );
      return;
    }
    agentSocket.send(
      JSON.stringify({
        type: "terminal_input",
        payload: {
          execution_id: resolvedSession.executionId,
          data: inputText,
        },
      }),
    );
  }

  private async sendTerminalResize(
    executionId?: string,
    cols?: number,
    rows?: number,
  ): Promise<void> {
    const resolvedSession = this.resolveExecutionSession(executionId);
    if (!resolvedSession) {
      return;
    }
    const agentSocket = this.agentSockets.get(resolvedSession.agentId);
    if (!agentSocket || agentSocket.readyState !== WebSocket.OPEN) {
      return;
    }
    const nextCols = Number(cols || 0);
    const nextRows = Number(rows || 0);
    if (nextCols <= 0 || nextRows <= 0) {
      return;
    }
    this.sendSocketMessage(agentSocket, {
      type: "terminal_resize",
      payload: {
        execution_id: resolvedSession.executionId,
        cols: nextCols,
        rows: nextRows,
      },
    });
  }

  private async createTerminalForAgent(agentId?: string): Promise<void> {
    const targetAgentId = String(
      agentId || this.panelState.selectedAgentId || "",
    ).trim();
    if (!targetAgentId) {
      vscode.window.showErrorMessage("请先选择一个 Agent");
      return;
    }
    if (!this.panelState.token) {
      vscode.window.showErrorMessage("请先连接 Jarvis 网关");
      return;
    }
    const gatewaySocket = this.panelState.gatewaySocket;
    if (!gatewaySocket || gatewaySocket.readyState !== WebSocket.OPEN) {
      vscode.window.showErrorMessage("网关未连接，无法创建终端");
      return;
    }

    const agentItem = this.agentItems.find((item) => item.id === targetAgentId);
    const nodeId = String(agentItem?.nodeId || "").trim();
    const workingDir = String(agentItem?.workingDir || "").trim();

    const payload: Record<string, string> = {};
    if (nodeId) {
      payload.node_id = nodeId;
    }
    if (workingDir) {
      payload.working_dir = workingDir;
    }

    this.sendSocketMessage(gatewaySocket, {
      type: "terminal_create",
      payload,
    });
  }

  private handleTerminalCreated(payload: Record<string, unknown>): void {
    console.log("[TERMINAL CREATED] payload:", payload);
    const terminalId = String(payload?.terminal_id || "").trim();
    if (!terminalId) {
      return;
    }

    const nodeId = String(payload?.node_id || "").trim();
    console.log(
      "[TERMINAL CREATED] terminalId:",
      terminalId,
      "nodeId:",
      nodeId,
    );
    const interpreter = String(payload?.interpreter || "bash").trim();
    const workingDir = String(payload?.working_dir || ".").trim();

    // 创建 EventEmitter 用于向终端写入数据
    const writeEmitter = new vscode.EventEmitter<string>();

    // 创建 Pseudoterminal
    const pty: vscode.Pseudoterminal = {
      onDidWrite: writeEmitter.event,
      open: (initialDimensions?: vscode.TerminalDimensions) => {
        writeEmitter.fire(`\x1b[32mJarvis Terminal [${terminalId}]\x1b[0m\r\n`);
        writeEmitter.fire(`Working directory: ${workingDir}\r\n\r\n`);
        // 发送初始尺寸
        console.log("[TERMINAL OPEN] initialDimensions:", initialDimensions);
        if (initialDimensions) {
          this.sendIndependentTerminalResize(
            terminalId,
            initialDimensions.columns,
            initialDimensions.rows,
          );
        } else {
          // 如果没有初始尺寸，使用默认值
          this.sendIndependentTerminalResize(terminalId, 80, 24);
        }
      },
      close: () => {
        this.closeIndependentTerminal(terminalId);
      },
      handleInput: (data: string) => {
        this.sendIndependentTerminalInput(terminalId, data);
      },
      setDimensions: (dimensions: vscode.TerminalDimensions) => {
        this.sendIndependentTerminalResize(
          terminalId,
          dimensions.columns,
          dimensions.rows,
        );
      },
    };

    // 创建 VSCode 终端
    const vscodeTerminal = vscode.window.createTerminal({
      name: `Jarvis: ${interpreter}`,
      pty,
    });

    // 保存会话
    const session: IndependentTerminalSession = {
      terminalId,
      nodeId,
      interpreter,
      workingDir,
      vscodeTerminal,
      pty,
      writeEmitter,
      closed: false,
    };
    this.independentTerminalSessions.set(terminalId, session);

    // 显示终端
    vscodeTerminal.show();
  }

  private sendIndependentTerminalInput(terminalId: string, data: string): void {
    const session = this.independentTerminalSessions.get(terminalId);
    if (!session || session.closed) {
      return;
    }
    const gatewaySocket = this.panelState.gatewaySocket;
    if (!gatewaySocket || gatewaySocket.readyState !== WebSocket.OPEN) {
      return;
    }

    const payload: Record<string, string> = {
      terminal_id: terminalId,
      data,
    };
    if (session.nodeId) {
      payload.node_id = session.nodeId;
    }

    this.sendSocketMessage(gatewaySocket, {
      type: "terminal_session_input",
      payload,
    });
  }

  private sendIndependentTerminalResize(
    terminalId: string,
    cols: number,
    rows: number,
  ): void {
    const session = this.independentTerminalSessions.get(terminalId);
    if (!session || session.closed) {
      return;
    }
    const gatewaySocket = this.panelState.gatewaySocket;
    if (!gatewaySocket || gatewaySocket.readyState !== WebSocket.OPEN) {
      return;
    }

    const payload: Record<string, string | number> = {
      terminal_id: terminalId,
      rows,
      cols,
    };
    if (session.nodeId) {
      payload.node_id = session.nodeId;
    }

    this.sendSocketMessage(gatewaySocket, {
      type: "terminal_session_resize",
      payload,
    });
  }

  private handleIndependentTerminalOutput(
    terminalId: string,
    data: string,
    encoded: boolean,
  ): void {
    const session = this.independentTerminalSessions.get(terminalId);
    if (!session || session.closed || !session.writeEmitter) {
      return;
    }

    let outputData = data;
    if (encoded) {
      try {
        outputData = Buffer.from(data, "base64").toString("utf-8");
      } catch {
        outputData = data;
      }
    }

    session.writeEmitter.fire(outputData);
  }

  private closeIndependentTerminal(terminalId: string): void {
    const session = this.independentTerminalSessions.get(terminalId);
    if (!session) {
      return;
    }

    session.closed = true;

    // 发送关闭消息到后端
    const gatewaySocket = this.panelState.gatewaySocket;
    if (gatewaySocket && gatewaySocket.readyState === WebSocket.OPEN) {
      const payload: Record<string, string> = {
        terminal_id: terminalId,
      };
      if (session.nodeId) {
        payload.node_id = session.nodeId;
      }
      this.sendSocketMessage(gatewaySocket, {
        type: "terminal_close",
        payload,
      });
    }

    // 清理资源
    if (session.writeEmitter) {
      session.writeEmitter.dispose();
    }

    this.independentTerminalSessions.delete(terminalId);
  }

  // ========== 文件树功能 ==========

  // 初始化文件树状态
  private initFileTreeState(agentId: string): void {
    if (!this.fileTreeState.has(agentId)) {
      this.fileTreeState.set(agentId, []);
      this.fileTreeExpanded.set(agentId, new Set());
    }
  }

  // 加载目录内容
  private async loadFileTreeNode(
    agentId: string,
    node: FileTreeNode,
    nodeId?: string,
  ): Promise<void> {
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    const targetNodeId = nodeId || "master";
    const url = buildNodeHttpUrl(
      gatewayAddress,
      targetNodeId,
      `directories?path=${encodeURIComponent(node.path)}`,
    );

    try {
      const response = await fetch(url, {
        headers: this.getAuthHeaders(),
      });

      if (!response.ok) {
        console.error("[FILETREE] 加载目录失败:", await response.text());
        return;
      }

      const result = await response.json();
      if (result.success && result.data) {
        const children: FileTreeNode[] = (result.data.items || []).map(
          (item: RemoteDirectoryItem) => {
            if (item.type === "file") {
              return {
                name: item.name,
                path: item.path,
                type: "file" as const,
              };
            }
            return {
              name: item.name,
              path: item.path,
              type: "directory" as const,
              expanded: false,
              loaded: false,
              children: [],
            };
          },
        );
        node.children = children;
        node.loaded = true;
      }
    } catch (error) {
      console.error("[FILETREE] 加载目录出错:", error);
    }
  }

  // 初始化文件树（加载根目录）
  private async initFileTree(
    agentId: string,
    rootPath: string,
    nodeId?: string,
  ): Promise<void> {
    this.initFileTreeState(agentId);

    const rootNode: FileTreeNode = {
      name: rootPath.split("/").pop() || rootPath,
      path: rootPath,
      type: "directory",
      expanded: true,
      loaded: false,
      children: [],
    };

    await this.loadFileTreeNode(agentId, rootNode, nodeId);
    this.fileTreeState.set(agentId, [rootNode]);
    this.fileTreeExpanded.get(agentId)?.add(rootPath);
  }

  // 切换节点展开/收缩
  private async toggleFileTreeNode(
    agentId: string,
    nodePath: string,
    nodeId?: string,
  ): Promise<void> {
    const treeNodes = this.fileTreeState.get(agentId);
    if (!treeNodes) return;

    const node = this.findFileTreeNode(treeNodes, nodePath);
    if (!node || node.type !== "directory") return;

    const expandedSet = this.fileTreeExpanded.get(agentId);
    if (!expandedSet) return;

    if (node.expanded) {
      node.expanded = false;
      expandedSet.delete(nodePath);
    } else {
      node.expanded = true;
      expandedSet.add(nodePath);
      if (!node.loaded) {
        await this.loadFileTreeNode(agentId, node, nodeId);
      }
    }
  }

  // 递归查找节点
  private findFileTreeNode(
    nodes: FileTreeNode[],
    path: string,
  ): FileTreeNode | null {
    for (const node of nodes) {
      if (node.path === path) {
        return node;
      }
      if (node.children && node.children.length > 0) {
        const found = this.findFileTreeNode(node.children, path);
        if (found) return found;
      }
    }
    return null;
  }

  // 获取可见的文件树节点（扁平化）
  private getVisibleFileTreeNodes(
    agentId: string,
  ): Array<{ node: FileTreeNode; depth: number }> {
    const treeNodes = this.fileTreeState.get(agentId) || [];
    return this.flattenFileTreeNodes(treeNodes, 0);
  }

  private flattenFileTreeNodes(
    nodes: FileTreeNode[],
    depth: number,
  ): Array<{ node: FileTreeNode; depth: number }> {
    const result: Array<{ node: FileTreeNode; depth: number }> = [];
    for (const node of nodes) {
      result.push({ node, depth });
      if (node.expanded && node.children && node.children.length > 0) {
        result.push(...this.flattenFileTreeNodes(node.children, depth + 1));
      }
    }
    return result;
  }

  // 打开远端文件进行编辑
  private async openRemoteFile(
    agentId: string,
    filePath: string,
    nodeId?: string,
  ): Promise<void> {
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    const targetNodeId = nodeId || "master";

    // 检查是否已经打开了相同路径的文件
    for (const [localPath, mapping] of this.remoteFileEditors.entries()) {
      if (
        mapping.remotePath === filePath &&
        mapping.agentId === agentId &&
        mapping.nodeId === targetNodeId
      ) {
        // 文件已打开，尝试激活它
        try {
          const existingDoc =
            await vscode.workspace.openTextDocument(localPath);
          await vscode.window.showTextDocument(existingDoc, {
            viewColumn: vscode.ViewColumn.One,
            preserveFocus: false,
            preview: false,
          });
          return;
        } catch {
          // 文件可能已被删除，从映射中移除
          this.remoteFileEditors.delete(localPath);
        }
      }
    }

    try {
      // 读取文件内容
      const response = await fetch(
        buildNodeHttpUrl(gatewayAddress, targetNodeId, "file-content"),
        {
          method: "POST",
          headers: {
            ...this.getAuthHeaders(),
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ path: filePath, node_id: targetNodeId }),
        },
      );

      const result = await response.json();
      if (!response.ok || !result.success || !result.data) {
        vscode.window.showErrorMessage(
          `读取文件失败: ${result.error?.message || "未知错误"}`,
        );
        return;
      }

      const content = result.data.content || "";

      // 创建临时文件（使用稳定的文件名，基于远端路径的 hash）
      const fileName = filePath.split("/").pop() || "untitled";
      const tempDir = path.join(
        os.tmpdir(),
        "jarvis-remote-files",
        agentId,
        targetNodeId,
      );
      await fs.promises.mkdir(tempDir, { recursive: true });

      // 使用远端路径的 base64 编码作为唯一标识，确保相同路径生成相同文件名
      const pathHash = Buffer.from(filePath)
        .toString("base64")
        .replace(/[/+=]/g, "_");
      const tempFilePath = path.join(tempDir, `${pathHash}_${fileName}`);

      // 检查文件是否已存在且是只读的，如果是则先改为可写
      try {
        const stat = await fs.promises.stat(tempFilePath);
        if (stat && (stat.mode & 0o200) === 0) {
          // 文件存在且是只读的，先改为可写
          await fs.promises.chmod(tempFilePath, 0o644);
        }
      } catch {
        // 文件不存在，忽略
      }

      await fs.promises.writeFile(tempFilePath, content, "utf-8");

      // 设置文件为只读（权限 444）
      await fs.promises.chmod(tempFilePath, 0o444);

      // 获取文件状态用于后续同步检查
      const fileStat = await this.fetchRemoteFileStat(filePath, targetNodeId);

      // 记录映射关系（包含 mtime 和 size 用于同步检查，默认只读）
      this.remoteFileEditors.set(tempFilePath, {
        agentId,
        remotePath: filePath,
        nodeId: targetNodeId,
        mtimeNs: fileStat?.mtime_ns,
        fileSize: fileStat?.size,
        readOnly: true,
      });

      // 在 VSCode 中打开文件（在第一列打开，会话面板在最右边）
      const document = await vscode.workspace.openTextDocument(tempFilePath);
      await vscode.window.showTextDocument(document, {
        viewColumn: vscode.ViewColumn.One,
        preserveFocus: false,
        preview: false,
      });

      // 启动心跳检查
      this.startRemoteFileHeartbeat();

      // 显示远端文件状态栏按钮
      this.showRemoteFileStatusBar(filePath, true);
    } catch (error) {
      console.error("[FILETREE] 打开文件出错:", error);
      vscode.window.showErrorMessage(`打开文件失败: ${error}`);
    }
  }

  // 保存文件到远端
  private async saveRemoteFile(localPath: string): Promise<boolean> {
    const mapping = this.remoteFileEditors.get(localPath);
    if (!mapping) {
      return false;
    }

    const { remotePath, nodeId } = mapping;
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);

    try {
      const content = await fs.promises.readFile(localPath, "utf-8");

      const response = await fetch(
        buildNodeHttpUrl(gatewayAddress, nodeId, "file-write"),
        {
          method: "POST",
          headers: {
            ...this.getAuthHeaders(),
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            path: remotePath,
            content,
            node_id: nodeId,
          }),
        },
      );

      const result = await response.json();
      if (!response.ok || !result.success) {
        vscode.window.showErrorMessage(
          `保存到远端失败: ${result.error?.message || "未知错误"}`,
        );
        return false;
      }

      vscode.window.showInformationMessage(`已同步到远端: ${remotePath}`);
      return true;
    } catch (error) {
      console.error("[FILETREE] 保存文件出错:", error);
      vscode.window.showErrorMessage(`保存文件失败: ${error}`);
      return false;
    }
  }

  // 生成文件树 HTML
  private generateFileTreeHtml(agentId: string): string {
    const visibleNodes = this.getVisibleFileTreeNodes(agentId);
    if (visibleNodes.length === 0) {
      return '<div class="file-tree-empty">点击上方按钮加载文件树</div>';
    }

    return visibleNodes
      .map(({ node, depth }) => {
        const indent = depth * 16;
        const isDir = node.type === "directory";
        const icon = isDir ? (node.expanded ? "📂" : "📁") : "📄";
        const expandArrow = isDir
          ? `<span class="expand-arrow ${node.expanded ? "expanded" : ""}">${node.expanded ? "▼" : "▶"}</span>`
          : '<span class="expand-arrow-placeholder"></span>';

        return `
          <div class="file-tree-node" style="padding-left: ${indent}px;" 
               data-path="${escapeHtml(node.path)}" 
               data-type="${node.type}"
               data-agent-id="${agentId}">
            ${expandArrow}
            <span class="file-icon">${icon}</span>
            <span class="file-name">${escapeHtml(node.name)}</span>
          </div>`;
      })
      .join("");
  }

  // 处理文件树按钮点击
  private async handleToggleFileTree(
    agentId: string,
    workingDir: string,
    nodeId?: string,
  ): Promise<void> {
    if (!agentId || !workingDir) {
      vscode.window.showWarningMessage("无法加载文件树：缺少工作目录信息");
      return;
    }

    // 如果已有文件树，切换展开/收缩状态
    if (this.fileTreeState.has(agentId)) {
      const treeNodes = this.fileTreeState.get(agentId);
      if (treeNodes && treeNodes.length > 0) {
        // 清除文件树（收缩）
        this.fileTreeState.delete(agentId);
        this.fileTreeExpanded.delete(agentId);
      } else {
        // 重新加载
        await this.initFileTree(agentId, workingDir, nodeId);
      }
    } else {
      // 初始化文件树
      await this.initFileTree(agentId, workingDir, nodeId);
    }

    this.renderAgentListView();
  }

  // 处理文件树节点点击
  private async handleToggleFileTreeNode(
    agentId: string,
    nodePath: string,
  ): Promise<void> {
    // 获取 agent 的 nodeId
    const agent = this.agentItems.find((a) => a.id === agentId);
    const nodeId = agent?.nodeId;

    await this.toggleFileTreeNode(agentId, nodePath, nodeId);
    this.renderAgentListView();
  }

  // 处理打开远端文件
  private async handleOpenRemoteFile(
    agentId: string,
    filePath: string,
  ): Promise<void> {
    // 获取 agent 的 nodeId
    const agent = this.agentItems.find((a) => a.id === agentId);
    const nodeId = agent?.nodeId;

    await this.openRemoteFile(agentId, filePath, nodeId);
  }

  // 同步远端文件（公共方法，供 activate 中的事件监听调用）
  public async syncRemoteFile(localPath: string): Promise<void> {
    await this.saveRemoteFile(localPath);
  }

  // 获取远端文件状态
  private async fetchRemoteFileStat(
    filePath: string,
    nodeId: string,
  ): Promise<{ mtime_ns?: number; size?: number } | null> {
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    try {
      const response = await fetch(
        buildNodeHttpUrl(gatewayAddress, nodeId, "file-stat"),
        {
          method: "POST",
          headers: {
            ...this.getAuthHeaders(),
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ path: filePath, node_id: nodeId }),
        },
      );
      const result = await response.json();
      if (!response.ok || !result.success || !result.data) {
        return null;
      }
      return result.data;
    } catch {
      return null;
    }
  }

  // 检查远端文件是否有变化
  private async checkRemoteFileChanges(): Promise<void> {
    // 获取当前活动的编辑器
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) return;

    const localPath = activeEditor.document.uri.fsPath;
    const mapping = this.remoteFileEditors.get(localPath);
    if (!mapping) return;

    const { remotePath, nodeId, mtimeNs, fileSize } = mapping;

    // 获取远端文件状态
    const remoteStat = await this.fetchRemoteFileStat(remotePath, nodeId);
    if (!remoteStat) return;

    const remoteMtimeNs = remoteStat.mtime_ns;
    const remoteFileSize = remoteStat.size;

    // 检查是否有变化
    const hasChange =
      (remoteMtimeNs !== undefined && remoteMtimeNs !== mtimeNs) ||
      (remoteFileSize !== undefined && remoteFileSize !== fileSize);

    if (!hasChange) return;

    // 检查本地是否有未保存的修改
    if (activeEditor.document.isDirty) {
      vscode.window
        .showWarningMessage(
          `远端文件 ${remotePath} 已被修改，但本地有未保存的更改。请先保存或放弃本地更改。`,
          "刷新（丢弃本地更改）",
          "保留本地更改",
        )
        .then(async (choice) => {
          if (choice === "刷新（丢弃本地更改）") {
            await this.refreshRemoteFile(localPath);
          }
        });
      return;
    }

    // 自动刷新
    await this.refreshRemoteFile(localPath);
    vscode.window.showInformationMessage(
      `远端文件 ${remotePath} 已更新，已自动刷新。`,
    );
  }

  // 刷新远端文件内容
  private async refreshRemoteFile(localPath: string): Promise<void> {
    const mapping = this.remoteFileEditors.get(localPath);
    if (!mapping) return;

    const { remotePath, nodeId } = mapping;
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);

    try {
      // 获取最新内容
      const response = await fetch(
        buildNodeHttpUrl(gatewayAddress, nodeId, "file-content"),
        {
          method: "POST",
          headers: {
            ...this.getAuthHeaders(),
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ path: remotePath, node_id: nodeId }),
        },
      );

      const result = await response.json();
      if (!response.ok || !result.success || !result.data) {
        return;
      }

      const content = result.data.content || "";

      // 检查文件是否是只读的，如果是则先改为可写
      const isReadOnly = mapping.readOnly;
      if (isReadOnly) {
        await fs.promises.chmod(localPath, 0o644);
      }

      // 更新本地文件
      await fs.promises.writeFile(localPath, content, "utf-8");

      // 如果原来是只读的，写入后恢复只读
      if (isReadOnly) {
        await fs.promises.chmod(localPath, 0o444);
      }

      // 获取最新的文件状态
      const remoteStat = await this.fetchRemoteFileStat(remotePath, nodeId);
      if (remoteStat) {
        mapping.mtimeNs = remoteStat.mtime_ns;
        mapping.fileSize = remoteStat.size;
      }

      // 重新加载文档
      const document = await vscode.workspace.openTextDocument(localPath);
      await vscode.window.showTextDocument(document, {
        viewColumn: vscode.ViewColumn.One,
        preserveFocus: false,
        preview: false,
      });
    } catch (error) {
      console.error("[FILETREE] 刷新文件出错:", error);
    }
  }

  // 启动远端文件心跳检查
  public startRemoteFileHeartbeat(): void {
    this.stopRemoteFileHeartbeat();
    // 每3秒检查一次
    this.remoteFileHeartbeatTimer = setInterval(() => {
      this.checkRemoteFileChanges();
    }, 3000);
  }

  // 停止远端文件心跳检查
  public stopRemoteFileHeartbeat(): void {
    if (this.remoteFileHeartbeatTimer) {
      clearInterval(this.remoteFileHeartbeatTimer);
      this.remoteFileHeartbeatTimer = undefined;
    }
  }

  // 显示远端文件状态栏按钮
  private showRemoteFileStatusBar(
    remotePath: string,
    isReadOnly: boolean,
  ): void {
    if (!this.readOnlyStatusBarItem) {
      this.readOnlyStatusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left,
        100, // 高优先级，显示在左边显眼位置
      );
    }

    if (isReadOnly) {
      this.readOnlyStatusBarItem.text = "$(lock) 只读模式 - 点击开启编辑";
      this.readOnlyStatusBarItem.tooltip = `远端文件: ${remotePath}\n点击开启编辑模式`;
      this.readOnlyStatusBarItem.backgroundColor = new vscode.ThemeColor(
        "statusBarItem.warningBackground",
      );
      this.readOnlyStatusBarItem.command = "jarvis.enableRemoteFileEdit";
    } else {
      this.readOnlyStatusBarItem.text = "$(unlock) 编辑模式 - 点击恢复只读";
      this.readOnlyStatusBarItem.tooltip = `远端文件: ${remotePath}\n保存时将同步到远端\n点击恢复只读模式`;
      this.readOnlyStatusBarItem.backgroundColor = new vscode.ThemeColor(
        "statusBarItem.prominentBackground",
      );
      this.readOnlyStatusBarItem.command = "jarvis.disableRemoteFileEdit";
    }
    this.readOnlyStatusBarItem.color = new vscode.ThemeColor(
      "statusBarItem.warningForeground",
    );
    this.readOnlyStatusBarItem.show();
  }

  // 隐藏远端文件状态栏按钮
  private hideRemoteFileStatusBar(): void {
    if (this.readOnlyStatusBarItem) {
      this.readOnlyStatusBarItem.hide();
    }
  }

  // 更新状态栏（根据当前活动编辑器）
  public updateReadOnlyStatusBar(): void {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      this.hideRemoteFileStatusBar();
      return;
    }

    const localPath = activeEditor.document.uri.fsPath;
    const mapping = this.remoteFileEditors.get(localPath);

    if (mapping) {
      this.showRemoteFileStatusBar(mapping.remotePath, mapping.readOnly);
    } else {
      this.hideRemoteFileStatusBar();
    }
  }

  // 开启远端文件编辑模式
  public async enableRemoteFileEdit(): Promise<void> {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      vscode.window.showWarningMessage("没有打开的文件");
      return;
    }

    const localPath = activeEditor.document.uri.fsPath;
    const mapping = this.remoteFileEditors.get(localPath);
    if (!mapping) {
      vscode.window.showWarningMessage("当前文件不是远端文件");
      return;
    }

    if (!mapping.readOnly) {
      vscode.window.showInformationMessage("当前文件已经是可编辑状态");
      return;
    }

    try {
      // 将文件权限改为可写（权限 644）
      await fs.promises.chmod(localPath, 0o644);
      mapping.readOnly = false;

      // 更新状态栏显示为编辑模式
      this.showRemoteFileStatusBar(mapping.remotePath, false);

      // 重新打开文件以刷新编辑器状态
      const document = await vscode.workspace.openTextDocument(localPath);
      await vscode.window.showTextDocument(document, {
        viewColumn: vscode.ViewColumn.One,
        preserveFocus: false,
        preview: false,
      });

      vscode.window.showInformationMessage(
        `已开启编辑模式: ${mapping.remotePath} (保存时将同步到远端)`,
      );
    } catch (error) {
      console.error("[FILETREE] 开启编辑模式失败:", error);
      vscode.window.showErrorMessage(`开启编辑模式失败: ${error}`);
    }
  }

  // 恢复远端文件只读模式
  public async disableRemoteFileEdit(): Promise<void> {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      vscode.window.showWarningMessage("没有打开的文件");
      return;
    }

    const localPath = activeEditor.document.uri.fsPath;
    const mapping = this.remoteFileEditors.get(localPath);
    if (!mapping) {
      vscode.window.showWarningMessage("当前文件不是远端文件");
      return;
    }

    if (mapping.readOnly) {
      vscode.window.showInformationMessage("当前文件已经是只读状态");
      return;
    }

    // 检查是否有未保存的修改
    if (activeEditor.document.isDirty) {
      const choice = await vscode.window.showWarningMessage(
        "当前文件有未保存的修改，恢复只读将丢弃这些修改。",
        "保存并恢复只读",
        "丢弃修改并恢复只读",
        "取消",
      );
      if (choice === "保存并恢复只读") {
        await activeEditor.document.save();
      } else if (choice === "丢弃修改并恢复只读") {
        // 重新加载文件内容
        await vscode.commands.executeCommand("workbench.action.files.revert");
      } else {
        return;
      }
    }

    try {
      // 将文件权限改为只读（权限 444）
      await fs.promises.chmod(localPath, 0o444);
      mapping.readOnly = true;

      // 更新状态栏显示为只读模式
      this.showRemoteFileStatusBar(mapping.remotePath, true);

      // 重新打开文件以刷新编辑器状态
      const document = await vscode.workspace.openTextDocument(localPath);
      await vscode.window.showTextDocument(document, {
        viewColumn: vscode.ViewColumn.One,
        preserveFocus: false,
        preview: false,
      });

      vscode.window.showInformationMessage(
        `已恢复只读模式: ${mapping.remotePath}`,
      );
    } catch (error) {
      console.error("[FILETREE] 恢复只读模式失败:", error);
      vscode.window.showErrorMessage(`恢复只读模式失败: ${error}`);
    }
  }

  // ========== 文件树功能结束 ==========

  private async loginWithPassword(password: string): Promise<string> {
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    const response = await fetch(
      buildHttpUrl(gatewayAddress, "/api/auth/login"),
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ password }),
      },
    );
    const result = (await response.json()) as LoginResponse;
    if (!response.ok || !result.success || !result.data?.token) {
      throw new Error(result.error?.message || "登录失败");
    }
    return result.data.token;
  }

  // 获取认证头
  private getAuthHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};
    if (this.panelState.token) {
      headers["Authorization"] = `Bearer ${this.panelState.token}`;
    }
    return headers;
  }

  private async fetchWithAuth(
    url: string,
    init?: RequestInit,
  ): Promise<Response> {
    const headers = new Headers(init?.headers || {});
    if (this.panelState.token) {
      headers.set("Authorization", `Bearer ${this.panelState.token}`);
    }
    if (init?.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(url, {
      ...init,
      headers,
    });
    if (
      this.panelState.token &&
      (response.status === 401 || response.status === 403)
    ) {
      this.handleAuthExpired("登录已失效，请重新连接 Jarvis");
    }
    return response;
  }

  private isInvalidTokenMessage(message: string): boolean {
    const normalizedMessage = String(message || "").toLowerCase();
    return (
      normalizedMessage.includes("invalid token") ||
      normalizedMessage.includes("token invalid") ||
      normalizedMessage.includes("token expired") ||
      normalizedMessage.includes("jwt expired") ||
      normalizedMessage.includes("unauthorized") ||
      normalizedMessage.includes("认证失败") ||
      normalizedMessage.includes("登录失效") ||
      normalizedMessage.includes("令牌失效")
    );
  }

  private handleAuthExpired(message: string): void {
    if (!this.panelState.token) {
      return;
    }
    this.stopAgentListRefresh();
    this.disposeSocket("gatewaySocket");
    for (const socket of this.agentSockets.values()) {
      try {
        socket.close();
      } catch {
        // ignore close error
      }
    }
    this.agentSockets.clear();
    this.agentConnectionAttempts.clear();
    // 关闭右侧 Chat Panel
    if (this.currentPanel) {
      this.currentPanel.dispose();
      this.currentPanel = undefined;
    }
    this.panelState.token = "";
    this.panelState.selectedAgentId = undefined;
    this.panelState.gatewaySocket = undefined;
    // 清理所有 agent 状态
    this.agentStatuses.clear();
    this.panelState.gatewayConnectionStatusText = message;
    this.panelState.gatewayHasConnectionError = true;
    this.leftViewLoginState.errorMessage = message;
    this.leftViewLoginState.isSubmitting = false;
    this.postPanelState();
    this.renderAgentListView();
  }

  private async loadModelGroups(nodeId?: string): Promise<void> {
    if (!this.panelState.token) {
      return;
    }
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    const targetNodeId = String(nodeId || "master").trim() || "master";
    const response = await this.fetchWithAuth(
      buildNodeHttpUrl(gatewayAddress, targetNodeId, "model-groups"),
    );
    const result = (await response.json()) as ModelGroupsResponse;
    if (!response.ok || !result.success) {
      throw new Error(result.error?.message || "获取模型组失败");
    }
    this.modelGroups = Array.isArray(result.data)
      ? result.data.map((group) => ({
          name: group.name,
          smartModel: group.smart_model || "-",
          normalModel: group.normal_model || "-",
          cheapModel: group.cheap_model || "-",
        }))
      : [];
    this.defaultLlmGroup = String(result.default_llm_group || "").trim();
    const fallbackGroup = this.modelGroups[0]?.name || "";
    const resolvedDefaultGroup = this.defaultLlmGroup || fallbackGroup;
    if (resolvedDefaultGroup) {
      this.createAgentFormState.llmGroup = resolvedDefaultGroup;
    }
  }

  private async loadNodeOptions(): Promise<void> {
    if (!this.panelState.token) {
      this.availableNodeOptions = [];
      return;
    }
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    const response = await this.fetchWithAuth(
      buildNodeHttpUrl(gatewayAddress, "master", "node/status"),
    );
    const result = (await response.json()) as {
      success?: boolean;
      data?: {
        nodes?: Array<{
          node_id?: string;
          status?: string;
          runtime_status?: string;
        }>;
      };
      error?: { message?: string };
    };
    if (!response.ok || !result.success) {
      throw new Error(result.error?.message || "获取节点状态失败");
    }
    const nodes = Array.isArray(result.data?.nodes) ? result.data?.nodes : [];
    this.availableNodeOptions = nodes
      .map((node) => ({
        nodeId: String(node?.node_id || "").trim(),
        status:
          String(node?.status || node?.runtime_status || "").trim() ||
          undefined,
      }))
      .filter((node) => Boolean(node.nodeId));
  }

  /**
   * 重启节点服务
   * 使用面板状态中的 restartNodeId 和 restartFrontendService
   */
  public async restartNodeService(): Promise<void> {
    if (!this.panelState.token) {
      vscode.window.showErrorMessage("请先连接并登录 Jarvis 网关");
      return;
    }

    // 防止重复点击
    if (this.panelState.isRestartingService) {
      return;
    }

    // 从面板状态获取参数
    const targetNodeId = this.panelState.restartNodeId || "master";
    const shouldRestartFrontend =
      targetNodeId === "master"
        ? this.panelState.restartFrontendService
        : false;

    // 检查是否有运行中的agent
    const runningAgents = this.agentItems.filter(
      (agent) => agent.statusClass === "running",
    );
    if (runningAgents.length > 0) {
      const agentNames = runningAgents
        .map((agent) => agent.displayName || agent.id)
        .join(", ");
      vscode.window.showWarningMessage(
        `检测到 ${runningAgents.length} 个运行中的 Agent：${agentNames}\n\n请先手动停止或完成这些 Agent 后再重启节点服务`,
        { modal: true },
      );
      return;
    }

    // 确认重启
    const confirmMessage =
      targetNodeId === "master"
        ? `确认重启本节点服务吗？这将短暂中断当前连接。`
        : `确认重启节点 "${targetNodeId}" 的服务吗？这将短暂中断该节点的连接。`;

    const confirmed = await vscode.window.showWarningMessage(
      confirmMessage,
      { modal: true },
      "确认重启",
    );

    if (confirmed !== "确认重启") {
      return;
    }

    // 设置重启中状态
    this.panelState.isRestartingService = true;
    this.renderAgentListView();

    // 发送重启请求
    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
      // 发送重启请求，不等待响应结果（服务重启会导致连接中断）
      this.fetchWithAuth(
        buildNodeHttpUrl(gatewayAddress, "master", "service/restart"),
        {
          method: "POST",
          body: JSON.stringify({
            node_id: targetNodeId,
            restart_frontend: shouldRestartFrontend,
          }),
        },
      ).catch(() => {
        // 忽略请求错误（服务重启会导致连接中断）
      });

      vscode.window.showInformationMessage(
        `已向节点 "${targetNodeId}" 发送重启请求`,
      );
    } catch (error) {
      vscode.window.showErrorMessage(`重启服务失败: ${getErrorMessage(error)}`);
    } finally {
      // 重置重启中状态
      this.panelState.isRestartingService = false;
      this.renderAgentListView();
    }
  }

  private async setConnectionLockEnabled(enabled: boolean): Promise<void> {
    this.panelState.connectionLockEnabled = enabled;
    await this.saveConnectionInfo();
    const gatewaySocket = this.panelState.gatewaySocket;
    if (gatewaySocket && gatewaySocket.readyState === WebSocket.OPEN) {
      this.sendSocketMessage(gatewaySocket, {
        type: "connection_lock",
        payload: { enabled },
      });
    }
    this.renderAgentListView();
  }

  private postPanelStateImmediate(): void {
    if (!this.currentPanel) {
      return;
    }
    const agentStatus = this.getSelectedAgentStatus();
    this.currentPanel.webview.postMessage({
      type: "state",
      payload: {
        gatewayUrl: this.panelState.gatewayUrl,
        password: this.panelState.password,
        selectedAgentId: this.panelState.selectedAgentId,
        statusText: agentStatus?.connection_status_text || "",
        isError: agentStatus?.has_connection_error || false,
        terminalOutput: agentStatus?.terminal_output || "暂无终端输出",
        inputMode: agentStatus?.input_mode || "multi",
        inputTip: agentStatus?.input_tip || "",
        executionStatus: agentStatus?.execution_status || "stopped",
        messages: agentStatus?.messages || [],
      },
    });
    console.log(
      "[POST STATE]",
      this.panelState.selectedAgentId,
      agentStatus?.execution_status,
    );
  }

  private postPanelState = throttle(() => {
    this.postPanelStateImmediate();
  }, 100);

  private renderAgentListViewImmediate(): void {
    if (!this.currentView) {
      return;
    }
    this.currentView.webview.html = this.getAgentListHtml();
  }

  private renderAgentListView = debounce(() => {
    this.renderAgentListViewImmediate();
  }, 100);

  private async connectFromLeftView(
    message: AgentListViewMessage,
  ): Promise<void> {
    const gatewayUrl = String(message.gatewayUrl || "").trim();
    const password = String(message.password || "");
    this.leftViewLoginState.isSubmitting = true;
    this.leftViewLoginState.errorMessage = "";
    this.renderAgentListView();

    try {
      await this.connectToGateway(gatewayUrl, password);
    } catch {
      // error state handled in connectToGateway
    } finally {
      this.leftViewLoginState.isSubmitting = false;
      this.renderAgentListView();
    }
  }

  private async toggleCreateAgentForm(): Promise<void> {
    this.createAgentFormState.isVisible = !this.createAgentFormState.isVisible;
    this.createAgentFormState.errorMessage = "";
    // 打开表单时，加载当前选择节点的模型组列表
    if (this.createAgentFormState.isVisible) {
      try {
        await this.loadModelGroups(
          this.createAgentFormState.nodeId || undefined,
        );
      } catch {
        // keep current model groups on failure
      }
    }
    this.renderAgentListView();
  }

  private async pickWorkingDirectory(): Promise<void> {
    this.remoteDirectoryBrowserState.isVisible = true;
    this.remoteDirectoryBrowserState.errorMessage = "";
    this.remoteDirectoryBrowserState.selectedIndex = -1;
    this.remoteDirectoryBrowserState.searchText = "";
    await this.loadRemoteDirectories(
      this.createAgentFormState.workingDir || "~",
    );
  }

  private async loadRemoteDirectories(path?: string): Promise<void> {
    if (!this.panelState.token) {
      this.remoteDirectoryBrowserState.isVisible = true;
      this.remoteDirectoryBrowserState.errorMessage =
        "请先连接并登录 Jarvis 网关";
      this.renderAgentListView();
      return;
    }
    const requestedPath =
      String(
        path ||
          this.remoteDirectoryBrowserState.selectedPath ||
          this.createAgentFormState.workingDir ||
          "~",
      ).trim() || "~";
    const targetNodeId = String(this.createAgentFormState.nodeId || "").trim();
    this.remoteDirectoryBrowserState.isVisible = true;
    this.remoteDirectoryBrowserState.isLoading = true;
    this.remoteDirectoryBrowserState.errorMessage = "";
    this.renderAgentListView();
    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
      const response = await this.fetchWithAuth(
        buildHttpUrl(
          gatewayAddress,
          `/api/node/${encodeURIComponent(String(targetNodeId || "master").trim() || "master")}/directories?path=${encodeURIComponent(requestedPath)}`,
        ),
      );
      const result = (await response.json()) as {
        success?: boolean;
        data?: { current_path?: string; items?: RemoteDirectoryItem[] };
        error?: { message?: string };
      };
      if (!response.ok || !result.success || !result.data) {
        throw new Error(result.error?.message || "获取目录列表失败");
      }
      const directoryItems = Array.isArray(result.data.items)
        ? result.data.items.filter((item) => item?.type === "directory")
        : [];
      this.remoteDirectoryBrowserState.currentPath = String(
        result.data.current_path || requestedPath,
      );
      this.remoteDirectoryBrowserState.selectedPath =
        this.remoteDirectoryBrowserState.currentPath;
      this.remoteDirectoryBrowserState.selectedIndex = -1;
      this.remoteDirectoryBrowserState.searchText = "";
      this.remoteDirectoryBrowserState.items = directoryItems.map((item) => ({
        name: String(item.name || item.path || ""),
        path: String(item.path || ""),
        type: String(item.type || "directory"),
      }));
    } catch (error) {
      this.remoteDirectoryBrowserState.errorMessage = getErrorMessage(error);
      this.remoteDirectoryBrowserState.items = [];
    } finally {
      this.remoteDirectoryBrowserState.isLoading = false;
      this.renderAgentListView();
    }
  }

  private selectRemoteDirectory(path?: string): void {
    const selectedPath = String(path || "").trim();
    if (!selectedPath) {
      return;
    }
    this.remoteDirectoryBrowserState.selectedPath = selectedPath;
    this.remoteDirectoryBrowserState.selectedIndex =
      this.getFilteredRemoteDirectoryItems().findIndex(
        (item) => item.path === selectedPath,
      );
    this.renderAgentListView();
  }

  private updateRemoteDirectorySearch(searchText?: string): void {
    this.remoteDirectoryBrowserState.searchText = String(searchText || "");
    this.remoteDirectoryBrowserState.selectedIndex = -1;
    this.renderAgentListView();
  }

  private getFilteredRemoteDirectoryItems(): RemoteDirectoryItem[] {
    const normalizedSearchText = this.remoteDirectoryBrowserState.searchText
      .toLowerCase()
      .trim();
    if (!normalizedSearchText) {
      return this.remoteDirectoryBrowserState.items;
    }
    return this.remoteDirectoryBrowserState.items.filter(
      (item) =>
        item.name.toLowerCase().includes(normalizedSearchText) ||
        item.path.toLowerCase().includes(normalizedSearchText),
    );
  }

  private async handleRemoteDirectoryKeydown(key?: string): Promise<void> {
    const filteredItems = this.getFilteredRemoteDirectoryItems();
    const maxIndex = filteredItems.length - 1;

    if (key === "Escape") {
      this.closeRemoteDirectoryBrowser();
      return;
    }

    if (key === "ArrowDown") {
      if (this.remoteDirectoryBrowserState.selectedIndex < maxIndex) {
        this.remoteDirectoryBrowserState.selectedIndex += 1;
      } else if (this.remoteDirectoryBrowserState.selectedIndex === -1) {
        this.remoteDirectoryBrowserState.selectedIndex = 0;
      }
      if (
        this.remoteDirectoryBrowserState.selectedIndex >= 0 &&
        this.remoteDirectoryBrowserState.selectedIndex <= maxIndex
      ) {
        this.remoteDirectoryBrowserState.selectedPath =
          filteredItems[this.remoteDirectoryBrowserState.selectedIndex].path;
      }
      this.renderAgentListView();
      return;
    }

    if (key === "ArrowUp") {
      if (this.remoteDirectoryBrowserState.selectedIndex > 0) {
        this.remoteDirectoryBrowserState.selectedIndex -= 1;
      } else if (this.remoteDirectoryBrowserState.selectedIndex === -1) {
        this.remoteDirectoryBrowserState.selectedIndex = maxIndex;
      } else {
        this.remoteDirectoryBrowserState.selectedIndex = -1;
      }
      if (
        this.remoteDirectoryBrowserState.selectedIndex >= 0 &&
        this.remoteDirectoryBrowserState.selectedIndex <= maxIndex
      ) {
        this.remoteDirectoryBrowserState.selectedPath =
          filteredItems[this.remoteDirectoryBrowserState.selectedIndex].path;
      }
      this.renderAgentListView();
      return;
    }

    if (key === "Enter") {
      if (
        this.remoteDirectoryBrowserState.selectedIndex >= 0 &&
        this.remoteDirectoryBrowserState.selectedIndex <= maxIndex
      ) {
        await this.loadRemoteDirectories(
          filteredItems[this.remoteDirectoryBrowserState.selectedIndex].path,
        );
        return;
      }
      this.confirmRemoteDirectorySelection();
    }
  }

  private getParentDirectoryPath(): string {
    const currentPath =
      String(
        this.remoteDirectoryBrowserState.currentPath ||
          this.createAgentFormState.workingDir ||
          "~",
      ).trim() || "~";
    if (currentPath === "~" || currentPath === "/") {
      return currentPath;
    }
    const normalizedPath =
      currentPath.endsWith("/") && currentPath.length > 1
        ? currentPath.slice(0, -1)
        : currentPath;
    const lastSeparatorIndex = normalizedPath.lastIndexOf("/");
    if (lastSeparatorIndex <= 0) {
      return normalizedPath.startsWith("~/") ? "~" : "/";
    }
    return normalizedPath.slice(0, lastSeparatorIndex);
  }

  private confirmRemoteDirectorySelection(): void {
    const selectedPath = String(
      this.remoteDirectoryBrowserState.currentPath ||
        this.remoteDirectoryBrowserState.selectedPath ||
        "",
    ).trim();
    if (!selectedPath) {
      this.remoteDirectoryBrowserState.errorMessage = "请选择工作目录";
      this.renderAgentListView();
      return;
    }
    this.createAgentFormState.workingDir = selectedPath;
    this.createAgentFormState.errorMessage = "";
    this.closeRemoteDirectoryBrowser();
  }

  private closeRemoteDirectoryBrowser(): void {
    this.remoteDirectoryBrowserState.isVisible = false;
    this.remoteDirectoryBrowserState.isLoading = false;
    this.remoteDirectoryBrowserState.errorMessage = "";
    this.remoteDirectoryBrowserState.selectedIndex = -1;
    this.remoteDirectoryBrowserState.searchText = "";
    this.renderAgentListView();
  }

  private resetCreateAgentForm(): void {
    this.createAgentFormState.isVisible = false;
    this.createAgentFormState.agentType = "agent";
    this.createAgentFormState.workingDir = "~";
    this.createAgentFormState.name = "通用Agent";
    this.createAgentFormState.llmGroup =
      this.defaultLlmGroup || this.modelGroups[0]?.name || "";
    this.createAgentFormState.nodeId = "";
    this.createAgentFormState.useWorktree = false;
    this.createAgentFormState.quickMode = false;
    this.createAgentFormState.isSubmitting = false;
    this.createAgentFormState.errorMessage = "";
    this.remoteDirectoryBrowserState.isVisible = false;
    this.remoteDirectoryBrowserState.currentPath = "~";
    this.remoteDirectoryBrowserState.selectedPath = "~";
    this.remoteDirectoryBrowserState.selectedIndex = -1;
    this.remoteDirectoryBrowserState.searchText = "";
    this.remoteDirectoryBrowserState.items = [];
    this.remoteDirectoryBrowserState.isLoading = false;
    this.remoteDirectoryBrowserState.errorMessage = "";
  }

  private updateCreateAgentDefaults(agentType: "agent" | "codeagent"): void {
    this.createAgentFormState.agentType = agentType;
    this.createAgentFormState.name =
      agentType === "codeagent" ? "代码Agent" : "通用Agent";
    if (agentType !== "codeagent") {
      this.createAgentFormState.useWorktree = false;
    }
  }

  private async copyAgent(agentId?: string): Promise<void> {
    if (!this.panelState.token) {
      vscode.window.showErrorMessage("请先连接并登录 Jarvis 网关");
      return;
    }
    const sourceAgent = this.agentItems.find((item) => item.id === agentId);
    if (!sourceAgent) {
      vscode.window.showErrorMessage("未找到要复制的 Agent");
      return;
    }
    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
      const normalizedNodeId =
        String(sourceAgent.nodeId || "master").trim() || "master";
      const response = await this.fetchWithAuth(
        buildNodeHttpUrl(gatewayAddress, normalizedNodeId, "agents"),
        {
          method: "POST",
          body: JSON.stringify({
            agent_type: sourceAgent.agentType,
            working_dir: sourceAgent.workingDir,
            name: sourceAgent.name || undefined,
            llm_group:
              sourceAgent.llmGroup || this.defaultLlmGroup || undefined,
            node_id: normalizedNodeId,
            worktree:
              sourceAgent.agentType === "codeagent"
                ? sourceAgent.worktree
                : false,
            quick_mode: Boolean(sourceAgent.quickMode),
          }),
        },
      );
      const result = (await response.json()) as CreateAgentResponse;
      if (!response.ok || !result.success || !result.data?.agent_id) {
        throw new Error(result.error?.message || "复制 Agent 失败");
      }
      this.panelState.selectedAgentId = result.data.agent_id;
      await this.refreshAgents();
      this.renderAgentListView();
      this.appendPanelMessage(
        `已复制 Agent：${result.data.name || result.data.agent_id}`,
        "system",
      );
      await this.openChatPanel(result.data.agent_id);
    } catch (error) {
      vscode.window.showErrorMessage(getErrorMessage(error));
    }
  }

  private async deleteAgent(agentId?: string): Promise<void> {
    if (!this.panelState.token) {
      vscode.window.showErrorMessage("请先连接并登录 Jarvis 网关");
      return;
    }
    if (!agentId) {
      vscode.window.showErrorMessage("未找到要删除的 Agent");
      return;
    }
    const confirmed = await vscode.window.showWarningMessage(
      "确认删除该 Agent？删除后将无法恢复。",
      { modal: true },
      "删除",
    );
    if (confirmed !== "删除") {
      return;
    }
    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
      const targetNodeId =
        this.agentItems.find((item) => item.id === agentId)?.nodeId || "";
      const normalizedNodeId =
        String(targetNodeId || "master").trim() || "master";
      const response = await this.fetchWithAuth(
        buildNodeHttpUrl(gatewayAddress, normalizedNodeId, `agents/${agentId}`),
        {
          method: "DELETE",
        },
      );
      const result = (await response.json()) as DeleteAgentResponse;
      if (!response.ok || !result.success) {
        throw new Error(result.error?.message || "删除 Agent 失败");
      }
      if (this.panelState.selectedAgentId === agentId) {
        this.panelState.selectedAgentId = undefined;
      }
      this.agentStatuses.delete(agentId);
      await this.clearPersistedAgentHistory(agentId);
      await this.refreshAgents();
      this.renderAgentListView();
      this.appendPanelMessage(`已删除 Agent：${agentId}`, "system");
      if (this.currentPanel) {
        this.currentPanel.title = this.getChatPanelTitle();
        this.currentPanel.webview.html = this.getChatPanelHtml(
          this.panelState.selectedAgentId,
        );
        this.postPanelState();
      }
    } catch (error) {
      vscode.window.showErrorMessage(getErrorMessage(error));
    }
  }

  // ========== 批量操作方法 ==========

  private toggleBatchMode(): void {
    this.isBatchMode = !this.isBatchMode;
    if (!this.isBatchMode) {
      this.selectedAgents.clear();
    }
    this.renderAgentListView();
  }

  private toggleSelectAgent(agentId: string): void {
    if (this.selectedAgents.has(agentId)) {
      this.selectedAgents.delete(agentId);
    } else {
      this.selectedAgents.add(agentId);
    }
    this.renderAgentListView();
  }

  private isAllSelected(): boolean {
    if (this.agentItems.length === 0) return false;
    return this.agentItems.every((item) => this.selectedAgents.has(item.id));
  }

  private toggleSelectAll(): void {
    if (this.isAllSelected()) {
      this.selectedAgents.clear();
    } else {
      this.agentItems.forEach((item) => this.selectedAgents.add(item.id));
    }
    this.renderAgentListView();
  }

  private async batchCopyAgents(): Promise<void> {
    if (!this.panelState.token) {
      vscode.window.showErrorMessage("请先连接并登录 Jarvis 网关");
      return;
    }
    if (this.selectedAgents.size === 0) {
      vscode.window.showWarningMessage("请先选择要复制的 Agent");
      return;
    }

    const confirmed = await vscode.window.showInformationMessage(
      `确认复制选中的 ${this.selectedAgents.size} 个 Agent？`,
      { modal: true },
      "复制",
    );
    if (confirmed !== "复制") {
      return;
    }

    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    let successCount = 0;
    let failCount = 0;

    for (const agentId of this.selectedAgents) {
      const sourceAgent = this.agentItems.find((item) => item.id === agentId);
      if (!sourceAgent) {
        failCount++;
        continue;
      }
      try {
        const normalizedNodeId =
          String(sourceAgent.nodeId || "master").trim() || "master";
        const response = await this.fetchWithAuth(
          buildNodeHttpUrl(gatewayAddress, normalizedNodeId, "agents"),
          {
            method: "POST",
            body: JSON.stringify({
              agent_type: sourceAgent.agentType,
              working_dir: sourceAgent.workingDir,
              name: sourceAgent.name || undefined,
              llm_group:
                sourceAgent.llmGroup || this.defaultLlmGroup || undefined,
              node_id: normalizedNodeId,
              worktree:
                sourceAgent.agentType === "codeagent"
                  ? sourceAgent.worktree
                  : false,
              quick_mode: Boolean(sourceAgent.quickMode),
            }),
          },
        );
        const result = (await response.json()) as CreateAgentResponse;
        if (response.ok && result.success && result.data?.agent_id) {
          successCount++;
        } else {
          failCount++;
        }
      } catch {
        failCount++;
      }
    }

    await this.refreshAgents();
    this.selectedAgents.clear();
    this.isBatchMode = false;
    this.renderAgentListView();

    if (failCount === 0) {
      vscode.window.showInformationMessage(`成功复制 ${successCount} 个 Agent`);
    } else {
      vscode.window.showWarningMessage(
        `复制完成：成功 ${successCount} 个，失败 ${failCount} 个`,
      );
    }
  }

  private async batchDeleteAgents(): Promise<void> {
    if (!this.panelState.token) {
      vscode.window.showErrorMessage("请先连接并登录 Jarvis 网关");
      return;
    }
    if (this.selectedAgents.size === 0) {
      vscode.window.showWarningMessage("请先选择要删除的 Agent");
      return;
    }

    const confirmed = await vscode.window.showWarningMessage(
      `确认删除选中的 ${this.selectedAgents.size} 个 Agent？删除后将无法恢复。`,
      { modal: true },
      "删除",
    );
    if (confirmed !== "删除") {
      return;
    }

    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    let successCount = 0;
    let failCount = 0;

    for (const agentId of this.selectedAgents) {
      try {
        const targetNodeId =
          this.agentItems.find((item) => item.id === agentId)?.nodeId || "";
        const normalizedNodeId =
          String(targetNodeId || "master").trim() || "master";
        const response = await this.fetchWithAuth(
          buildNodeHttpUrl(
            gatewayAddress,
            normalizedNodeId,
            `agents/${agentId}`,
          ),
          {
            method: "DELETE",
          },
        );
        const result = (await response.json()) as DeleteAgentResponse;
        if (response.ok && result.success) {
          successCount++;
          if (this.panelState.selectedAgentId === agentId) {
            this.panelState.selectedAgentId = undefined;
          }
          this.agentStatuses.delete(agentId);
          await this.clearPersistedAgentHistory(agentId);
        } else {
          failCount++;
        }
      } catch {
        failCount++;
      }
    }

    await this.refreshAgents();
    this.selectedAgents.clear();
    this.isBatchMode = false;
    this.renderAgentListView();

    if (this.currentPanel) {
      this.currentPanel.title = this.getChatPanelTitle();
      this.currentPanel.webview.html = this.getChatPanelHtml(
        this.panelState.selectedAgentId,
      );
      this.postPanelState();
    }

    if (failCount === 0) {
      vscode.window.showInformationMessage(`成功删除 ${successCount} 个 Agent`);
    } else {
      vscode.window.showWarningMessage(
        `删除完成：成功 ${successCount} 个，失败 ${failCount} 个`,
      );
    }
  }

  // ========== 批量操作方法结束 ==========

  private async createAgent(message: AgentListViewMessage): Promise<void> {
    if (!this.panelState.token) {
      this.createAgentFormState.isVisible = true;
      this.createAgentFormState.errorMessage = "请先连接并登录 Jarvis 网关";
      this.renderAgentListView();
      return;
    }

    const requestedAgentType =
      message.agentType === "codeagent" ? "codeagent" : "agent";
    const workingDir = String(message.workingDir || "").trim();
    const agentName = String(message.name || "").trim();
    const llmGroup =
      String(message.llmGroup || "").trim() ||
      this.defaultLlmGroup ||
      this.modelGroups[0]?.name ||
      "";
    const nodeId = String(message.nodeId || "").trim();
    const useWorktree =
      requestedAgentType === "codeagent" ? Boolean(message.useWorktree) : false;
    const quickMode = Boolean(message.quickMode);

    this.updateCreateAgentDefaults(requestedAgentType);
    this.createAgentFormState.workingDir = workingDir;
    this.createAgentFormState.name =
      agentName || this.createAgentFormState.name;
    this.createAgentFormState.llmGroup = llmGroup;
    this.createAgentFormState.nodeId = nodeId;
    this.createAgentFormState.useWorktree = useWorktree;
    this.createAgentFormState.quickMode = quickMode;
    this.createAgentFormState.isVisible = true;

    if (!workingDir) {
      this.createAgentFormState.errorMessage = "工作目录不能为空";
      this.renderAgentListView();
      return;
    }
    if (!llmGroup) {
      this.createAgentFormState.errorMessage = "模型组不能为空";
      this.renderAgentListView();
      return;
    }

    this.createAgentFormState.isSubmitting = true;
    this.createAgentFormState.errorMessage = "";
    this.renderAgentListView();

    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
      const normalizedNodeId = String(nodeId || "master").trim() || "master";
      const response = await this.fetchWithAuth(
        buildNodeHttpUrl(gatewayAddress, normalizedNodeId, "agents"),
        {
          method: "POST",
          body: JSON.stringify({
            agent_type: requestedAgentType,
            working_dir: workingDir,
            name: agentName || undefined,
            llm_group: llmGroup,
            node_id: normalizedNodeId,
            worktree: useWorktree,
            quick_mode: quickMode,
          }),
        },
      );
      const result = (await response.json()) as CreateAgentResponse;
      if (!response.ok || !result.success || !result.data?.agent_id) {
        throw new Error(result.error?.message || "创建 Agent 失败");
      }

      this.panelState.selectedAgentId = result.data.agent_id;
      this.resetCreateAgentForm();
      await this.refreshAgents();
      this.renderAgentListView();
      this.appendPanelMessage(
        `已创建 Agent：${result.data.name || result.data.agent_id}`,
        "system",
      );
      await this.openChatPanel(result.data.agent_id);
      void this.connectAgentSocket(result.data.agent_id);
    } catch (error) {
      this.createAgentFormState.isSubmitting = false;
      this.createAgentFormState.errorMessage = getErrorMessage(error);
      this.renderAgentListView();
    }
  }

  private getExecutionStatusLabel(
    status: "running" | "waiting_single" | "waiting_multi" | "stopped",
  ): string {
    if (status === "waiting_single") {
      return "等待单行输入";
    }
    if (status === "waiting_multi") {
      return "等待多行输入";
    }
    if (status === "stopped") {
      return "已完成";
    }
    return "运行中";
  }

  private getAgentDisplayLabel(agentId?: string): string {
    const resolvedAgentId = String(agentId || "").trim();
    if (!resolvedAgentId) {
      return "未选择 Agent";
    }
    const matchedAgent = this.agentItems.find(
      (item) => item.id === resolvedAgentId,
    );
    const displayName = String(
      matchedAgent?.displayName || matchedAgent?.name || resolvedAgentId,
    ).trim();
    if (!displayName || displayName === resolvedAgentId) {
      return resolvedAgentId;
    }
    return `${displayName} (${resolvedAgentId})`;
  }

  private getChatPanelTitle(): string {
    return this.panelState.selectedAgentId
      ? `Jarvis · ${this.getAgentDisplayLabel(this.panelState.selectedAgentId)}`
      : "Jarvis";
  }

  private connectGatewaySocket(): void {
    this.disposeSocket("gatewaySocket");
    this.panelState.gatewayConnectionStatusText = "主网关连接中...";
    this.panelState.gatewayHasConnectionError = false;
    this.renderAgentListView();
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    const socketUrl = buildWebSocketUrl(gatewayAddress);
    const gatewaySocket = new WebSocket(
      socketUrl,
      buildWebSocketProtocols(this.panelState.token),
    );

    gatewaySocket.on("open", () => {
      this.panelState.gatewayConnectionStatusText = "主网关已连接";
      this.panelState.gatewayHasConnectionError = false;
      this.sendSocketMessage(gatewaySocket, {
        type: "connection_lock",
        payload: { enabled: this.panelState.connectionLockEnabled },
      });
      this.postPanelState();
    });

    gatewaySocket.on("message", (data: RawData) => {
      this.handleGatewaySocketMessage(data);
    });

    gatewaySocket.on("error", () => {
      this.panelState.gatewayConnectionStatusText = "主网关连接异常";
      this.panelState.gatewayHasConnectionError = true;
      this.postPanelState();
    });

    gatewaySocket.on("close", () => {
      this.panelState.gatewayConnectionStatusText = "主网关已断开连接";
      this.panelState.gatewayHasConnectionError = true;
      this.handleAuthExpired("主网关已断开连接，请重新连接");
    });

    this.panelState.gatewaySocket = gatewaySocket;
  }

  private async waitForSocketClose(socket: WebSocket): Promise<void> {
    if (socket.readyState === WebSocket.CLOSED) {
      return;
    }
    try {
      socket.close();
    } catch {
      // ignore close error
    }
    await new Promise<void>((resolve) => {
      if (socket.readyState === WebSocket.CLOSED) {
        resolve();
        return;
      }
      const checkInterval = setInterval(() => {
        if (socket.readyState === WebSocket.CLOSED) {
          clearInterval(checkInterval);
          resolve();
        }
      }, 50);
      setTimeout(() => {
        clearInterval(checkInterval);
        resolve();
      }, 1000);
    });
  }

  private async connectAgentSocket(
    agentId?: string,
    retryCount = 0,
  ): Promise<void> {
    const targetAgentId = String(
      agentId || this.panelState.selectedAgentId || "",
    ).trim();
    if (!targetAgentId || !this.panelState.token) {
      return;
    }
    // 检查Agent是否已完成，如果已完成则跳过连接
    const agentItem = this.agentItems.find((item) => item.id === targetAgentId);
    if (agentItem && agentItem.statusClass === "stopped") {
      return;
    }
    if (retryCount === 0) {
      const pendingAttempt = this.agentConnectionAttempts.get(targetAgentId);
      if (pendingAttempt) {
        return pendingAttempt;
      }
    }

    const connectionPromise = this.connectAgentSocketWithRetry(
      targetAgentId,
      retryCount,
    ).finally(() => {
      if (retryCount === 0) {
        this.agentConnectionAttempts.delete(targetAgentId);
      }
    });

    if (retryCount === 0) {
      this.agentConnectionAttempts.set(targetAgentId, connectionPromise);
    }
    return connectionPromise;
  }

  private async connectAgentSocketWithRetry(
    agentId: string,
    retryCount: number,
  ): Promise<void> {
    const existingSocket = this.agentSockets.get(agentId);
    if (existingSocket && existingSocket.readyState === WebSocket.OPEN) {
      this.sendSocketMessage(existingSocket, {
        type: "get_status",
        payload: {},
      });
      return;
    }
    if (existingSocket && existingSocket.readyState !== WebSocket.CLOSED) {
      await this.waitForSocketClose(existingSocket);
      this.agentSockets.delete(agentId);
    }

    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl);
    const agentNodeId =
      this.agentItems.find((item) => item.id === agentId)?.nodeId || "";
    const socketUrl = buildAgentWebSocketUrl(
      gatewayAddress,
      agentId,
      agentNodeId,
    );

    await new Promise<void>((resolve, reject) => {
      const agentSocket = new WebSocket(
        socketUrl,
        buildWebSocketProtocols(this.panelState.token),
      );
      let connectionHandled = false;
      const timeoutId = setTimeout(() => {
        if (connectionHandled) {
          return;
        }
        connectionHandled = true;
        try {
          agentSocket.close();
        } catch {
          // ignore close error
        }
        reject(new Error(`Agent WebSocket 连接超时：${agentId}`));
      }, AGENT_CONNECTION_TIMEOUT_MS);

      agentSocket.on("open", () => {
        if (connectionHandled) {
          return;
        }
        connectionHandled = true;
        clearTimeout(timeoutId);
        this.agentSockets.set(agentId, agentSocket);
        this.sendSocketMessage(agentSocket, {
          type: "get_status",
          payload: {},
        });
        this.withAgentState(agentId, (state) => {
          state.connection_status_text = `已连接 Agent：${this.getAgentDisplayLabel(agentId)}`;
          state.has_connection_error = false;
        });
        resolve();
      });

      agentSocket.on("message", (data: RawData) => {
        this.handleAgentSocketMessage(agentId, data);
      });

      agentSocket.on("error", () => {
        if (connectionHandled) {
          return;
        }
        connectionHandled = true;
        clearTimeout(timeoutId);
        try {
          agentSocket.close();
        } catch {
          // ignore close error
        }
        reject(new Error(`Agent WebSocket 连接异常：${agentId}`));
      });

      agentSocket.on("close", () => {
        if (this.agentSockets.get(agentId) === agentSocket) {
          this.agentSockets.delete(agentId);
        }
        if (!connectionHandled) {
          connectionHandled = true;
          clearTimeout(timeoutId);
          reject(new Error(`Agent WebSocket 提前关闭：${agentId}`));
          return;
        }
        this.withAgentState(agentId, (state) => {
          state.connection_status_text = `Agent 连接已关闭：${this.getAgentDisplayLabel(agentId)}`;
        });
      });
    }).catch(async (error) => {
      this.withAgentState(agentId, (state) => {
        state.connection_status_text = `等待 Agent 就绪：${this.getAgentDisplayLabel(agentId)} (${retryCount + 1}/${AGENT_CONNECTION_MAX_RETRIES})`;
        state.has_connection_error =
          retryCount + 1 >= AGENT_CONNECTION_MAX_RETRIES;
      });
      if (retryCount + 1 >= AGENT_CONNECTION_MAX_RETRIES) {
        this.appendPanelMessage(getErrorMessage(error), "error", agentId);
        throw error;
      }
      await new Promise((resolve) => {
        setTimeout(resolve, AGENT_CONNECTION_RETRY_DELAY_MS);
      });
      await this.connectAgentSocketWithRetry(agentId, retryCount + 1);
    });
  }

  private handleGatewaySocketMessage(rawData: RawData): void {
    const parsedMessage = parseSocketMessage(rawData);
    console.log("[GATEWAY MSG]", parsedMessage?.type, parsedMessage);
    if (!parsedMessage) {
      return;
    }

    if (parsedMessage.type === "ready") {
      this.appendPanelMessage("主通道就绪", "system");
      return;
    }
    if (parsedMessage.type === "status_update") {
      const agentId = this.panelState.selectedAgentId;
      if (agentId) {
        this.withAgentState(agentId, (state) => {
          this.updateExecutionStatus(
            state,
            parsedMessage.payload?.execution_status,
          );
          state.connection_status_text = `执行状态：${this.getExecutionStatusLabel(state.execution_status)}`;
          state.has_connection_error = false;
        });
      }
      this.postPanelState();
      return;
    }
    if (parsedMessage.type === "execution") {
      // 检查是否是独立终端的输出
      const executionId = String(
        parsedMessage.payload?.execution_id || "",
      ).trim();
      console.log(
        "[GATEWAY] execution message:",
        executionId,
        "sessions:",
        Array.from(this.independentTerminalSessions.keys()),
      );
      if (executionId.startsWith("terminal_")) {
        const terminalId = executionId.replace("terminal_", "");
        const data = String(parsedMessage.payload?.data || "");
        const encoded = Boolean(parsedMessage.payload?.encoded);
        console.log(
          "[GATEWAY TERMINAL] output for:",
          terminalId,
          "data length:",
          data.length,
          "encoded:",
          encoded,
        );
        this.handleIndependentTerminalOutput(terminalId, data, encoded);
        return;
      }
      // 非独立终端的执行输出
      const agentId = this.panelState.selectedAgentId;
      if (agentId) {
        this.handleExecutionPayload(agentId, parsedMessage.payload);
      }
      return;
    }
    if (parsedMessage.type === "input_request") {
      const agentId = this.panelState.selectedAgentId;
      if (agentId) {
        this.withAgentState(agentId, (state) => {
          state.pending_request_id =
            typeof parsedMessage.payload?.request_id === "string"
              ? parsedMessage.payload.request_id
              : undefined;
          const mode =
            parsedMessage.payload?.mode === "single" ? "single" : "multi";
          state.input_mode = mode;
          state.execution_status =
            mode === "single" ? "waiting_single" : "waiting_multi";
          state.input_tip = String(
            parsedMessage.payload?.tip || "Agent 请求输入",
          );
        });
        this.postPanelState();
      }
      return;
    }
    if (parsedMessage.type === "terminal_created") {
      this.handleTerminalCreated(
        parsedMessage.payload as Record<string, unknown>,
      );
      return;
    }
    if (parsedMessage.type === "terminal_closed") {
      const terminalId = String(
        parsedMessage.payload?.terminal_id || "",
      ).trim();
      console.log("[TERMINAL CLOSED] terminalId:", terminalId);
      if (terminalId) {
        const session = this.independentTerminalSessions.get(terminalId);
        if (session && !session.closed) {
          session.closed = true;
          if (session.writeEmitter) {
            session.writeEmitter.fire(
              "\r\n\x1b[33m[Terminal closed by server]\x1b[0m\r\n",
            );
          }
          // 关闭 VSCode 终端
          if (session.vscodeTerminal) {
            session.vscodeTerminal.dispose();
          }
          this.independentTerminalSessions.delete(terminalId);
        }
      }
      return;
    }
    if (parsedMessage.type === "execution") {
      // 检查是否是独立终端的输出
      const executionId = String(
        parsedMessage.payload?.execution_id || "",
      ).trim();
      console.log(
        "[MAIN SOCKET] execution message:",
        executionId,
        "sessions:",
        Array.from(this.independentTerminalSessions.keys()),
      );
      if (executionId.startsWith("terminal_")) {
        const terminalId = executionId.replace("terminal_", "");
        const data = String(parsedMessage.payload?.data || "");
        const encoded = Boolean(parsedMessage.payload?.encoded);
        console.log(
          "[INDEPENDENT TERMINAL] output for:",
          terminalId,
          "data length:",
          data.length,
          "encoded:",
          encoded,
        );
        this.handleIndependentTerminalOutput(terminalId, data, encoded);
        return;
      }
      // 非独立终端的执行输出
      const agentId = this.panelState.selectedAgentId;
      if (agentId) {
        this.handleExecutionPayload(agentId, parsedMessage.payload);
      }
      return;
    }
    if (parsedMessage.type === "error") {
      const errorMessage = String(
        parsedMessage.payload?.message || "主通道发生未知错误",
      );
      if (this.isInvalidTokenMessage(errorMessage)) {
        this.handleAuthExpired(errorMessage);
        return;
      }
      this.appendPanelMessage(errorMessage, "error");
    }
  }

  private handleAgentSocketMessage(agentId: string, rawData: RawData): void {
    const parsedMessage = parseSocketMessage(rawData);
    console.log("[AGENT MSG]", agentId, parsedMessage?.type, parsedMessage);
    if (!parsedMessage) {
      return;
    }

    if (parsedMessage.type === "output") {
      this.handleOutputPayload(agentId, parsedMessage.payload);
      return;
    }

    if (parsedMessage.type === "input_request") {
      this.withAgentState(agentId, (state) => {
        state.pending_request_id =
          typeof parsedMessage.payload?.request_id === "string"
            ? parsedMessage.payload.request_id
            : undefined;
        const mode =
          parsedMessage.payload?.mode === "single" ? "single" : "multi";
        state.input_mode = mode;
        state.execution_status =
          mode === "single" ? "waiting_single" : "waiting_multi";
        state.input_tip = String(
          parsedMessage.payload?.tip || "Agent 请求输入",
        );
      });
      this.postPanelState();
      return;
    }

    if (parsedMessage.type === "confirm") {
      void this.handleConfirmRequest(agentId, parsedMessage.payload);
      return;
    }

    if (parsedMessage.type === "status_update") {
      this.withAgentState(agentId, (state) => {
        this.updateExecutionStatus(
          state,
          parsedMessage.payload?.execution_status,
        );
      });
      this.postPanelState();
      return;
    }

    if (parsedMessage.type === "error") {
      const errorMessage = String(parsedMessage.payload?.message || "未知错误");
      if (this.isInvalidTokenMessage(errorMessage)) {
        this.handleAuthExpired(errorMessage);
        return;
      }
      this.appendPanelMessage(errorMessage, "error", agentId);
      return;
    }

    if (parsedMessage.type === "execution") {
      this.handleExecutionPayload(agentId, parsedMessage.payload);
    }
  }

  private async handleConfirmRequest(
    agentId: string,
    payload: Record<string, unknown> | undefined,
  ): Promise<void> {
    this.withAgentState(agentId, (state) => {
      state.pending_request_id =
        typeof payload?.request_id === "string"
          ? payload.request_id
          : undefined;
    });
    const message = String(payload?.message || "请确认");
    const defaultConfirm = payload?.default !== false; // 默认为 true

    // 通过 webview 显示确认对话框
    if (this.currentPanel) {
      this.currentPanel.webview.postMessage({
        type: "showConfirm",
        payload: {
          message,
          defaultConfirm,
          agentId,
        },
      });
    } else {
      // 如果没有 webview，使用原生对话框作为后备
      const confirmed = await vscode.window.showInformationMessage(
        message,
        { modal: true },
        "确认",
      );
      await this.sendConfirmResult(agentId, confirmed === "确认");
    }
  }

  private async sendConfirmResult(
    agentId: string,
    confirmed: boolean,
  ): Promise<void> {
    const agentSocket = this.agentSockets.get(agentId);
    if (!agentSocket || agentSocket.readyState !== WebSocket.OPEN) {
      this.appendPanelMessage(
        "当前 Agent WebSocket 未连接，无法发送确认结果",
        "error",
        agentId,
      );
      return;
    }
    const agentState = this.getAgentState(agentId);
    this.sendSocketMessage(agentSocket, {
      type: "confirm_result",
      payload: {
        confirmed,
        request_id: agentState.pending_request_id,
      },
    });
    this.withAgentState(agentId, (state) => {
      state.pending_request_id = undefined;
      state.input_tip = "";
      state.execution_status = "running";
    });
    this.postPanelState();
  }

  private handleOutputPayload(
    agentId: string,
    payload: Record<string, unknown> | undefined,
  ): void {
    const outputType = String(payload?.output_type || "");
    if (outputType === "STREAM_START") {
      const streamId = `stream-${Date.now()}`;
      this.withAgentState(agentId, (state) => {
        state.pending_stream_text = "";
        state.active_streaming_message_id = streamId;
        state.messages.push({
          text: "",
          variant: "stream",
          lang: "markdown",
          streamId,
        });
      });
      this.postPanelState();
      return;
    }
    if (outputType === "STREAM_CHUNK") {
      this.withAgentState(agentId, (state) => {
        state.pending_stream_text += String(payload?.text || "");
        if (!state.active_streaming_message_id) {
          return;
        }
        const streamingMessage = state.messages.find(
          (item) => item.streamId === state.active_streaming_message_id,
        );
        if (streamingMessage) {
          streamingMessage.text = state.pending_stream_text;
          streamingMessage.lang = "markdown";
        }
      });
      // 注意：withAgentState内部已经调用了postPanelState，无需重复调用
      return;
    }
    if (outputType === "STREAM_END") {
      this.withAgentState(agentId, (state) => {
        if (state.active_streaming_message_id) {
          state.messages = state.messages.filter(
            (item) => item.streamId !== state.active_streaming_message_id,
          );
        }
        state.pending_stream_text = "";
        state.active_streaming_message_id = undefined;
      });
      this.postPanelState();
      return;
    }
    // 处理 DIFF 类型：side by side diff 渲染
    if (outputType === "DIFF") {
      const outputText = String(payload?.text || "");
      if (outputText) {
        this.appendPanelMessage(outputText, "DIFF", agentId);
      }
      return;
    }
    const outputText = String(payload?.text || "");
    if (outputText) {
      const lang =
        payload?.lang === "markdown"
          ? "markdown"
          : payload?.lang === "diff"
            ? "diff"
            : "text";
      this.appendPanelMessage(outputText, "output", agentId, lang);
    }
  }

  private handleExecutionPayload(
    agentId: string,
    payload: Record<string, unknown> | undefined,
  ): void {
    const executionId = String(payload?.execution_id || "default");
    const executionChunk = decodeExecutionChunk(payload);
    const messageType = String(payload?.message_type || "");
    let nextBuffer = "";

    this.withAgentState(agentId, (state) => {
      if (messageType === "tool_stream_start") {
        state.execution_status = "running";
        state.active_execution_id = executionId;
        this.ensureExecutionTerminalSession(agentId, executionId);
        this.upsertExecutionMessage(state, executionId, {
          text: `执行中：${executionId}`,
          executionBuffer: state.execution_buffers[executionId] || "",
          finished: false,
        });
      }

      if (executionChunk) {
        nextBuffer = appendTerminalChunk(
          state.execution_buffers[executionId] || "",
          executionChunk,
        );
        state.execution_buffers[executionId] = nextBuffer;
        this.upsertExecutionMessage(state, executionId, {
          text: `执行中：${executionId}`,
          executionBuffer: nextBuffer,
        });
      } else {
        nextBuffer = state.execution_buffers[executionId] || "";
      }

      if (messageType === "tool_stream_end") {
        if (state.active_execution_id === executionId) {
          state.active_execution_id = undefined;
        }
        this.upsertExecutionMessage(state, executionId, {
          text: `执行完成：${executionId}`,
          executionBuffer: nextBuffer,
          finished: true,
        });
      }
    });

    const session = this.ensureExecutionTerminalSession(agentId, executionId);
    if (executionChunk) {
      this.writeExecutionTerminalChunk(session, executionChunk);
    }
    if (messageType === "tool_stream_end") {
      this.closeExecutionTerminalSession(agentId, executionId);
    }

    this.postPanelState();
  }

  private updateExecutionStatus(state: AgentStatus, status: unknown): void {
    const normalizedStatus = String(status || "running");
    // 如果当前正在等待输入（waiting_*），不被running状态覆盖
    const isWaitingInput =
      state.execution_status === "waiting_single" ||
      state.execution_status === "waiting_multi";
    if (isWaitingInput && normalizedStatus === "running") {
      console.log(
        "[STATUS PROTECT] ignoring running status, keeping:",
        state.execution_status,
      );
      return;
    }
    if (
      normalizedStatus === "waiting_single" ||
      normalizedStatus === "waiting_multi" ||
      normalizedStatus === "running" ||
      normalizedStatus === "stopped"
    ) {
      state.execution_status = normalizedStatus;
    } else {
      state.execution_status = "running";
    }
  }

  private sendSocketMessage(socket: WebSocket, payload: unknown): void {
    if (socket.readyState !== WebSocket.OPEN) {
      return;
    }
    socket.send(JSON.stringify(payload));
  }

  private createDefaultAgentState(): AgentStatus {
    return {
      connection_status: "disconnected",
      execution_status: "running",
      input_mode: "multi",
      input_tip: "",
      terminal_output: "暂无终端输出",
      connection_status_text: "未连接",
      has_connection_error: false,
      messages: [],
      pending_request_id: undefined,
      pending_stream_text: "",
      active_streaming_message_id: undefined,
      active_execution_id: undefined,
      execution_buffers: {},
      last_execution_id: undefined,
      last_buffer: "",
      closed: false,
    };
  }

  private getAgentState(agentId: string): AgentStatus {
    const existingState = this.agentStatuses.get(agentId);
    if (existingState) {
      return existingState;
    }
    const nextState = this.createDefaultAgentState();
    this.agentStatuses.set(agentId, nextState);
    this.loadPersistedAgentHistory(agentId);
    return nextState;
  }

  private withAgentState(
    agentId: string,
    updater: (state: AgentStatus) => void,
  ): void {
    const state = this.getAgentState(agentId);
    updater(state);
    this.postPanelState();
    void this.persistAgentHistory(agentId);
  }

  private getSelectedAgentStatus(): AgentStatus | undefined {
    const agentId = this.panelState.selectedAgentId;
    if (!agentId) {
      return undefined;
    }
    return this.agentStatuses.get(agentId);
  }

  // syncSelectedAgentState is no longer needed - AgentStatus is the single source of truth

  private getExecutionSessionKey(agentId: string, executionId: string): string {
    return `${agentId}::${executionId}`;
  }

  private ensureExecutionTerminalSession(
    agentId: string,
    executionId: string,
  ): ExecutionTerminalSession {
    const sessionKey = this.getExecutionSessionKey(agentId, executionId);
    const existingSession = this.executionTerminalSessions.get(sessionKey);
    if (existingSession) {
      return existingSession;
    }
    const session: ExecutionTerminalSession = {
      agentId,
      executionId,
      lastBuffer: "",
      closed: false,
    };
    this.executionTerminalSessions.set(sessionKey, session);
    return session;
  }

  private writeExecutionTerminalChunk(
    session: ExecutionTerminalSession,
    chunk: string,
  ): void {
    if (session.closed) {
      return;
    }
    const normalizedChunk = String(chunk || "");
    if (!normalizedChunk) {
      return;
    }
    session.lastBuffer = `${session.lastBuffer}${normalizedChunk}`;
  }

  private closeExecutionTerminalSession(
    agentId: string,
    executionId: string,
  ): void {
    const session = this.executionTerminalSessions.get(
      this.getExecutionSessionKey(agentId, executionId),
    );
    if (!session || session.closed) {
      return;
    }
    session.closed = true;
  }

  private disposeExecutionTerminalSession(
    agentId: string,
    executionId: string,
  ): void {
    const sessionKey = this.getExecutionSessionKey(agentId, executionId);
    const session = this.executionTerminalSessions.get(sessionKey);
    if (!session) {
      return;
    }
    this.executionTerminalSessions.delete(sessionKey);
  }

  private resolveExecutionSession(
    executionId?: string,
  ): { agentId: string; executionId: string } | undefined {
    const selectedAgentId = this.panelState.selectedAgentId;
    const targetExecutionId = String(executionId || "").trim();
    if (targetExecutionId) {
      if (selectedAgentId) {
        const selectedSession = this.executionTerminalSessions.get(
          this.getExecutionSessionKey(selectedAgentId, targetExecutionId),
        );
        if (selectedSession && !selectedSession.closed) {
          return {
            agentId: selectedSession.agentId,
            executionId: selectedSession.executionId,
          };
        }
      }
      for (const session of this.executionTerminalSessions.values()) {
        if (session.executionId === targetExecutionId && !session.closed) {
          return { agentId: session.agentId, executionId: session.executionId };
        }
      }
      return undefined;
    }
    if (!selectedAgentId) {
      return undefined;
    }
    const agentState = this.getAgentState(selectedAgentId);
    if (!agentState.active_execution_id) {
      return undefined;
    }
    const activeSession = this.executionTerminalSessions.get(
      this.getExecutionSessionKey(
        selectedAgentId,
        agentState.active_execution_id,
      ),
    );
    if (!activeSession || activeSession.closed) {
      return undefined;
    }
    return {
      agentId: activeSession.agentId,
      executionId: activeSession.executionId,
    };
  }

  private upsertExecutionMessage(
    state: AgentStatus,
    executionId: string,
    patch: Partial<ChatMessageItem>,
  ): void {
    const index = state.messages.findIndex(
      (item) =>
        item.variant === "execution" && item.executionId === executionId,
    );
    if (index >= 0) {
      state.messages[index] = {
        ...state.messages[index],
        ...patch,
        variant: "execution",
        executionId,
      };
      return;
    }
    state.messages.push({
      text: String(patch.text || `执行中：${executionId}`),
      variant: "execution",
      executionId,
      executionBuffer: patch.executionBuffer || "",
      finished: Boolean(patch.finished),
    });
  }

  private appendPanelMessage(
    text: string,
    variant: "system" | "error" | "output" | "stream" | "DIFF" = "system",
    agentId?: string,
    lang: "markdown" | "diff" | "text" = "text",
  ): void {
    if (agentId) {
      const agentState = this.getAgentState(agentId);
      agentState.messages.push({ text, variant, lang });
      void this.persistAgentHistory(agentId);
    } else {
      // 如果没有指定 agentId，添加到当前选中的 agent
      const selectedAgentId = this.panelState.selectedAgentId;
      if (selectedAgentId) {
        const agentState = this.getAgentState(selectedAgentId);
        agentState.messages.push({ text, variant, lang });
        void this.persistAgentHistory(selectedAgentId);
      }
    }
    this.postPanelState();
  }

  private disposeSocket(socketKey: "gatewaySocket"): void {
    const socket = this.panelState[socketKey];
    if (!socket) {
      return;
    }
    try {
      socket.close();
    } catch {
      // ignore close error
    }
    this.panelState[socketKey] = undefined;
  }

  public dispose(): void {
    this.stopAgentListRefresh();
    this.disposeSocket("gatewaySocket");
    // 清理所有独立终端会话
    for (const session of this.independentTerminalSessions.values()) {
      if (session.writeEmitter) {
        session.writeEmitter.dispose();
      }
      if (session.vscodeTerminal) {
        session.vscodeTerminal.dispose();
      }
    }
    this.independentTerminalSessions.clear();
  }
}

interface ChatPanelMessage {
  type?: string;
  gatewayUrl?: string;
  password?: string;
  text?: string;
  query?: string;
  executionId?: string;
  confirmed?: boolean;
  cols?: number;
  rows?: number;
  agentId?: string;
  payload?: {
    offset?: number;
    limit?: number;
  };
}

interface ModelGroupsResponse {
  success: boolean;
  data?: Array<{
    name: string;
    smart_model?: string;
    normal_model?: string;
    cheap_model?: string;
  }>;
  default_llm_group?: string;
  error?: {
    message?: string;
  };
}

interface LoginResponse {
  success: boolean;
  data?: {
    token?: string;
  };
  error?: {
    message?: string;
  };
}

interface CreateAgentResponse {
  success: boolean;
  data?: {
    agent_id?: string;
    name?: string;
    status?: string;
    agent_type?: string;
  };
  error?: {
    message?: string;
  };
}

interface DeleteAgentResponse {
  success: boolean;
  error?: {
    message?: string;
  };
}

interface AgentListResponse {
  success: boolean;
  data?: Array<{
    agent_id: string;
    name?: string;
    status?: string;
    agent_type?: string;
    working_dir?: string;
    llm_group?: string;
    worktree?: boolean;
    quick_mode?: boolean;
    node_id?: string;
  }>;
  error?: {
    message?: string;
  };
}

function parseGatewayAddress(address: string): GatewayAddress {
  const trimmedAddress = address.trim();
  if (!trimmedAddress) {
    return { host: "127.0.0.1", port: "8000" };
  }
  if (trimmedAddress.includes("://")) {
    const url = new URL(trimmedAddress);
    const inferredPort =
      url.port ||
      (url.protocol === "https:" || url.protocol === "wss:" ? "443" : "80");
    return { host: url.hostname, port: inferredPort };
  }
  if (trimmedAddress.includes(":")) {
    const [host, port] = trimmedAddress.split(":");
    return { host: host || "127.0.0.1", port: port || "8000" };
  }
  return { host: trimmedAddress, port: "8000" };
}

function buildNodeHttpUrl(
  gatewayAddress: GatewayAddress,
  nodeId: string = "master",
  path: string = "",
): string {
  const normalizedNodeId = String(nodeId || "master").trim() || "master";
  const normalizedPath = `/${String(path || "").replace(/^\/+/, "")}`;
  return `http://${gatewayAddress.host}:${gatewayAddress.port}/api/node/${encodeURIComponent(normalizedNodeId)}${normalizedPath}`;
}

function buildHttpUrl(gatewayAddress: GatewayAddress, path: string): string {
  const normalizedPath = `/${String(path || "").replace(/^\/+/, "")}`;
  return `http://${gatewayAddress.host}:${gatewayAddress.port}${normalizedPath}`;
}

function buildWebSocketProtocols(token?: string): string[] | undefined {
  const normalizedToken = String(token || "").trim();
  if (!normalizedToken) {
    return undefined;
  }
  return ["jarvis-ws", `jarvis-token.${encodeURIComponent(normalizedToken)}`];
}

function buildNodeWebSocketUrl(
  gatewayAddress: GatewayAddress,
  nodeId: string = "master",
  path: string = "",
): string {
  const normalizedNodeId = String(nodeId || "master").trim() || "master";
  const normalizedPath = `/${String(path || "").replace(/^\/+/, "")}`;
  return `ws://${gatewayAddress.host}:${gatewayAddress.port}/api/node/${encodeURIComponent(normalizedNodeId)}${normalizedPath}`;
}

function buildWebSocketUrl(gatewayAddress: GatewayAddress): string {
  return buildNodeWebSocketUrl(gatewayAddress, "master", "ws");
}

function buildAgentWebSocketUrl(
  gatewayAddress: GatewayAddress,
  agentId: string,
  nodeId?: string,
): string {
  const normalizedNodeId = String(nodeId || "master").trim() || "master";
  return buildNodeWebSocketUrl(
    gatewayAddress,
    normalizedNodeId,
    `agent/${agentId}/ws`,
  );
}

function parseSocketMessage(
  rawData: RawData,
): { type?: string; payload?: Record<string, unknown> } | null {
  let text: string;
  if (typeof rawData === "string") {
    text = rawData;
  } else if (Buffer.isBuffer(rawData)) {
    text = rawData.toString("utf-8");
  } else if (rawData instanceof ArrayBuffer) {
    text = Buffer.from(rawData).toString("utf-8");
  } else if (Array.isArray(rawData)) {
    text = Buffer.concat(rawData).toString("utf-8");
  } else {
    return null;
  }

  try {
    return JSON.parse(text) as {
      type?: string;
      payload?: Record<string, unknown>;
    };
  } catch {
    return null;
  }
}

function decodeExecutionChunk(
  payload: Record<string, unknown> | undefined,
): string {
  if (!payload) {
    return "";
  }
  const messageType = String(payload.message_type || "");
  if (messageType === "tool_input") {
    return "";
  }
  const chunkData = String(payload.data || "");
  if (!chunkData) {
    return "";
  }
  const encoded = Boolean(payload.encoded);
  if (!encoded) {
    return chunkData;
  }
  try {
    return Buffer.from(chunkData, "base64").toString("utf-8");
  } catch {
    return chunkData;
  }
}

function appendTerminalChunk(currentOutput: string, nextChunk: string): string {
  if (!nextChunk) {
    return currentOutput;
  }
  if (!currentOutput || currentOutput === "暂无终端输出") {
    return nextChunk;
  }
  return `${currentOutput}${nextChunk}`;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function activate(context: vscode.ExtensionContext): void {
  const provider = new JarvisAgentListViewProvider(
    context.extensionUri,
    context.globalState,
  );
  activeProvider = provider;

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      JarvisAgentListViewProvider.viewType,
      provider,
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("jarvis.openPanel", async () => {
      await provider.openChatPanel();
    }),
  );

  // 注册开启远端文件编辑命令
  context.subscriptions.push(
    vscode.commands.registerCommand("jarvis.enableRemoteFileEdit", async () => {
      await provider.enableRemoteFileEdit();
    }),
  );

  // 注册恢复远端文件只读命令
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "jarvis.disableRemoteFileEdit",
      async () => {
        await provider.disableRemoteFileEdit();
      },
    ),
  );

  // 注册重启节点服务命令
  context.subscriptions.push(
    vscode.commands.registerCommand("jarvis.restartNodeService", async () => {
      await provider.restartNodeService();
    }),
  );

  // 监听文件保存事件，同步远端文件
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (document) => {
      const localPath = document.uri.fsPath;
      // 检查是否是远端文件编辑
      if (localPath.includes("jarvis-remote-files")) {
        await provider.syncRemoteFile(localPath);
      }
    }),
  );

  // 监听编辑器切换事件，更新只读状态栏
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(() => {
      provider.updateReadOnlyStatusBar();
    }),
  );
}

let activeProvider: JarvisAgentListViewProvider | undefined;

export function deactivate(): void {
  activeProvider?.stopRemoteFileHeartbeat();
  activeProvider?.dispose();
}

function createNonce(): string {
  const possible =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  return Array.from({ length: 32 }, () =>
    possible.charAt(Math.floor(Math.random() * possible.length)),
  ).join("");
}
