import * as vscode from 'vscode'
import WebSocket, { RawData } from 'ws'

interface AgentListItem {
  id: string
  displayName: string
  statusText: string
}

interface GatewayAddress {
  host: string
  port: string
}

interface ChatPanelState {
  gatewayUrl: string
  password: string
  token: string
  selectedAgentId?: string
  gatewaySocket?: WebSocket
  agentSocket?: WebSocket
  terminalOutput: string
  connectionStatusText: string
  hasConnectionError: boolean
}

interface CreateAgentFormState {
  isVisible: boolean
  agentType: 'agent' | 'codeagent'
  workingDir: string
  name: string
  llmGroup: string
  useWorktree: boolean
  isSubmitting: boolean
  errorMessage: string
}

interface LeftViewLoginState {
  errorMessage: string
  isSubmitting: boolean
}

interface ModelGroupItem {
  name: string
  smartModel: string
  normalModel: string
  cheapModel: string
}

interface AgentListViewMessage {
  type?: string
  agentId?: string
  agentType?: string
  gatewayUrl?: string
  password?: string
  workingDir?: string
  name?: string
  llmGroup?: string
  useWorktree?: boolean
}

class JarvisAgentListViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = 'jarvis.agentListView'

  private currentPanel: vscode.WebviewPanel | undefined
  private agentItems: AgentListItem[] = [
    {
      id: 'default-agent',
      displayName: 'default-agent',
      statusText: '示例 Agent（MVP 占位）'
    }
  ]
  private currentView: vscode.WebviewView | undefined
  private readonly panelState: ChatPanelState = {
    gatewayUrl: '127.0.0.1:8000',
    password: '',
    token: '',
    selectedAgentId: undefined,
    gatewaySocket: undefined,
    agentSocket: undefined,
    terminalOutput: '暂无终端输出',
    connectionStatusText: '未连接',
    hasConnectionError: false
  }
  private readonly createAgentFormState: CreateAgentFormState = {
    isVisible: false,
    agentType: 'agent',
    workingDir: '~',
    name: '通用Agent',
    llmGroup: 'default',
    useWorktree: false,
    isSubmitting: false,
    errorMessage: ''
  }
  private readonly leftViewLoginState: LeftViewLoginState = {
    errorMessage: '',
    isSubmitting: false
  }
  private modelGroups: ModelGroupItem[] = []
  private defaultLlmGroup = ''

  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.currentView = webviewView
    webviewView.webview.options = {
      enableScripts: true
    }

    webviewView.webview.html = this.getAgentListHtml()

    webviewView.webview.onDidReceiveMessage(async (message: AgentListViewMessage) => {
      if (message?.type === 'openAgent') {
        await this.openChatPanel(message.agentId)
        return
      }
      if (message?.type === 'refreshAgents') {
        await this.refreshAgents()
        return
      }
      if (message?.type === 'connect') {
        await this.connectFromLeftView(message)
        return
      }
      if (message?.type === 'toggleCreateAgentForm') {
        this.toggleCreateAgentForm()
        return
      }
      if (message?.type === 'cancelCreateAgent') {
        this.resetCreateAgentForm()
        this.renderAgentListView()
        return
      }
      if (message?.type === 'createAgent') {
        await this.createAgent(message)
      }
    })
  }

  async openChatPanel(agentId?: string): Promise<void> {
    if (agentId) {
      this.panelState.selectedAgentId = agentId
    }

    if (!this.currentPanel) {
      this.currentPanel = vscode.window.createWebviewPanel(
        'jarvis.chatPanel',
        this.getChatPanelTitle(),
        { viewColumn: vscode.ViewColumn.Beside, preserveFocus: false },
        {
          enableScripts: true,
          retainContextWhenHidden: true
        }
      )

      this.currentPanel.webview.onDidReceiveMessage(async (message: ChatPanelMessage) => {
        await this.handleChatPanelMessage(message)
      })

      this.currentPanel.onDidDispose(() => {
        this.currentPanel = undefined
      })
    }

    this.currentPanel.title = this.getChatPanelTitle()
    this.currentPanel.webview.html = this.getChatPanelHtml(this.panelState.selectedAgentId)
    this.postPanelState()
    await this.currentPanel.reveal(vscode.ViewColumn.Beside, false)
  }

  private getAgentListHtml(): string {
    const nonce = createNonce()
    if (!this.panelState.token) {
      return this.getLeftLoginHtml(nonce)
    }

    const createButtonLabel = this.createAgentFormState.isVisible ? '收起创建' : '创建 Agent'
    const createButtonDisabled = this.createAgentFormState.isSubmitting ? 'disabled' : ''
    const submitButtonDisabled = this.createAgentFormState.isSubmitting ? 'disabled' : ''
    const worktreeChecked = this.createAgentFormState.useWorktree ? 'checked' : ''
    const worktreeDisabled = this.createAgentFormState.agentType === 'codeagent' ? '' : 'disabled'
    const createAgentErrorMarkup = this.createAgentFormState.errorMessage
      ? `<div class="form-error">${escapeHtml(this.createAgentFormState.errorMessage)}</div>`
      : ''
    const llmGroupSelectOptions = this.modelGroups
      .map((group) => {
        const selected = group.name === this.createAgentFormState.llmGroup ? 'selected' : ''
        return `<option value="${escapeHtml(group.name)}" ${selected}>${escapeHtml(group.name)}</option>`
      })
      .join('')
    const llmGroupFieldMarkup = this.modelGroups.length > 0
      ? `
    <div class="form-group">
      <label for="llmGroup">模型组</label>
      <select id="llmGroup">${llmGroupSelectOptions}</select>
    </div>`
      : `
    <div class="form-group">
      <label for="llmGroup">模型组</label>
      <input id="llmGroup" value="${escapeHtml(this.createAgentFormState.llmGroup)}" placeholder="${escapeHtml(this.defaultLlmGroup || '请输入模型组')}" />
    </div>`
    const createAgentFormMarkup = this.createAgentFormState.isVisible
      ? `
  <div class="create-agent-panel">
    <div class="form-group">
      <label for="agentType">Agent 类型</label>
      <select id="agentType">
        <option value="agent" ${this.createAgentFormState.agentType === 'agent' ? 'selected' : ''}>agent</option>
        <option value="codeagent" ${this.createAgentFormState.agentType === 'codeagent' ? 'selected' : ''}>codeagent</option>
      </select>
    </div>
    <div class="form-group">
      <label for="workingDir">工作目录</label>
      <input id="workingDir" value="${escapeHtml(this.createAgentFormState.workingDir)}" placeholder="~/project" />
    </div>
    <div class="form-group">
      <label for="agentName">名称</label>
      <input id="agentName" value="${escapeHtml(this.createAgentFormState.name)}" placeholder="通用Agent" />
    </div>
    ${llmGroupFieldMarkup}
    <label class="checkbox-row">
      <input id="useWorktree" type="checkbox" ${worktreeChecked} ${worktreeDisabled} />
      <span>codeagent 使用 worktree</span>
    </label>
    ${createAgentErrorMarkup}
    <div class="form-actions">
      <button id="cancelCreateAgentButton" type="button" ${createButtonDisabled}>取消</button>
      <button id="submitCreateAgentButton" type="button" ${submitButtonDisabled}>${this.createAgentFormState.isSubmitting ? '创建中...' : '创建'}</button>
    </div>
  </div>`
      : ''
    const agentListMarkup = this.agentItems
      .map((agentItem) => {
        return `
    <li data-agent-id="${agentItem.id}">
      <div class="agent-name">${escapeHtml(agentItem.displayName)}</div>
      <div class="agent-meta">${escapeHtml(agentItem.statusText)}</div>
    </li>`
      })
      .join('')

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
    button, select, input { border: 1px solid var(--vscode-input-border, var(--vscode-panel-border)); border-radius: 4px; }
    button { background: var(--vscode-button-background); color: var(--vscode-button-foreground); padding: 6px 10px; cursor: pointer; }
    input, select { width: 100%; padding: 6px 8px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); box-sizing: border-box; }
    ul { list-style: none; padding: 0; margin: 0; }
    li { border: 1px solid var(--vscode-panel-border); border-radius: 6px; margin-bottom: 8px; padding: 8px; cursor: pointer; }
    .agent-name { font-weight: 600; }
    .agent-meta { opacity: 0.8; font-size: 12px; margin-top: 4px; }
    .create-agent-panel { border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 10px; margin-bottom: 12px; }
    .form-group { margin-bottom: 10px; }
    .form-group label { display: block; font-size: 12px; margin-bottom: 4px; opacity: 0.9; }
    .checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 12px; }
    .checkbox-row input { width: auto; }
    .form-actions { display: flex; justify-content: flex-end; gap: 8px; }
    .form-error { color: var(--vscode-errorForeground); font-size: 12px; margin-bottom: 10px; }
  </style>
