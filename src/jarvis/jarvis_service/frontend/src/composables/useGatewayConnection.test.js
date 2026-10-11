// useGatewayConnection 单元测试
// 覆盖：连接状态派生 / connect / disconnect / reconnect / 网关重启 /
// connectToAgent / autoConnectToOnlineAgents / 心跳（sendHeartbeat / checkHeartbeatTimeout）
// mock WebSocket / window.location / localStorage，与 useTerminal.test.js 风格一致。
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useGatewayConnection } from './useGatewayConnection.js'

// ---- mock 全局环境 ----
function setupGlobals() {
  // WebSocket
  class MockWebSocket {
    constructor(url, protocols) {
      this.url = url
      this.protocols = protocols
      this.readyState = 1 // OPEN
      this.send = vi.fn()
      this.close = vi.fn()
      this.onopen = null
      this.onmessage = null
      this.onclose = null
      this.onerror = null
      this._connectionCompleted = false // 预声明，preventExtensions 后仍可赋值
      // 防止被 vue ref 深响应式代理，使 socket.value === ws（与真实浏览器行为一致）
      Object.preventExtensions(this)
      MockWebSocket.instances.push(this)
    }
  }
  MockWebSocket.OPEN = 1
  MockWebSocket.CONNECTING = 0
  MockWebSocket.CLOSED = 3
  MockWebSocket.instances = []
  globalThis.WebSocket = MockWebSocket

  // window.location（buildDefaultGatewayUrl 使用）
  Object.defineProperty(globalThis, 'location', {
    value: { protocol: 'http:', hostname: 'localhost', reload: vi.fn() },
    writable: true,
    configurable: true,
  })

  // window.confirm（disconnectAll 使用）
  globalThis.confirm = vi.fn(() => true)
  globalThis.alert = vi.fn()
}

