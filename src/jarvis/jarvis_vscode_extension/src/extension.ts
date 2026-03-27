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

  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.currentView = webviewView
    webviewView.webview.options = {
      enableScripts: true
    }

    webviewView.webview.html = this.getAgentListHtml()

    webviewView.webview.onDidReceiveMessage(async (message: { type?: string; agentId?: string }) => {
      if (message?.type === 'openAgent') {
        await this.openChatPanel(message.agentId)
      }
      if (message?.type === 'refreshAgents') {
        await this.refreshAgents()
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
    const agentListMarkup = this.agentItems
      .map((agentItem) => {
        return `
    <li data-agent-id="${agentItem.id}">
      <div class="agent-name">${agentItem.displayName}</div>
      <div class="agent-meta">${agentItem.statusText}</div>
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
    .toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    button { border: 1px solid var(--vscode-button-border, transparent); background: var(--vscode-button-background); color: var(--vscode-button-foreground); padding: 6px 10px; cursor: pointer; }
    ul { list-style: none; padding: 0; margin: 0; }
    li { border: 1px solid var(--vscode-panel-border); border-radius: 6px; margin-bottom: 8px; padding: 8px; cursor: pointer; }
    .agent-name { font-weight: 600; }
    .agent-meta { opacity: 0.8; font-size: 12px; margin-top: 4px; }
  </style>
</head>
<body>
  <div class="toolbar">
    <strong>Agents</strong>
    <button id="refreshButton">刷新</button>
  </div>
  <ul>${agentListMarkup}
  </ul>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const refreshButton = document.getElementById('refreshButton');
    if (refreshButton) {
      refreshButton.addEventListener('click', () => {
        vscode.postMessage({ type: 'refreshAgents' });
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
  </style>
</head>
<body>
  <div class="layout">
    <div class="section">
      <div><strong>当前 Agent：</strong><span id="selectedAgentLabel">${selectedAgentLabel}</span></div>
      <div class="status">连接、对话与终端 MVP 面板</div>
    </div>
    <div class="section">
      <div class="row">
        <input id="gatewayUrl" placeholder="127.0.0.1:8000" />
        <input id="password" type="password" placeholder="密码（可选）" />
        <button id="connectButton">连接</button>
        <button id="loadAgentsButton">加载 Agents</button>
      </div>
      <div class="status" id="connectionStatus">未连接</div>
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
    const gatewayUrlInput = document.getElementById('gatewayUrl');
    const passwordInput = document.getElementById('password');
    const connectionStatus = document.getElementById('connectionStatus');
    const selectedAgentLabel = document.getElementById('selectedAgentLabel');

    function appendMessage(text, variant = 'system') {
      const item = document.createElement('div');
      item.className = 'message ' + variant;
      item.textContent = text;
      messages.appendChild(item);
      messages.scrollTop = messages.scrollHeight;
    }

    document.getElementById('connectButton').addEventListener('click', () => {
      vscode.postMessage({
        type: 'connect',
        gatewayUrl: gatewayUrlInput.value,
        password: passwordInput.value
      });
    });

    document.getElementById('loadAgentsButton').addEventListener('click', () => {
      vscode.postMessage({ type: 'loadAgents' });
    });

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
        gatewayUrlInput.value = data.payload.gatewayUrl || '';
        passwordInput.value = data.payload.password || '';
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
    if (message.type === 'connect') {
      await this.connectToGateway(message.gatewayUrl ?? '', message.password ?? '')
      return
    }
    if (message.type === 'loadAgents') {
      await this.refreshAgents()
      return
    }
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
      this.postPanelState()
      this.postPanelMessage('登录成功', 'system')
      this.connectGatewaySocket()
      await this.refreshAgents()
    } catch (error) {
      const errorMessage = getErrorMessage(error)
      this.panelState.connectionStatusText = `连接失败：${errorMessage}`
      this.panelState.hasConnectionError = true
      this.postPanelState()
      this.postPanelMessage(`连接失败：${errorMessage}`, 'error')
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

      if (this.currentView) {
        this.currentView.webview.html = this.getAgentListHtml()
      }
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

interface LoginResponse {
  success: boolean
  data?: {
    token?: string
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