</head>
<body>
  <div class="toolbar">
    <strong>Agents</strong>
    <div class="toolbar-actions">
      <button id="toggleCreateAgentButton" ${createButtonDisabled}>${createButtonLabel}</button>
      <button id="refreshButton">刷新</button>
    </div>
  </div>
  ${createAgentFormMarkup}
  <ul>${agentListMarkup}
  </ul>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const refreshButton = document.getElementById('refreshButton');
    const toggleCreateAgentButton = document.getElementById('toggleCreateAgentButton');
    if (refreshButton) {
      refreshButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'refreshAgents' });
      });
    }
    if (toggleCreateAgentButton) {
      toggleCreateAgentButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'toggleCreateAgentForm' });
      });
    }
    const submitCreateAgentButton = document.getElementById('submitCreateAgentButton');
    if (submitCreateAgentButton) {
      submitCreateAgentButton.addEventListener('click', () => {
        const agentType = document.getElementById('agentType');
        const workingDir = document.getElementById('workingDir');
        const agentName = document.getElementById('agentName');
        const llmGroup = document.getElementById('llmGroup');
        const useWorktree = document.getElementById('useWorktree');
        vscode.postMessage({
          type: 'createAgent',
          agentType: agentType ? agentType.value : 'agent',
          workingDir: workingDir ? workingDir.value : '',
          name: agentName ? agentName.value : '',
          llmGroup: llmGroup ? llmGroup.value : '',
          useWorktree: Boolean(useWorktree && useWorktree.checked)
        });
      });
    }
    const cancelCreateAgentButton = document.getElementById('cancelCreateAgentButton');
    if (cancelCreateAgentButton) {
      cancelCreateAgentButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'cancelCreateAgent' });
      });
    }
    document.querySelectorAll('[data-agent-id]').forEach((item) => {
      item.addEventListener('click', () => {
        vscode.postMessage({ type: 'openAgent', agentId: item.getAttribute('data-agent-id') });
      });
    });
  </script>