function makeHarness() {
  setupGlobals()
  const socket = ref(null)
  const sockets = ref(new Map())
  const auth = ref({ password: 'pw', token: '', userInfo: null })
  const username = ref('tester')
  const myClientId = ref('')
  const terminalSessions = ref([])
  const allOutputs = ref(new Map())
  const currentAgentId = ref('agent-1')
  const agentList = ref([])
  const agentStatuses = ref(new Map())
  const showConnectModal = ref(true)
  const showSettingsModal = ref(false)
  const autoLoginEnabled = ref(false)
  const userAccessibleNodes = ref(null)
  const gitCustomDir = ref(null)

  const parseGatewayAddress = vi.fn((address) => {
    const m = address.match(/^ws:\/\/([^:/]+):(\d+)$/)
    return m ? { host: m[1], port: m[2], protocol: null } : null
  })
  const buildWebSocketUrl = vi.fn((host, port, protocol) => `ws://${host}:${port}`)
  const buildWebSocketProtocols = vi.fn(() => [])
  const buildAgentWebSocketUrl = vi.fn((host, agentId, protocol, port, nodeId) => `ws://${host}:${port}/agent/${agentId}?node=${nodeId}`)
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/node/${nodeId}/${path}`)
  const fetchWithAuth = vi.fn()
  const loginWithPassword = vi.fn(async () => {})
  const hasAuthToken = vi.fn(() => true)
  const startAgentListRefresh = vi.fn()
  const startNodeStatusRefresh = vi.fn()
  const restoreVirtualWorkspaceDirs = vi.fn()
  const loadGitCustomDir = vi.fn(() => null)
  const refreshUserInfo = vi.fn(async () => {})
  const fetchUserPermissions = vi.fn()
  const fetchModelGroups = vi.fn()
  const fetchNodeStatus = vi.fn()
  const fetchUserAccessibleNodes = vi.fn()
  const restoreTerminalSessions = vi.fn()
  const getOrCreateClientId = vi.fn(() => 'client-test')
  const sendChatMessageToServer = vi.fn()
  const loadHistoryMessages = vi.fn()
  const closeTerminal = vi.fn()
  const handleMessage = vi.fn()
  const getAgentLastSeq = vi.fn(() => 0)
  const showToast = vi.fn()
  const showConfirm = vi.fn()

  const api = useGatewayConnection({
    socket,
    sockets,
    auth,
    username,
    myClientId,
    terminalSessions,
    allOutputs,
    currentAgentId,
    agentList,
    agentStatuses,
    showConnectModal,
    showSettingsModal,
    autoLoginEnabled,
    userAccessibleNodes,
    gitCustomDir,
    parseGatewayAddress,
    buildWebSocketUrl,
    buildWebSocketProtocols,
    buildAgentWebSocketUrl,
    getGatewayAddress,
    buildNodeHttpUrl,
    fetchWithAuth,
    loginWithPassword,
    hasAuthToken,
    startAgentListRefresh,
    startNodeStatusRefresh,
    restoreVirtualWorkspaceDirs,
    loadGitCustomDir,
    refreshUserInfo,
    fetchUserPermissions,
    fetchModelGroups,
    fetchNodeStatus,
    fetchUserAccessibleNodes,
    restoreTerminalSessions,
    getOrCreateClientId,
    sendChatMessageToServer,
    loadHistoryMessages,
    closeTerminal,
    handleMessage,
    getAgentLastSeq,
    showToast,
    showConfirm,
  })

  return {
    api, socket, sockets, auth, username, myClientId, terminalSessions, allOutputs,
    currentAgentId, agentList, agentStatuses, showConnectModal, showSettingsModal,
    autoLoginEnabled, userAccessibleNodes, gitCustomDir,
    lastPongTime: api.lastPongTime, connectingAgents: api.connectingAgents,
    userDisconnected: api.userDisconnected, isAutoConnecting: api.isAutoConnecting,
    reconnecting: api.reconnecting, reconnectAttempts: api.reconnectAttempts,
    reconnectTimer: api.reconnectTimer, connecting: api.connecting,
    agentConnecting: api.agentConnecting, connectErrorMessage: api.connectErrorMessage,
    isRestartingGateway: api.isRestartingGateway, restartNodeId: api.restartNodeId,
    restartFrontendService: api.restartFrontendService,
    parseGatewayAddress, buildWebSocketUrl, buildWebSocketProtocols, buildAgentWebSocketUrl,
    getGatewayAddress, buildNodeHttpUrl, fetchWithAuth, loginWithPassword, hasAuthToken,
    startAgentListRefresh, startNodeStatusRefresh, restoreVirtualWorkspaceDirs, loadGitCustomDir,
    refreshUserInfo, fetchUserPermissions, fetchModelGroups, fetchNodeStatus, fetchUserAccessibleNodes,
    restoreTerminalSessions, getOrCreateClientId, sendChatMessageToServer, loadHistoryMessages,
    closeTerminal, handleMessage, getAgentLastSeq, showToast, showConfirm,
  }
}

describe('useGatewayConnection', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('暴露预期接口', () => {
    const { api } = makeHarness()
    expect(typeof api.connect).toBe('function')
    expect(typeof api.disconnect).toBe('function')
    expect(typeof api.reconnect).toBe('function')
    expect(typeof api.disconnectAll).toBe('function')
    expect(typeof api.handleRestartGateway).toBe('function')
    expect(typeof api.confirmRestartGateway).toBe('function')
    expect(typeof api.restartGateway).toBe('function')
    expect(typeof api.connectToAgent).toBe('function')
    expect(typeof api.autoConnectToOnlineAgents).toBe('function')
    expect(typeof api.checkHeartbeatTimeout).toBe('function')
    expect(typeof api.sendHeartbeat).toBe('function')
  })

  it('初始状态：离线、未连接', () => {
    const { api } = makeHarness()
    expect(api.connectionStatus.value).toBe('offline')
    expect(api.connectionLabel.value).toBe('未连接')
    expect(api.connecting.value).toBe(false)
    expect(api.reconnecting.value).toBe(false)
    expect(api.userDisconnected.value).toBe(false)
    expect(api.HEARTBEAT_INTERVAL).toBe(5000)
    expect(api.HEARTBEAT_TIMEOUT).toBe(15000)
    expect(api.reconnectInterval).toBe(5000)
  })

  it('gatewayUrl 默认取 localStorage 或当前域名', () => {
    const { api } = makeHarness()
    // localStorage 无值时用 buildDefaultGatewayUrl：ws://localhost:8000
    expect(api.gatewayUrl.value).toBe('ws://localhost:8000')
  })

  it('gatewayUrl 优先读取 localStorage 保存值', () => {
    localStorage.setItem('jarvis_gateway_url', 'ws://myhost:9000')
    const { api } = makeHarness()
    expect(api.gatewayUrl.value).toBe('ws://myhost:9000')
  })

  describe('connectionStatus / connectionLabel', () => {
    it('connecting 时显示连接中', () => {
      const { api } = makeHarness()
      api.connecting.value = true
      expect(api.connectionStatus.value).toBe('connecting')
      expect(api.connectionLabel.value).toBe('连接中')
    })

    it('reconnecting 时显示重连中', () => {
      const { api } = makeHarness()
      api.reconnecting.value = true
      expect(api.connectionStatus.value).toBe('reconnecting')
      expect(api.connectionLabel.value).toBe('重连中')
    })

    it('socket 存在时显示已连接', () => {
      const { api, socket } = makeHarness()
      socket.value = { readyState: 1 }
      expect(api.connectionStatus.value).toBe('online')
      expect(api.connectionLabel.value).toBe('已连接')
    })
  })

  describe('connect', () => {
    it('已连接时不重复连接', async () => {
      const { api, socket, parseGatewayAddress } = makeHarness()
      socket.value = { readyState: 1 }
      await api.connect()
      expect(parseGatewayAddress).not.toHaveBeenCalled()
    })

    it('无效网关地址时设置错误信息', async () => {
      const { api } = makeHarness()
      api.gatewayUrl.value = 'invalid-address'
      await api.connect()
      expect(api.connectErrorMessage.value).toBe('无效的网关地址格式')
    })

    it('无 token 时调用 loginWithPassword 登录', async () => {
      const { api, hasAuthToken, loginWithPassword, socket, showConnectModal } = makeHarness()
      hasAuthToken.mockReturnValue(false)
      await api.connect()
      expect(loginWithPassword).toHaveBeenCalledWith('pw')
      // 登录后仍无 token → 登录失败
      expect(api.connectErrorMessage.value).toBe('登录失败，请重试')
      expect(socket.value).toBe(null)
      expect(showConnectModal.value).toBe(true)
    })

    it('登录失败时设置错误信息且不建立连接', async () => {
      const { api, hasAuthToken, loginWithPassword, socket } = makeHarness()
      hasAuthToken.mockReturnValue(false)
      loginWithPassword.mockRejectedValue(new Error('bad credentials'))
      await api.connect()
      expect(api.connectErrorMessage.value).toBe('bad credentials')
      expect(socket.value).toBe(null)
    })

    it('连接成功：onopen 建立 socket 并触发初始化流程', async () => {
      const { api, socket, showConnectModal, startAgentListRefresh, startNodeStatusRefresh,
        restoreVirtualWorkspaceDirs, loadGitCustomDir, refreshUserInfo, fetchUserPermissions,
        fetchModelGroups, fetchNodeStatus, fetchUserAccessibleNodes,
        restoreTerminalSessions, myClientId, getOrCreateClientId, sendChatMessageToServer,
        loadHistoryMessages } = makeHarness()
      await api.connect()
      // 触发 onopen 建立连接
      const ws = globalThis.WebSocket.instances[0]
      ws.onopen()
      // 等待 refreshUserInfo().finally(...) 等异步回调完成
      await new Promise(r => setTimeout(r, 0))
      // socket.value 是 ref 深响应式代理，不能与原始 ws 用 toBe 比较，改为断言 url
      expect(socket.value).not.toBe(null)
      expect(socket.value.url).toBe(ws.url)
      expect(showConnectModal.value).toBe(false)
      expect(api.connectionStatus.value).toBe('online')
      expect(startAgentListRefresh).toHaveBeenCalled()
      expect(startNodeStatusRefresh).toHaveBeenCalled()
      expect(restoreVirtualWorkspaceDirs).toHaveBeenCalled()
      expect(loadGitCustomDir).toHaveBeenCalled()
      expect(refreshUserInfo).toHaveBeenCalled()
      expect(fetchUserPermissions).toHaveBeenCalled()
      // autoConnectToOnlineAgents 是闭包内部函数无法直接 spy，
      // 通过 fetchModelGroups/fetchNodeStatus 等初始化副作用验证流程
      expect(fetchModelGroups).toHaveBeenCalled()
      expect(fetchNodeStatus).toHaveBeenCalled()
      expect(fetchUserAccessibleNodes).toHaveBeenCalled()
      expect(restoreTerminalSessions).toHaveBeenCalled()
      // 自动注册聊天室
      expect(getOrCreateClientId).toHaveBeenCalled()
      expect(myClientId.value).toBe('client-test')
      expect(sendChatMessageToServer).toHaveBeenCalledWith('chat_register', { client_id: 'client-test', name: 'tester' })
      // 无历史输出时加载历史消息
      expect(loadHistoryMessages).toHaveBeenCalledWith(false)
    })

    it('onmessage 解析 JSON 并交给 handleMessage', async () => {
      const { api, socket, handleMessage } = makeHarness()
      await api.connect()
      const ws = globalThis.WebSocket.instances[0]
      ws.onopen()
      ws.onmessage({ data: JSON.stringify({ type: 'hello', payload: {} }) })
      expect(handleMessage).toHaveBeenCalledWith({ type: 'hello', payload: {} })
    })

    it('onmessage 忽略旧连接消息', async () => {
      const { api, socket, handleMessage } = makeHarness()
      await api.connect()
      const oldWs = globalThis.WebSocket.instances[0]
      oldWs.onopen()
      // 模拟重连后 socket 指向新连接，旧连接收到消息应被忽略
      socket.value = { readyState: 1 }
      oldWs.onmessage({ data: JSON.stringify({ type: 'stale' }) })
      expect(handleMessage).not.toHaveBeenCalled()
    })

    it('onclose 销毁所有独立终端', async () => {
      const { api, socket, terminalSessions, closeTerminal } = makeHarness()
      terminalSessions.value = [{ terminal_id: 't1' }, { terminal_id: 't2' }]
      await api.connect()
      const ws = globalThis.WebSocket.instances[0]
      ws.onopen()
      ws.onclose({ code: 1000, reason: 'bye' })
      expect(closeTerminal).toHaveBeenCalledTimes(2)
      expect(closeTerminal).toHaveBeenCalledWith('t1')
      expect(closeTerminal).toHaveBeenCalledWith('t2')
    })

    it('onclose 用户未主动断开且有 token 时触发自动重连', async () => {
      const { api, socket, reconnectTimer } = makeHarness()
      await api.connect()
      const ws = globalThis.WebSocket.instances[0]
      ws.onopen()
      ws.onclose({ code: 1006, reason: '' })
      expect(api.reconnecting.value).toBe(true)
      expect(api.reconnectAttempts.value).toBe(1)
      expect(reconnectTimer.value).not.toBe(null)
    })

    it('onclose 用户主动断开时不重连', async () => {
      const { api, socket, userDisconnected } = makeHarness()
      await api.connect()
      const ws = globalThis.WebSocket.instances[0]
      ws.onopen()
      userDisconnected.value = true
      ws.onclose({ code: 1000, reason: 'bye' })
      expect(api.reconnecting.value).toBe(false)
      expect(api.reconnectAttempts.value).toBe(0)
      expect(api.reconnectAttempts.value).toBe(0)
    })
  })

  describe('disconnect', () => {
    it('设置用户主动断开标志并关闭连接', () => {
      const { api, socket, userDisconnected } = makeHarness()
      socket.value = { readyState: 1, close: vi.fn() }
      api.disconnect()
      expect(userDisconnected.value).toBe(true)
      expect(socket.value.close).toHaveBeenCalled()
    })

    it('无连接时安全调用', () => {
      const { api } = makeHarness()
      api.disconnect()
      expect(api.userDisconnected.value).toBe(true)
    })
  })

  describe('reconnect', () => {
    it('关闭现有连接并重新连接', async () => {
      const { api, socket, showSettingsModal } = makeHarness()
      socket.value = { readyState: 1, close: vi.fn() }
      await api.reconnect()
      expect(socket.value.close).toHaveBeenCalled()
      expect(showSettingsModal.value).toBe(false)
      // reconnect 内部调用 connect，会新建连接
      expect(socket.value).not.toBe(null)
    })
  })

  describe('disconnectAll', () => {
    it('用户取消时不执行断开', () => {
      const { api, socket } = makeHarness()
      globalThis.confirm.mockReturnValue(false)
      socket.value = { readyState: 1, close: vi.fn() }
      api.disconnectAll()
      expect(socket.value.close).not.toHaveBeenCalled()
    })

    it('确认后关闭所有连接并清空状态', () => {
      const { api, socket, sockets, currentAgentId, agentList, agentStatuses, auth, userAccessibleNodes, autoLoginEnabled } = makeHarness()
      const agentWs = { readyState: 1, close: vi.fn() }
      sockets.value.set('agent-1', agentWs)
      const mainWs = { readyState: 1, close: vi.fn() }
      socket.value = mainWs
      currentAgentId.value = 'agent-1'
      agentList.value = [{ agent_id: 'agent-1' }]
      agentStatuses.value.set('agent-1', {})
      auth.value.token = 'tok'
      userAccessibleNodes.value = ['n1']
      autoLoginEnabled.value = true
      api.disconnectAll()
      expect(agentWs.close).toHaveBeenCalled()
      expect(mainWs.close).toHaveBeenCalled()
      expect(sockets.value.size).toBe(0)
      expect(currentAgentId.value).toBe(null)
      expect(agentList.value).toEqual([])
      expect(agentStatuses.value.size).toBe(0)
      expect(auth.value.token).toBe('')
      expect(userAccessibleNodes.value).toBe(null)
      expect(autoLoginEnabled.value).toBe(false)
      expect(localStorage.getItem('jarvis_auth_token')).toBe(null)
    })
  })

  describe('handleRestartGateway / confirmRestartGateway', () => {
    it('handleRestartGateway 记录节点并弹确认框', () => {
      const { api, restartNodeId, restartFrontendService, showConfirm } = makeHarness()
      api.handleRestartGateway({ nodeId: 'node-9', restartFrontend: true })
      expect(restartNodeId.value).toBe('node-9')
      expect(restartFrontendService.value).toBe(true)
      expect(showConfirm).toHaveBeenCalled()
    })

    it('confirmRestartGateway 确认后调用 restartGateway', async () => {
      const { api, showConfirm, fetchWithAuth, buildNodeHttpUrl, getGatewayAddress, showToast } = makeHarness()
      // restartGateway 是闭包内部函数无法直接 spy，改为验证其副作用：
      // 确认回调触发后，restartGateway 会发起 HTTP 重启请求
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { message: '重启中' } }),
      })
      api.confirmRestartGateway()
      expect(showConfirm).toHaveBeenCalled()
      // 提取确认回调并执行
      const confirmCb = showConfirm.mock.calls[0][1]
      confirmCb()
      await new Promise(r => setTimeout(r, 0))
      expect(getGatewayAddress).toHaveBeenCalled()
      expect(buildNodeHttpUrl).toHaveBeenCalledWith('127.0.0.1', '8000', 'master', 'service/restart')
      expect(showToast).toHaveBeenCalledWith('重启中', 'success')
    })

    it('正在重启时不重复弹框', () => {
      const { api, showConfirm, isRestartingGateway } = makeHarness()
      isRestartingGateway.value = true
      api.confirmRestartGateway()
      expect(showConfirm).not.toHaveBeenCalled()
    })
  })

  describe('restartGateway', () => {
    it('发送重启请求并提示成功', async () => {
      const { api, fetchWithAuth, buildNodeHttpUrl, getGatewayAddress, showToast, isRestartingGateway } = makeHarness()
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { message: '重启中' } }),
      })
      await api.restartGateway()
      expect(getGatewayAddress).toHaveBeenCalled()
      expect(buildNodeHttpUrl).toHaveBeenCalledWith('127.0.0.1', '8000', 'master', 'service/restart')
      expect(showToast).toHaveBeenCalledWith('重启中', 'success')
    })

    it('后端返回失败时提示错误', async () => {
      const { api, fetchWithAuth, showToast } = makeHarness()
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: false, error: { message: '服务未运行' } }),
      })
      await api.restartGateway()
      expect(showToast).toHaveBeenCalledWith('服务未运行', 'error')
    })

    it('请求异常时提示错误', async () => {
      const { api, fetchWithAuth, showToast } = makeHarness()
      fetchWithAuth.mockRejectedValue(new Error('network down'))
      await api.restartGateway()
      expect(showToast).toHaveBeenCalledWith('network down', 'error')
    })
  })

  describe('connectToAgent', () => {
    it('连接锁存在时直接返回 null', async () => {
      const { api, connectingAgents } = makeHarness()
      connectingAgents.value.add('agent-1')
      const result = await api.connectToAgent({ agent_id: 'agent-1' })
      expect(result).toBe(null)
    })

    it('已存在有效连接时复用并发送 get_status', async () => {
      const { api, sockets } = makeHarness()
      const existingWs = { readyState: 1, send: vi.fn() }
      sockets.value.set('agent-1', existingWs)
      const result = await api.connectToAgent({ agent_id: 'agent-1' })
      // result 是 sockets.value 中 existingWs 的响应式代理，不能 toBe 比较，改为断言行为
      expect(result.readyState).toBe(1)
      expect(result.send).toHaveBeenCalledWith(JSON.stringify({ type: 'get_status', payload: {} }))
    })

    it('成功建立连接：保存 socket、发送 sync_request、resolve ws', async () => {
      const { api, sockets, getAgentLastSeq, allOutputs, agentConnecting } = makeHarness()
      const promise = api.connectToAgent({ agent_id: 'agent-1', node_id: 'node-1' })
      const ws = globalThis.WebSocket.instances[globalThis.WebSocket.instances.length - 1]
      // 触发 onopen
      ws.onopen()
      const result = await promise
      expect(result).toBe(ws)
      // sockets.value 中存的是 ws 的响应式代理，断言 url 一致
      expect(sockets.value.get('agent-1').url).toBe(ws.url)
      expect(agentConnecting.value).toBe(false)
      expect(allOutputs.value.has('agent-1')).toBe(true)
      expect(ws.send).toHaveBeenCalledWith(JSON.stringify({
        type: 'sync_request',
        payload: { agent_seqs: { 'agent-1': 0 } },
      }))
    })

    it('onmessage 收到 pong 时更新 lastPongTime 且不交给 handleMessage', async () => {
      const { api, sockets, lastPongTime, handleMessage } = makeHarness()
      const promise = api.connectToAgent({ agent_id: 'agent-1' })
      const ws = globalThis.WebSocket.instances[globalThis.WebSocket.instances.length - 1]
      ws.onopen()
      await promise
      // 连接建立时 lastPongTime 尚未记录，收到 pong 后应写入时间戳
      expect(lastPongTime.value.has('agent-1')).toBe(false)
      ws.onmessage({ data: JSON.stringify({ type: 'pong' }) })
      expect(lastPongTime.value.get('agent-1')).toBeTypeOf('number')
      expect(handleMessage).not.toHaveBeenCalled()
    })

    it('onmessage 普通消息交给 handleMessage（带 agentId）', async () => {
      const { api, sockets, handleMessage } = makeHarness()
      const promise = api.connectToAgent({ agent_id: 'agent-1' })
      const ws = globalThis.WebSocket.instances[globalThis.WebSocket.instances.length - 1]
      ws.onopen()
      await promise
      ws.onmessage({ data: JSON.stringify({ type: 'output', payload: {} }) })
      expect(handleMessage).toHaveBeenCalledWith({ type: 'output', payload: {} }, 'agent-1')
    })

    it('连接超时：reject 并清理连接状态', async () => {
      const { api, sockets, connectingAgents, agentConnecting } = makeHarness()
      // 使用假定时器加速超时
      vi.useFakeTimers()
      const promise2 = api.connectToAgent({ agent_id: 'agent-2' })
      vi.advanceTimersByTime(10000)
      await expect(promise2).rejects.toThrow('Connection timeout')
      expect(sockets.value.has('agent-2')).toBe(false)
      expect(connectingAgents.value.has('agent-2')).toBe(false)
      expect(agentConnecting.value).toBe(false)
      vi.useRealTimers()
    })
  })

  describe('autoConnectToOnlineAgents', () => {
    it('无在线 agent 时直接返回', async () => {
      const { api, agentList, sockets } = makeHarness()
      agentList.value = [{ agent_id: 'a1', status: 'stopped' }]
      await api.autoConnectToOnlineAgents()
      // 无在线 agent 时不建立任何连接
      expect(sockets.value.size).toBe(0)
      expect(globalThis.WebSocket.instances.length).toBe(0)
    })
    it('逐个连接在线 agent 并保持当前选中不变', async () => {
      const { api, agentList, sockets, currentAgentId } = makeHarness()
      agentList.value = [
        { agent_id: 'a1', status: 'running' },
        { agent_id: 'a2', status: 'running' },
      ]
      currentAgentId.value = 'keep-me'
      // autoConnectToOnlineAgents 内部逐个 await connectToAgent（含 500ms 间隔），
      // 需分步触发各 agent 的 onopen
      const p = api.autoConnectToOnlineAgents()
      // 第一个 agent 的 ws 已同步创建
      const wsA1 = globalThis.WebSocket.instances[0]
      wsA1.onopen()
      // 等待 500ms 间隔后第二个 agent 的 ws 创建
      await new Promise(r => setTimeout(r, 600))
      const wsA2 = globalThis.WebSocket.instances[1]
      wsA2.onopen()
      await p
      expect(currentAgentId.value).toBe('keep-me')
      expect(sockets.value.has('a1')).toBe(true)
      expect(sockets.value.has('a2')).toBe(true)
    })
  })

  describe('心跳', () => {
    it('sendHeartbeat 向所有开放连接发送 ping 并记录时间', () => {
      const { api, sockets, lastPongTime } = makeHarness()
      const ws1 = { readyState: 1, send: vi.fn() }
      const ws2 = { readyState: 1, send: vi.fn() }
      sockets.value.set('a1', ws1)
      sockets.value.set('a2', ws2)
      api.sendHeartbeat()
      expect(ws1.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))
      expect(ws2.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))
      expect(lastPongTime.value.has('a1')).toBe(true)
      expect(lastPongTime.value.has('a2')).toBe(true)
    })

    it('sendHeartbeat 跳过未开放连接', () => {
      const { api, sockets } = makeHarness()
      const wsClosed = { readyState: 3, send: vi.fn() }
      sockets.value.set('a1', wsClosed)
      api.sendHeartbeat()
      expect(wsClosed.send).not.toHaveBeenCalled()
    })

    it('checkHeartbeatTimeout 超时连接被清理并触发当前 Agent 重连', () => {
      const { api, sockets, lastPongTime, connectingAgents, currentAgentId, agentList } = makeHarness()
      const ws = { readyState: 1, close: vi.fn() }
      sockets.value.set('a1', ws)
      // 超时：无 lastPong
      lastPongTime.value.delete('a1')
      currentAgentId.value = 'a1'
      const agent = { agent_id: 'a1' }
      agentList.value = [agent]
      const wsCountBefore = globalThis.WebSocket.instances.length
      api.checkHeartbeatTimeout()
      expect(ws.close).toHaveBeenCalled()
      expect(sockets.value.has('a1')).toBe(false)
      // 触发重连后 connectToAgent 重新加连接锁（重连进行中）
      expect(connectingAgents.value.has('a1')).toBe(true)
      // connectToAgent 是闭包内部函数无法直接 spy，验证其副作用：
      // 触发重连会创建新的 WebSocket 连接
      expect(globalThis.WebSocket.instances.length).toBe(wsCountBefore + 1)
    })

    it('checkHeartbeatTimeout 未超时连接保留', () => {
      const { api, sockets, lastPongTime } = makeHarness()
      const ws = { readyState: 1, close: vi.fn() }
      sockets.value.set('a1', ws)
      lastPongTime.value.set('a1', Date.now())
      api.checkHeartbeatTimeout()
      expect(ws.close).not.toHaveBeenCalled()
      expect(sockets.value.has('a1')).toBe(true)
    })
  })
})