</body>
</html>`
  }

  private getLeftLoginHtml(nonce: string): string {
    const connectButtonDisabled = this.leftViewLoginState.isSubmitting ? 'disabled' : ''
    const loginErrorMarkup = this.leftViewLoginState.errorMessage
      ? `<div class="form-error">${escapeHtml(this.leftViewLoginState.errorMessage)}</div>`
      : ''

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
  </style>
</head>
<body>
  <div class="login-panel">
    <div class="panel-title">连接到 Jarvis</div>
    ${loginErrorMarkup}
    <div class="form-group">
      <label for="gatewayUrl">网关地址</label>
      <input id="gatewayUrl" value="${escapeHtml(this.panelState.gatewayUrl)}" placeholder="127.0.0.1:8000" />
    </div>
    <div class="form-group">
      <label for="password">密码</label>
      <input id="password" type="password" value="${escapeHtml(this.panelState.password)}" placeholder="可选" />
    </div>
    <button id="connectButton" ${connectButtonDisabled}>${this.leftViewLoginState.isSubmitting ? '连接中...' : '连接'}</button>
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
  </script>
</body>
</html>`
  }

  private getChatPanelHtml(agentId?: string): string {
    const nonce = createNonce()
    const selectedAgentLabel = agentId ?? '未选择 Agent'
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Jarvis Chat</title>
  <style>
    body { font-family: var(--vscode-font-family); padding: 0; margin: 0; color: var(--vscode-foreground); background: var(--vscode-editor-background); }
    .layout { display: grid; grid-template-rows: auto auto 1fr auto auto; height: 100vh; }
    .section { padding: 12px; border-bottom: 1px solid var(--vscode-panel-border); }
    .messages { overflow: auto; padding: 12px; }
    .message { margin-bottom: 12px; padding: 10px; border-radius: 8px; background: var(--vscode-sideBar-background); }
    .message.system { border-left: 3px solid var(--vscode-textLink-foreground); }
    .message.error { border-left: 3px solid var(--vscode-errorForeground); }
    .terminal { height: 180px; margin: 12px; border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 10px; background: #111; color: #ddd; font-family: monospace; white-space: pre-wrap; overflow: auto; }
    .row { display: flex; gap: 8px; align-items: center; }
    input { flex: 1; padding: 8px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border, var(--vscode-panel-border)); }
    button { border: 1px solid var(--vscode-button-border, transparent); background: var(--vscode-button-background); color: var(--vscode-button-foreground); padding: 8px 12px; cursor: pointer; }
    .status { font-size: 12px; opacity: 0.8; }
    .status.error { color: var(--vscode-errorForeground); }
    .hint { font-size: 12px; opacity: 0.75; }
  </style>
</head>
<body>
  <div class="layout">
    <div class="section">
      <div><strong>当前 Agent：</strong><span id="selectedAgentLabel">${selectedAgentLabel}</span></div>
      <div class="status" id="connectionStatus">未连接</div>
      <div class="hint">连接与 Agent 管理请在左侧边栏完成，此处聚焦聊天与终端。</div>
    </div>
    <div class="messages" id="messages"></div>
    <div class="section">
      <div class="row">
        <input id="messageInput" placeholder="输入消息..." />
        <button id="sendButton">发送</button>
      </div>
    </div>
    <div>
      <div class="terminal" id="terminalOutput">暂无终端输出</div>
    </div>
  </div>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const messages = document.getElementById('messages');
    const terminalOutput = document.getElementById('terminalOutput');
    const connectionStatus = document.getElementById('connectionStatus');
    const selectedAgentLabel = document.getElementById('selectedAgentLabel');

    function appendMessage(text, variant = 'system') {
      const item = document.createElement('div');
      item.className = 'message ' + variant;
      item.textContent = text;
      messages.appendChild(item);
      messages.scrollTop = messages.scrollHeight;
    }

    document.getElementById('sendButton').addEventListener('click', () => {
      const messageInput = document.getElementById('messageInput');
      const text = messageInput.value;
      if (!text.trim()) {
        return;
      }
      vscode.postMessage({ type: 'sendMessage', text });
      messageInput.value = '';
    });

    window.addEventListener('message', (event) => {
      const data = event.data || {};
      if (data.type === 'state') {
        selectedAgentLabel.textContent = data.payload.selectedAgentId || '未选择 Agent';
        connectionStatus.textContent = data.payload.statusText || '未连接';
        connectionStatus.className = data.payload.isError ? 'status error' : 'status';
        terminalOutput.textContent = data.payload.terminalOutput || '暂无终端输出';
      }
      if (data.type === 'message') {
        appendMessage(data.payload.text || '', data.payload.variant || 'system');
      }
      if (data.type === 'terminalOutput') {
        terminalOutput.textContent = data.payload || '暂无终端输出';
      }
    });
  </script>
</body>
</html>`
  }

  private async handleChatPanelMessage(message: ChatPanelMessage): Promise<void> {
    if (message.type === 'sendMessage') {
      await this.sendAgentMessage(message.text ?? '')
    }
  }

  private async connectToGateway(gatewayUrl: string, password: string): Promise<void> {
    this.panelState.gatewayUrl = gatewayUrl.trim() || this.panelState.gatewayUrl
    this.panelState.password = password
    this.postPanelMessage(`正在连接 ${this.panelState.gatewayUrl} ...`)

    try {
      const token = await this.loginWithPassword(this.panelState.password)
      this.panelState.token = token
      this.panelState.connectionStatusText = '已登录，正在连接主 WebSocket'
      this.panelState.hasConnectionError = false
      this.leftViewLoginState.errorMessage = ''
      await this.loadModelGroups()
      this.postPanelState()
      this.connectGatewaySocket()
      await this.refreshAgents()
      this.renderAgentListView()
      this.postPanelMessage('登录成功', 'system')
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      this.panelState.connectionStatusText = `连接失败：${errorMessage}`
      this.panelState.hasConnectionError = true
      this.leftViewLoginState.errorMessage = errorMessage
      this.postPanelState()
      this.renderAgentListView()
      this.postPanelMessage(`连接失败：${errorMessage}`, 'error')
      throw error
    }
  }

  private async refreshAgents(): Promise<void> {
    if (!this.panelState.token) {
      this.postPanelMessage('请先连接并登录 Jarvis 网关', 'error')
      return
    }

    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl)
      const response = await fetch(buildHttpUrl(gatewayAddress, '/api/agents'), {
        headers: {
          Authorization: `Bearer ${this.panelState.token}`
        }
      })
      const result = (await response.json()) as AgentListResponse
      if (!response.ok || !result.success || !Array.isArray(result.data)) {
        throw new Error(result.error?.message || '获取 Agent 列表失败')
      }

      this.agentItems = result.data.map((agent) => ({
        id: agent.agent_id,
        displayName: agent.name || agent.agent_id,
        statusText: agent.status || agent.agent_type || 'unknown'
      }))

      if (!this.panelState.selectedAgentId && this.agentItems.length > 0) {
        this.panelState.selectedAgentId = this.agentItems[0].id
      }

      this.renderAgentListView()
      if (this.currentPanel) {
        this.currentPanel.title = this.getChatPanelTitle()
        this.currentPanel.webview.html = this.getChatPanelHtml(this.panelState.selectedAgentId)
      }

      this.panelState.connectionStatusText = '已连接并加载 Agents'
      this.panelState.hasConnectionError = false
      this.postPanelState()
      this.connectAgentSocket()
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      this.postPanelMessage(`加载 Agent 失败：${errorMessage}`, 'error')
    }
  }

  private async sendAgentMessage(text: string): Promise<void> {
    const messageText = text.trim()
    if (!messageText) {
      return
    }
    if (!this.panelState.selectedAgentId) {
      this.postPanelMessage('请先在左侧选择 Agent', 'error')
      return
    }
    if (!this.panelState.token) {
      this.postPanelMessage('请先连接 Jarvis 网关', 'error')
      return
    }
    if (!this.panelState.agentSocket || this.panelState.agentSocket.readyState !== WebSocket.OPEN) {
      this.postPanelMessage('当前 Agent WebSocket 未连接，无法发送消息', 'error')
      return
    }

    this.postPanelMessage(`我：${messageText}`, 'system')
    this.panelState.agentSocket.send(JSON.stringify({
      type: 'input_result',
      payload: {
        text: messageText
      }
    }))
  }

  private async loginWithPassword(password: string): Promise<string> {
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl)
    const response = await fetch(buildHttpUrl(gatewayAddress, '/api/auth/login'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ password })
    })
    const result = (await response.json()) as LoginResponse
    if (!response.ok || !result.success || !result.data?.token) {
      throw new Error(result.error?.message || '登录失败')
    }
    return result.data.token
  }

  private async loadModelGroups(): Promise<void> {
    if (!this.panelState.token) {
      return
    }
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl)
    const response = await fetch(buildHttpUrl(gatewayAddress, '/api/model-groups'), {
      headers: {
        Authorization: `Bearer ${this.panelState.token}`
      }
    })
    const result = (await response.json()) as ModelGroupsResponse
    if (!response.ok || !result.success) {
      throw new Error(result.error?.message || '获取模型组失败')
    }
    this.modelGroups = Array.isArray(result.data)
      ? result.data.map((group) => ({
          name: group.name,
          smartModel: group.smart_model || '-',
          normalModel: group.normal_model || '-',
          cheapModel: group.cheap_model || '-'
        }))
      : []
    this.defaultLlmGroup = String(result.default_llm_group || '').trim()
    const fallbackGroup = this.modelGroups[0]?.name || ''
    const resolvedDefaultGroup = this.defaultLlmGroup || fallbackGroup
    if (resolvedDefaultGroup) {
      this.createAgentFormState.llmGroup = resolvedDefaultGroup
    }
  }

  private postPanelState(): void {
    if (!this.currentPanel) {
      return
    }
    this.currentPanel.webview.postMessage({
      type: 'state',
      payload: {
        gatewayUrl: this.panelState.gatewayUrl,
        password: this.panelState.password,
        selectedAgentId: this.panelState.selectedAgentId,
        statusText: this.panelState.connectionStatusText,
        isError: this.panelState.hasConnectionError,
        terminalOutput: this.panelState.terminalOutput
      }
    })
  }

  private postPanelMessage(text: string, variant: 'system' | 'error' = 'system'): void {
    if (!this.currentPanel) {
      return
    }
    this.currentPanel.webview.postMessage({
      type: 'message',
      payload: {
        text,
        variant
      }
    })
  }

  private renderAgentListView(): void {
    if (!this.currentView) {
      return
    }
    this.currentView.webview.html = this.getAgentListHtml()
  }

  private async connectFromLeftView(message: AgentListViewMessage): Promise<void> {
    const gatewayUrl = String(message.gatewayUrl || '').trim()
    const password = String(message.password || '')
    this.leftViewLoginState.isSubmitting = true
    this.leftViewLoginState.errorMessage = ''
    this.renderAgentListView()

    try {
      await this.connectToGateway(gatewayUrl, password)
    } catch {
      // error state handled in connectToGateway
    } finally {
      this.leftViewLoginState.isSubmitting = false
      this.renderAgentListView()
    }
  }

  private toggleCreateAgentForm(): void {
    this.createAgentFormState.isVisible = !this.createAgentFormState.isVisible
    this.createAgentFormState.errorMessage = ''
    this.renderAgentListView()
  }

  private resetCreateAgentForm(): void {
    this.createAgentFormState.isVisible = false
    this.createAgentFormState.agentType = 'agent'
    this.createAgentFormState.workingDir = '~'
    this.createAgentFormState.name = '通用Agent'
    this.createAgentFormState.llmGroup = this.defaultLlmGroup || this.modelGroups[0]?.name || ''
    this.createAgentFormState.useWorktree = false
    this.createAgentFormState.isSubmitting = false
    this.createAgentFormState.errorMessage = ''
  }

  private updateCreateAgentDefaults(agentType: 'agent' | 'codeagent'): void {
    this.createAgentFormState.agentType = agentType
    this.createAgentFormState.name = agentType === 'codeagent' ? '代码Agent' : '通用Agent'
    if (agentType !== 'codeagent') {
      this.createAgentFormState.useWorktree = false
    }
  }

  private async createAgent(message: AgentListViewMessage): Promise<void> {
    if (!this.panelState.token) {
      this.createAgentFormState.isVisible = true
      this.createAgentFormState.errorMessage = '请先连接并登录 Jarvis 网关'
      this.renderAgentListView()
      return
    }

    const requestedAgentType = message.agentType === 'codeagent' ? 'codeagent' : 'agent'
    const workingDir = String(message.workingDir || '').trim()
    const agentName = String(message.name || '').trim()
    const llmGroup = String(message.llmGroup || '').trim() || this.defaultLlmGroup || this.modelGroups[0]?.name || ''
    const useWorktree = requestedAgentType === 'codeagent' ? Boolean(message.useWorktree) : false

    this.updateCreateAgentDefaults(requestedAgentType)
    this.createAgentFormState.workingDir = workingDir
    this.createAgentFormState.name = agentName || this.createAgentFormState.name
    this.createAgentFormState.llmGroup = llmGroup
    this.createAgentFormState.useWorktree = useWorktree
    this.createAgentFormState.isVisible = true

    if (!workingDir) {
      this.createAgentFormState.errorMessage = '工作目录不能为空'
      this.renderAgentListView()
      return
    }
    if (!llmGroup) {
      this.createAgentFormState.errorMessage = '模型组不能为空'
      this.renderAgentListView()
      return
    }

    this.createAgentFormState.isSubmitting = true
    this.createAgentFormState.errorMessage = ''
    this.renderAgentListView()

    try {
      const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl)
      const response = await fetch(buildHttpUrl(gatewayAddress, '/api/agents'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.panelState.token}`
        },
        body: JSON.stringify({
          agent_type: requestedAgentType,
          working_dir: workingDir,
          name: agentName || undefined,
          llm_group: llmGroup,
          worktree: useWorktree
        })
      })
      const result = (await response.json()) as CreateAgentResponse
      if (!response.ok || !result.success || !result.data?.agent_id) {
        throw new Error(result.error?.message || '创建 Agent 失败')
      }

      this.panelState.selectedAgentId = result.data.agent_id
      this.resetCreateAgentForm()
      await this.refreshAgents()
      this.renderAgentListView()
      this.postPanelMessage(`已创建 Agent：${result.data.name || result.data.agent_id}`, 'system')
      await this.openChatPanel(result.data.agent_id)
    } catch (error) {
      this.createAgentFormState.isSubmitting = false
      this.createAgentFormState.errorMessage = getErrorMessage(error)
      this.renderAgentListView()
    }
  }

  private getChatPanelTitle(): string {
    return this.panelState.selectedAgentId ? `Jarvis · ${this.panelState.selectedAgentId}` : 'Jarvis'
  }

  private connectGatewaySocket(): void {
    this.disposeSocket('gatewaySocket')
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl)
    const socketUrl = buildWebSocketUrl(gatewayAddress)
    const gatewaySocket = new WebSocket(socketUrl, {
      headers: {
        Authorization: `Bearer ${this.panelState.token}`
      }
    })

    gatewaySocket.on('open', () => {
      this.panelState.connectionStatusText = '主 WebSocket 已连接'
      this.panelState.hasConnectionError = false
      this.postPanelState()
    })

    gatewaySocket.on('message', (data: RawData) => {
      this.handleGatewaySocketMessage(data)
    })

    gatewaySocket.on('error', () => {
      this.panelState.connectionStatusText = '主 WebSocket 连接异常'
      this.panelState.hasConnectionError = true
      this.postPanelState()
    })

    gatewaySocket.on('close', () => {
      this.panelState.connectionStatusText = '主 WebSocket 已关闭'
      this.postPanelState()
    })

    this.panelState.gatewaySocket = gatewaySocket
  }

  private connectAgentSocket(): void {
    if (!this.panelState.selectedAgentId || !this.panelState.token) {
      return
    }

    this.disposeSocket('agentSocket')
    const gatewayAddress = parseGatewayAddress(this.panelState.gatewayUrl)
    const socketUrl = buildAgentWebSocketUrl(gatewayAddress, this.panelState.selectedAgentId)
    const agentSocket = new WebSocket(socketUrl, {
      headers: {
        Authorization: `Bearer ${this.panelState.token}`
      }
    })

    agentSocket.on('open', () => {
      this.postPanelMessage(`已连接 Agent：${this.panelState.selectedAgentId}`, 'system')
    })

    agentSocket.on('message', (data: RawData) => {
      this.handleAgentSocketMessage(data)
    })

    agentSocket.on('error', () => {
      this.postPanelMessage('Agent WebSocket 连接异常', 'error')
    })

    agentSocket.on('close', () => {
      this.postPanelMessage('Agent WebSocket 已关闭', 'system')
    })

    this.panelState.agentSocket = agentSocket
  }

  private handleGatewaySocketMessage(rawData: RawData): void {
    const parsedMessage = parseSocketMessage(rawData)
    if (!parsedMessage) {
      return
    }

    if (parsedMessage.type === 'ready') {
      this.postPanelMessage('主通道就绪', 'system')
      return
    }
    if (parsedMessage.type === 'status_update') {
      const executionStatus = String(parsedMessage.payload?.execution_status || 'running')
      this.panelState.connectionStatusText = `状态：${executionStatus}`
      this.panelState.hasConnectionError = false
      this.postPanelState()
      return
    }
    if (parsedMessage.type === 'execution') {
      const executionChunk = decodeExecutionChunk(parsedMessage.payload)
      if (!executionChunk) {
        return
      }
      this.panelState.terminalOutput = appendTerminalChunk(this.panelState.terminalOutput, executionChunk)
      this.postPanelState()
    }
  }

  private handleAgentSocketMessage(rawData: RawData): void {
    const parsedMessage = parseSocketMessage(rawData)
    if (!parsedMessage) {
      return
    }

    if (parsedMessage.type === 'output') {
      const outputText = String(parsedMessage.payload?.text || '')
      if (outputText) {
        this.postPanelMessage(outputText, 'system')
      }
      return
    }

    if (parsedMessage.type === 'input_request') {
      const promptText = String(parsedMessage.payload?.tip || 'Agent 请求输入')
      this.postPanelMessage(promptText, 'system')
      return
    }

    if (parsedMessage.type === 'execution') {
      const executionChunk = decodeExecutionChunk(parsedMessage.payload)
      if (!executionChunk) {
        return
      }
      this.panelState.terminalOutput = appendTerminalChunk(this.panelState.terminalOutput, executionChunk)
      this.postPanelState()
    }
  }

  private disposeSocket(socketKey: 'gatewaySocket' | 'agentSocket'): void {
    const socket = this.panelState[socketKey]
    if (!socket) {
      return
    }
    try {
      socket.close()
    } catch {
      // ignore close error
    }
    this.panelState[socketKey] = undefined
  }
}

interface ChatPanelMessage {
  type?: string
  gatewayUrl?: string
  password?: string
  text?: string
}

interface ModelGroupsResponse {
  success: boolean
  data?: Array<{
    name: string
    smart_model?: string
    normal_model?: string
    cheap_model?: string
  }>
  default_llm_group?: string
  error?: {
    message?: string
  }
}

interface LoginResponse {
  success: boolean
  data?: {
    token?: string
  }
  error?: {
    message?: string
  }
}

interface CreateAgentResponse {
  success: boolean
  data?: {
    agent_id?: string
    name?: string
    status?: string
    agent_type?: string
  }
  error?: {
    message?: string
  }
}

interface AgentListResponse {
  success: boolean
  data?: Array<{
    agent_id: string
    name?: string
    status?: string
    agent_type?: string
  }>
  error?: {
    message?: string
  }
}

function parseGatewayAddress(address: string): GatewayAddress {
  const trimmedAddress = address.trim()
  if (!trimmedAddress) {
    return { host: '127.0.0.1', port: '8000' }
  }
  if (trimmedAddress.includes('://')) {
    const url = new URL(trimmedAddress)
    const inferredPort = url.port || (url.protocol === 'https:' || url.protocol === 'wss:' ? '443' : '80')
    return { host: url.hostname, port: inferredPort }
  }
  if (trimmedAddress.includes(':')) {
    const [host, port] = trimmedAddress.split(':')
    return { host: host || '127.0.0.1', port: port || '8000' }
  }
  return { host: trimmedAddress, port: '8000' }
}

function buildHttpUrl(gatewayAddress: GatewayAddress, path: string): string {
  return `http://${gatewayAddress.host}:${gatewayAddress.port}${path}`
}

function buildWebSocketUrl(gatewayAddress: GatewayAddress): string {
  return `ws://${gatewayAddress.host}:${gatewayAddress.port}/ws`
}

function buildAgentWebSocketUrl(gatewayAddress: GatewayAddress, agentId: string): string {
  return `ws://${gatewayAddress.host}:${gatewayAddress.port}/api/agent/${agentId}/ws`
}

function parseSocketMessage(rawData: RawData): { type?: string; payload?: Record<string, unknown> } | null {
  let text: string
  if (typeof rawData === 'string') {
    text = rawData
  } else if (Buffer.isBuffer(rawData)) {
    text = rawData.toString('utf-8')
  } else if (rawData instanceof ArrayBuffer) {
    text = Buffer.from(rawData).toString('utf-8')
  } else if (Array.isArray(rawData)) {
    text = Buffer.concat(rawData).toString('utf-8')
  } else {
    return null
  }

  try {
    return JSON.parse(text) as { type?: string; payload?: Record<string, unknown> }
  } catch {
    return null
  }
}

function decodeExecutionChunk(payload: Record<string, unknown> | undefined): string {
  if (!payload) {
    return ''
  }
  const chunkData = String(payload.data || '')
  if (!chunkData) {
    return ''
  }
  const encoded = Boolean(payload.encoded)
  if (!encoded) {
    return chunkData
  }
  try {
    return Buffer.from(chunkData, 'base64').toString('utf-8')
  } catch {
    return chunkData
  }
}

function appendTerminalChunk(currentOutput: string, nextChunk: string): string {
  if (!nextChunk) {
    return currentOutput
  }
  if (!currentOutput || currentOutput === '暂无终端输出') {
    return nextChunk
  }
  return `${currentOutput}${nextChunk}`
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function activate(context: vscode.ExtensionContext): void {
  const provider = new JarvisAgentListViewProvider(context.extensionUri)

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(JarvisAgentListViewProvider.viewType, provider)
  )

  context.subscriptions.push(
    vscode.commands.registerCommand('jarvis.openPanel', async () => {
      await provider.openChatPanel()
    })
  )

  context.subscriptions.push(
    vscode.commands.registerCommand('jarvis.refreshAgents', async () => {
      await provider.openChatPanel()
    })
  )
}

export function deactivate(): void {}

function createNonce(): string {
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  return Array.from({ length: 32 }, () => possible.charAt(Math.floor(Math.random() * possible.length))).join('')
}
