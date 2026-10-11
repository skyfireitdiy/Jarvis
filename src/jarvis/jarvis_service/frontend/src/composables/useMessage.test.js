// useMessage 单元测试
// monaco 在 jsdom 不可用，mock 整个 monaco 模块（useMessage 顶层 import monaco-editor 用于 handleEditorOpenFile）
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
// ---- mock monaco 模块（useMessage 顶层 import monaco-editor 会执行）----
const { monacoMock } = vi.hoisted(() => {
  const monacoMock = {
    editor: {
      defineTheme: vi.fn(),
      registerEditorOpener: vi.fn(),
      createModel: vi.fn(() => ({ isDisposed: () => false, setValue: vi.fn(), getValue: vi.fn(() => ''), getLanguageId: () => 'plaintext' })),
      create: vi.fn(() => ({
        getModel: vi.fn(() => null),
        setModel: vi.fn(),
        updateOptions: vi.fn(),
        layout: vi.fn(),
        dispose: vi.fn(),
        focus: vi.fn(),
        revealLineInCenter: vi.fn(),
        setPosition: vi.fn(),
        setSelection: vi.fn(),
        getSelection: vi.fn(() => null),
        getContainerDomNode: vi.fn(() => ({ isConnected: true })),
        onDidFocusEditorText: vi.fn(),
        onDidChangeModelContent: vi.fn(),
        onDidChangeCursorPosition: vi.fn(),
        addAction: vi.fn(),
        saveViewState: vi.fn(() => null),
        restoreViewState: vi.fn(),
        trigger: vi.fn(),
      })),
      getModel: vi.fn(() => null),
    },
    Uri: {
      file: vi.fn((p) => ({ toString: () => `file://${p}` })),
    },
    Selection: vi.fn((sl, sc, el, ec) => ({ startLineNumber: sl, startColumn: sc, endLineNumber: el, endColumn: ec })),
    KeyCode: { F12: 1, LeftArrow: 2, RightArrow: 3, KeyP: 4 },
    KeyMod: { CtrlCmd: 1, Alt: 2 },
  }
  return { monacoMock }
})
vi.mock('monaco-editor/esm/vs/editor/editor.main.js', () => monacoMock)
// ---- 引入被测模块（须在 mock 之后）----
const { useMessage } = await import('./useMessage.js')

// 构造测试 harness，注入全部依赖
function makeHarness(overrides = {}) {
  const currentAgentId = ref('agent-1')
  const outputList = ref(null)
  const inputText = ref('')
  const inputBuffers = ref(new Map())
  const panelConfirmData = ref(new Map())
  const inputMode = ref('multi')
  const agentStatuses = ref(new Map())
  const panelInputTexts = ref(new Map())
  const inputRequests = ref(new Map())
  const agentList = ref([])
  const allOutputs = ref(new Map())
  const pendingConfirmAgentId = ref(null)
  const pendingInputAgentId = ref(null)
  const panels = ref([])
  const sockets = ref(new Map())
  const socket = ref(null)
  const inputTip = ref('')
  const panelInputTips = ref(new Map())
  const panelInputModes = ref(new Map())
  const streamingMessages = ref(new Map())
  const bufferPanelAgentId = ref(null)
  const bufferEditText = ref('')
  const panelOutputLists = ref(new Map())
  const chatName = ref('')
  const username = ref('test-user')
  const showBufferPanel = ref(false)
  const panelInputPasswords = ref(new Map())
  const sessionPanelRefs = ref(new Map())
  const confirmDialog = ref(null)
  const historyOffset = ref(0)
  const hasMoreHistory = ref(true)
  const auth = ref({ password: '' })
  const showConnectModal = ref(false)
  const pipelineStore = ref({})
  const notifyOnExit = ref(true)
  const notifyOnInput = ref(true)

  const isCurrentAgent = vi.fn(() => true)
  const isAutoScrollEnabled = vi.fn(() => true)
  const isAnyModalOpen = vi.fn(() => false)
  const showToast = vi.fn()
  const sendSystemNotification = vi.fn()
  const notifyInputRequest = vi.fn()
  const handleAutoRead = vi.fn()
  const sendMessageToAgent = vi.fn()
  const loadHistoryMessages = vi.fn()
  const getActiveWorkspaceView = vi.fn(() => null)
  const onPipelineEvent = vi.fn()
  const handleChatMessage = vi.fn()
  const resolveAgentRelativePath = vi.fn((path) => path)
  const openWorkspaceFile = vi.fn()
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/node/${nodeId}/${path}`)
  const fetchWithAuth = vi.fn()
  const showConfirm = vi.fn()
  const connectErrorMessage = ref('')
  const ensureAgentEditorPane = vi.fn()
  const editorModels = new Map()

  const terminalSessions = ref([])
  const appendExecution = vi.fn()
  const getExecutionSessionKey = vi.fn((agentId, executionId) => `${agentId}:${executionId}`)
  const isCreatingTerminalSession = ref(false)
  const terminalCreationTracker = { shouldSwitch: vi.fn(() => true) }
  const activeTerminalId = ref(null)
  const independentTerminalHosts = ref(new Map())
  const initIndependentTerminal = vi.fn()
  const attachTerminalSession = vi.fn()
  const closeTerminal = vi.fn()

  const api = useMessage({
    outputList,
    currentAgentId,
    inputText,
    inputBuffers,
    panelConfirmData,
    inputMode,
    agentStatuses,
    panelInputTexts,
    inputRequests,
    agentList,
    allOutputs,
    pendingConfirmAgentId,
    pendingInputAgentId,
    panels,
    sockets,
    socket,
    inputTip,
    panelInputTips,
    panelInputModes,
    streamingMessages,
    bufferPanelAgentId,
    bufferEditText,
    panelOutputLists,
    chatName,
    username,
    showBufferPanel,
    panelInputPasswords,
    sessionPanelRefs,
    confirmDialog,
    historyOffset,
    hasMoreHistory,
    auth,
    showConnectModal,
    pipelineStore,
    notifyOnExit,
    notifyOnInput,
    isCurrentAgent,
    isAutoScrollEnabled,
    isAnyModalOpen,
    showToast,
    sendSystemNotification,
    notifyInputRequest,
    handleAutoRead,
    sendMessageToAgent,
    loadHistoryMessages,
    getActiveWorkspaceView,
    onPipelineEvent,
    handleChatMessage,
    resolveAgentRelativePath,
    openWorkspaceFile,
    getGatewayAddress,
    buildNodeHttpUrl,
    fetchWithAuth,
    showConfirm,
    terminalSessions,
    appendExecution,
    getExecutionSessionKey,
    isCreatingTerminalSession,
    terminalCreationTracker,
    activeTerminalId,
    independentTerminalHosts,
    initIndependentTerminal,
    attachTerminalSession,
    closeTerminal,
    connectErrorMessageGetter: () => connectErrorMessage,
    ensureAgentEditorPane,
    editorModels,
    ...overrides,
  })
  return {
    api,
    currentAgentId,
    outputList,
    inputText,
    inputBuffers,
    panelConfirmData,
    inputMode,
    agentStatuses,
    panelInputTexts,
    inputRequests,
    agentList,
    allOutputs,
    pendingConfirmAgentId,
    pendingInputAgentId,
    panels,
    sockets,
    socket,
    inputTip,
    panelInputTips,
    panelInputModes,
    streamingMessages,
    bufferPanelAgentId,
    bufferEditText,
    panelOutputLists,
    chatName,
    username,
    showBufferPanel,
    panelInputPasswords,
    sessionPanelRefs,
    confirmDialog,
    historyOffset,
    hasMoreHistory,
    auth,
    showConnectModal,
    notifyOnExit,
    notifyOnInput,
    isCurrentAgent,
    isAutoScrollEnabled,
    isAnyModalOpen,
    showToast,
    sendSystemNotification,
    notifyInputRequest,
    handleAutoRead,
    sendMessageToAgent,
    loadHistoryMessages,
    onPipelineEvent,
    handleChatMessage,
    connectErrorMessage,
    showConfirm,
    terminalSessions,
    appendExecution,
    isCreatingTerminalSession,
    terminalCreationTracker,
    activeTerminalId,
    independentTerminalHosts,
    initIndependentTerminal,
    attachTerminalSession,
    closeTerminal,
  }
}

function makeWs(open = true) {
  return {
    readyState: open ? WebSocket.OPEN : WebSocket.CLOSED,
    sent: [],
    send: vi.fn(function (data) { this.sent.push(data) }),
  }
}

describe('useMessage', () => {
  it('暴露预期接口（32 个符号）', () => {
    const { api } = makeHarness()
    const expected = [
      'syncAgentInputMode', 'handleMessage', 'handleEvalJsRequest', 'handleEditorOpenFile',
      'getEditorSelection', 'sendSelectionToAgent', 'safeSerialize', 'renderMessageHtml',
      'appendOutput', 'scrollSessionToBottom', 'copyToClipboard', 'isCursorAtFirstLine',
      'isCursorAtLastLine', 'pendingFileUploads', 'handleFileUploadResponse', 'uploadImageToNode',
      'insertTextAtCursor', 'closeBufferPanelIfForAgent', 'updateInputBuffer', 'appendToInputBuffer',
      'submitCompletion', 'sendInputDirectly', 'sendInputResult', 'sendBufferedInput',
      'clearBuffer', 'loadBufferToInput', 'saveBufferEdit', 'sendConfirmResult',
      'handlePanelConfirm', 'handlePanelCancelConfirm', 'restoreWaitingConfirmUI', 'sendMessageToAgentById',
    ]
    for (const name of expected) {
      if (name === 'pendingFileUploads') {
        expect(api[name]).toBeInstanceOf(Map)
      } else {
        expect(typeof api[name], name).toBe('function')
      }
    }
  })

  describe('renderMessageHtml', () => {
    it('markdown 消息渲染为 HTML', () => {
      const { api } = makeHarness()
      const html = api.renderMessageHtml({ text: '# 标题', lang: 'markdown' })
      expect(html).toContain('<h1')
    })
    it('diff 消息包装为代码块', () => {
      const { api } = makeHarness()
      const html = api.renderMessageHtml({ text: '--- a\n+++ b', lang: 'diff' })
      expect(html).toContain('diff')
    })
    it('普通文本转义 HTML', () => {
      const { api } = makeHarness()
      const html = api.renderMessageHtml({ text: '<script>alert(1)</script>', lang: 'text' })
      expect(html).not.toContain('<script>')
      expect(html).toContain('&lt;script&gt;')
    })
  })

  describe('appendOutput', () => {
    it('过滤 __CTRL_C_PRESSED__ 内部控制信号', () => {
      const { api, allOutputs } = makeHarness()
      api.appendOutput({ text: '__CTRL_C_PRESSED__', output_type: 'user_input' }, 'agent-1')
      expect(allOutputs.value.get('agent-1')).toBeUndefined()
    })
    it('追加普通输出到目标 Agent 列表', () => {
      const { api, allOutputs } = makeHarness()
      // 真实行为：allOutputs Map 需预置该 agent 的数组（loadHistoryMessages 会先 set）
      allOutputs.value.set('agent-1', [])
      api.appendOutput({ text: 'hello', output_type: 'stdout', lang: 'text' }, 'agent-1')
      const items = allOutputs.value.get('agent-1')
      expect(items).toHaveLength(1)
      expect(items[0].text).toBe('hello')
      expect(items[0].agent_id).toBe('agent-1')
      expect(items[0]._stableId).toBeTruthy()
    })
    it('execution 消息按 execution_id 去重', () => {
      const { api, allOutputs } = makeHarness()
      allOutputs.value.set('agent-1', [])
      api.appendOutput({ text: 'run1', output_type: 'execution', execution_id: 'exec-1' }, 'agent-1')
      api.appendOutput({ text: 'run1-dup', output_type: 'execution', execution_id: 'exec-1' }, 'agent-1')
      const items = allOutputs.value.get('agent-1')
      expect(items).toHaveLength(1)
    })
    it('seq 去重：相同 seq 的消息跳过', () => {
      const { api, allOutputs } = makeHarness()
      allOutputs.value.set('agent-1', [])
      api.appendOutput({ text: 'a', output_type: 'stdout', seq: 5 }, 'agent-1')
      api.appendOutput({ text: 'b', output_type: 'stdout', seq: 5 }, 'agent-1')
      const items = allOutputs.value.get('agent-1')
      expect(items).toHaveLength(1)
      expect(items[0].text).toBe('a')
    })
  })

  describe('handleMessage', () => {
    it('ready：恢复输入请求状态', () => {
      const { api, inputRequests, inputTip, inputMode, pendingInputAgentId, panelInputTips, inputText } = makeHarness()
      inputRequests.value.set('agent-1', { tip: '请回答', mode: 'multi', preset: '默认值' })
      api.handleMessage({ type: 'ready', payload: {}, seq: 1 }, 'agent-1')
      expect(inputTip.value).toBe('请回答')
      expect(inputMode.value).toBe('multi')
      expect(inputText.value).toBe('默认值')
      expect(pendingInputAgentId.value).toBe('agent-1')
      expect(panelInputTips.value.get('agent-1')).toBe('请回答')
    })

    it('output 普通输出：调用 appendOutput', () => {
      const { api, allOutputs } = makeHarness()
      allOutputs.value.set('agent-1', [])
      api.handleMessage({ type: 'output', payload: { text: 'hi', output_type: 'stdout' }, seq: 3 }, 'agent-1')
      const items = allOutputs.value.get('agent-1')
      expect(items).toHaveLength(1)
      expect(items[0].text).toBe('hi')
    })

    it('output STREAM_START/CHUNK/END：流式消息合并', () => {
      const { api, allOutputs, streamingMessages } = makeHarness()
      allOutputs.value.set('agent-1', [])
      api.handleMessage({ type: 'output', payload: { output_type: 'STREAM_START', text: '' }, seq: 1 }, 'agent-1')
      // STREAM_START 后流式消息进入 allOutputs 与 streamingMessages
      expect(streamingMessages.value.has('agent-1')).toBe(true)
      let items = allOutputs.value.get('agent-1')
      expect(items).toHaveLength(1)
      expect(items[0].output_type).toBe('STREAM')
      // STREAM_CHUNK 累积文本
      api.handleMessage({ type: 'output', payload: { output_type: 'STREAM_CHUNK', text: 'Hello' }, seq: 2 }, 'agent-1')
      api.handleMessage({ type: 'output', payload: { output_type: 'STREAM_CHUNK', text: ' World' }, seq: 3 }, 'agent-1')
      expect(streamingMessages.value.get('agent-1').text).toBe('Hello World')
      // STREAM_END 后流式消息被移除（从 allOutputs 与 streamingMessages）
      api.handleMessage({ type: 'output', payload: { output_type: 'STREAM_END', text: '' }, seq: 4 }, 'agent-1')
      expect(streamingMessages.value.has('agent-1')).toBe(false)
      items = allOutputs.value.get('agent-1')
      expect(items).toHaveLength(0)
    })

    it('input_request：保存输入请求并触发提示音', () => {
      const { api, inputRequests, notifyInputRequest, handleAutoRead, pendingInputAgentId } = makeHarness()
      api.handleMessage({ type: 'input_request', payload: { tip: '输入', mode: 'multi' }, seq: 1 }, 'agent-1')
      expect(pendingInputAgentId.value).toBe('agent-1')
      expect(inputRequests.value.has('agent-1')).toBe(true)
      expect(notifyInputRequest).toHaveBeenCalled()
      expect(handleAutoRead).toHaveBeenCalledWith('agent-1', 'waiting_multi')
    })

    it('input_request：缓冲区有内容时直接发送', () => {
      const { api, inputBuffers, sockets } = makeHarness()
      const ws = makeWs(true)
      sockets.value.set('agent-1', ws)
      inputBuffers.value.set('agent-1', '缓冲内容')
      api.handleMessage({ type: 'input_request', payload: { mode: 'multi', request_id: 'req-1' }, seq: 1 }, 'agent-1')
      expect(inputBuffers.value.has('agent-1')).toBe(false)
      expect(ws.sent).toHaveLength(1)
      const sentMsg = JSON.parse(ws.sent[0])
      expect(sentMsg.type).toBe('input_result')
      expect(sentMsg.payload.text).toBe('缓冲内容')
      expect(sentMsg.payload.request_id).toBe('req-1')
    })

    it('confirm：设置确认数据与状态', () => {
      const { api, pendingConfirmAgentId, agentStatuses, panelConfirmData, inputMode, notifyInputRequest } = makeHarness()
      api.handleMessage({ type: 'confirm', payload: { message: '继续?', default: false }, seq: 1 }, 'agent-1')
      expect(pendingConfirmAgentId.value).toBe('agent-1')
      expect(agentStatuses.value.get('agent-1').execution_status).toBe('waiting_confirm')
      expect(panelConfirmData.value.get('agent-1').message).toBe('继续?')
      expect(panelConfirmData.value.get('agent-1').defaultConfirm).toBe(false)
      expect(inputMode.value).toBe('single')
      expect(notifyInputRequest).toHaveBeenCalled()
    })

    it('execution：调用 appendExecution 并创建输出项', () => {
      const { api, appendExecution, allOutputs } = makeHarness()
      allOutputs.value.set('agent-1', [])
      api.handleMessage({ type: 'execution', payload: { execution_id: 'exec-1', status: 'running' }, seq: 1 }, 'agent-1')
      expect(appendExecution).toHaveBeenCalled()
      const items = allOutputs.value.get('agent-1')
      const execItem = items.find(i => i.output_type === 'execution')
      expect(execItem).toBeTruthy()
      expect(execItem.execution_id).toBe('exec-1')
    })

    it('terminal_created：推入会话并初始化终端', () => {
      const { api, terminalSessions, activeTerminalId, independentTerminalHosts, attachTerminalSession, isCreatingTerminalSession } = makeHarness()
      independentTerminalHosts.value.set('term-1', {})
      api.handleMessage({ type: 'terminal_created', payload: { terminal_id: 'term-1', node_id: 'node-1' }, seq: 1 }, 'agent-1')
      expect(isCreatingTerminalSession.value).toBe(false)
      expect(terminalSessions.value).toHaveLength(1)
      expect(terminalSessions.value[0].terminal_id).toBe('term-1')
      expect(activeTerminalId.value).toBe('term-1')
      expect(attachTerminalSession).toHaveBeenCalledWith('term-1')
    })

    it('terminal_closed：关闭已存在的终端', () => {
      const { api, terminalSessions, closeTerminal } = makeHarness()
      terminalSessions.value.push({ terminal_id: 'term-1', node_id: 'node-1' })
      api.handleMessage({ type: 'terminal_closed', payload: { terminal_id: 'term-1' }, seq: 1 }, 'agent-1')
      expect(closeTerminal).toHaveBeenCalledWith('term-1')
    })

    it('error AUTH_FAILED：设置错误信息并打开连接对话框', () => {
      const { api, connectErrorMessage, auth, showConnectModal } = makeHarness()
      api.handleMessage({ type: 'error', payload: { message: '认证失败', code: 'AUTH_FAILED' }, seq: 1 }, 'agent-1')
      expect(connectErrorMessage.value).toBe('认证失败')
      expect(auth.value.password).toBe('')
      expect(showConnectModal.value).toBe(true)
    })

    it('error FORBIDDEN：显示 toast', () => {
      const { api, showToast } = makeHarness()
      api.handleMessage({ type: 'error', payload: { message: '无权限', code: 'FORBIDDEN' }, seq: 1 }, 'agent-1')
      expect(showToast).toHaveBeenCalledWith('无权限', 'error')
    })

    it('pipeline_event：转发给 onPipelineEvent', () => {
      const { api, onPipelineEvent } = makeHarness()
      const payload = { pipeline_id: 'p1', status: 'running' }
      api.handleMessage({ type: 'pipeline_event', payload, seq: 1 }, 'agent-1')
      expect(onPipelineEvent).toHaveBeenCalledWith(payload)
    })

    it('status_update running：清除等待输入/确认状态', () => {
      const { api, agentStatuses, inputRequests, pendingConfirmAgentId, confirmDialog, panelConfirmData } = makeHarness()
      agentStatuses.value.set('agent-1', { execution_status: 'waiting_multi' })
      inputRequests.value.set('agent-1', { tip: 'x' })
      pendingConfirmAgentId.value = 'agent-1'
      confirmDialog.value = { message: '确认' }
      panelConfirmData.value.set('agent-1', { message: '确认' })
      api.handleMessage({ type: 'status_update', payload: { execution_status: 'running' }, seq: 1 }, 'agent-1')
      expect(agentStatuses.value.get('agent-1').execution_status).toBe('running')
      expect(inputRequests.value.has('agent-1')).toBe(false)
      expect(pendingConfirmAgentId.value).toBe(null)
      expect(confirmDialog.value).toBe(null)
      expect(panelConfirmData.value.has('agent-1')).toBe(false)
    })

    it('status_update finished：发送退出通知', () => {
      const { api, agentList, sendSystemNotification } = makeHarness()
      agentList.value = [{ agent_id: 'agent-1', name: '测试Agent' }]
      api.handleMessage({ type: 'status_update', payload: { execution_status: 'finished' }, seq: 1 }, 'agent-1')
      expect(sendSystemNotification).toHaveBeenCalledWith('测试Agent 已退出')
    })

    it('chat_ 前缀消息：转发给 handleChatMessage', () => {
      const { api, handleChatMessage } = makeHarness()
      const payload = { text: 'hi' }
      api.handleMessage({ type: 'chat_message', payload, seq: 1 }, 'agent-1')
      expect(handleChatMessage).toHaveBeenCalledWith('chat_message', payload)
    })

    it('file_upload_response：转发给 handleFileUploadResponse', () => {
      const { api } = makeHarness()
      const resolve = vi.fn()
      api.pendingFileUploads.set('msg-1', resolve)
      api.handleMessage({ type: 'file_upload_response', payload: { message_id: 'msg-1', success: true, file_path: '/tmp/x.png' }, seq: 1 }, 'agent-1')
      expect(resolve).toHaveBeenCalledWith('/tmp/x.png')
    })
  })

  describe('sendInputResult / sendConfirmResult / sendMessageToAgentById', () => {
    it('sendInputResult：向 Agent socket 发送 input_result', () => {
      const { api, sockets, inputRequests, pendingInputAgentId } = makeHarness()
      const ws = makeWs(true)
      sockets.value.set('agent-1', ws)
      inputRequests.value.set('agent-1', { tip: 'x' })
      pendingInputAgentId.value = 'agent-1'
      api.sendInputResult('我的回答', 'req-1', 'agent-1', 'multi')
      expect(ws.sent).toHaveLength(1)
      const sentMsg = JSON.parse(ws.sent[0])
      expect(sentMsg.type).toBe('input_result')
      expect(sentMsg.payload.text).toBe('我的回答')
      expect(sentMsg.payload.request_id).toBe('req-1')
      expect(inputRequests.value.has('agent-1')).toBe(false)
      expect(pendingInputAgentId.value).toBe(null)
    })

    it('sendConfirmResult：发送 confirm_result 并恢复状态', () => {
      const { api, sockets, agentStatuses, panelConfirmData, inputMode, pendingConfirmAgentId } = makeHarness()
      const ws = makeWs(true)
      sockets.value.set('agent-1', ws)
      agentStatuses.value.set('agent-1', { execution_status: 'waiting_confirm' })
      panelConfirmData.value.set('agent-1', { message: '确认' })
      pendingConfirmAgentId.value = 'agent-1'
      api.sendConfirmResult(true, 'agent-1')
      expect(ws.sent).toHaveLength(1)
      const sentMsg = JSON.parse(ws.sent[0])
      expect(sentMsg.type).toBe('confirm_result')
      expect(sentMsg.payload.confirmed).toBe(true)
      expect(agentStatuses.value.get('agent-1').execution_status).toBe('running')
      expect(panelConfirmData.value.has('agent-1')).toBe(false)
      expect(inputMode.value).toBe('multi')
      expect(pendingConfirmAgentId.value).toBe(null)
    })

    it('sendMessageToAgentById：向指定 Agent socket 发送消息', () => {
      const { api, sockets } = makeHarness()
      const ws = makeWs(true)
      sockets.value.set('agent-1', ws)
      api.sendMessageToAgentById('agent-1', { type: 'interrupt', payload: {} })
      expect(ws.sent).toHaveLength(1)
      expect(JSON.parse(ws.sent[0]).type).toBe('interrupt')
    })
  })

  describe('缓冲区操作', () => {
    it('updateInputBuffer / appendToInputBuffer', () => {
      const { api, inputBuffers, bufferEditText } = makeHarness()
      api.updateInputBuffer('agent-1', '第一行')
      api.appendToInputBuffer('agent-1', '第二行')
      expect(inputBuffers.value.get('agent-1')).toBe('第一行\n第二行')
      expect(bufferEditText.value).toBe('第一行\n第二行')
    })

    it('sendBufferedInput：发送并清空缓冲区', () => {
      const { api, inputBuffers, sendMessageToAgent, showBufferPanel, bufferPanelAgentId } = makeHarness()
      inputBuffers.value.set('agent-1', '缓冲内容')
      bufferPanelAgentId.value = 'agent-1'
      showBufferPanel.value = true
      api.sendBufferedInput('agent-1')
      expect(inputBuffers.value.has('agent-1')).toBe(false)
      expect(sendMessageToAgent).toHaveBeenCalledTimes(1)
      const [msg, agentId] = sendMessageToAgent.mock.calls[0]
      expect(msg.type).toBe('input_result')
      expect(msg.payload.text).toBe('缓冲内容')
      expect(agentId).toBe('agent-1')
      expect(showBufferPanel.value).toBe(false)
    })

    it('clearBuffer：清空并关闭面板', () => {
      const { api, inputBuffers, bufferPanelAgentId, showBufferPanel, allOutputs } = makeHarness()
      allOutputs.value.set('agent-1', [])
      inputBuffers.value.set('agent-1', '内容')
      bufferPanelAgentId.value = 'agent-1'
      showBufferPanel.value = true
      api.clearBuffer()
      expect(inputBuffers.value.has('agent-1')).toBe(false)
      expect(showBufferPanel.value).toBe(false)
      const items = allOutputs.value.get('agent-1')
      expect(items.some(i => i.text.includes('缓冲区已清空'))).toBe(true)
    })
  })

  describe('safeSerialize / 光标判断', () => {
    it('safeSerialize：undefined 转 null', () => {
      const { api } = makeHarness()
      expect(api.safeSerialize(undefined)).toBe(null)
    })
    it('safeSerialize：可序列化对象原样返回', () => {
      const { api } = makeHarness()
      expect(api.safeSerialize({ a: 1, b: 'x' })).toEqual({ a: 1, b: 'x' })
    })
    it('safeSerialize：循环引用降级为字符串', () => {
      const { api } = makeHarness()
      const obj = {}
      obj.self = obj
      const result = api.safeSerialize(obj)
      expect(typeof result).toBe('string')
    })
    it('isCursorAtFirstLine / isCursorAtLastLine', () => {
      const { api } = makeHarness()
      const ta = { value: 'line1\nline2\nline3', selectionStart: 3, selectionEnd: 3 }
      expect(api.isCursorAtFirstLine(ta)).toBe(true)
      ta.selectionStart = 8
      ta.selectionEnd = 8
      expect(api.isCursorAtFirstLine(ta)).toBe(false)
      const ta2 = { value: 'line1\nline2', selectionStart: 6, selectionEnd: 6 }
      expect(api.isCursorAtLastLine(ta2)).toBe(true)
      ta2.selectionEnd = 3
      expect(api.isCursorAtLastLine(ta2)).toBe(false)
    })
  })

  describe('handlePanelConfirm / handlePanelCancelConfirm', () => {
    it('有 onConfirm 回调时调用并清理', () => {
      const { api, panelConfirmData, panelInputTexts, inputText } = makeHarness()
      const onConfirm = vi.fn()
      panelConfirmData.value.set('agent-1', { message: '确认', onConfirm })
      api.handlePanelConfirm({ agentId: 'agent-1' })
      expect(onConfirm).toHaveBeenCalled()
      expect(panelConfirmData.value.has('agent-1')).toBe(false)
      expect(panelInputTexts.value.get('agent-1')).toBe('')
      expect(inputText.value).toBe('')
    })

    it('无回调时走 sendConfirmResult(true)', () => {
      const { api, sockets, panelConfirmData } = makeHarness()
      const ws = makeWs(true)
      sockets.value.set('agent-1', ws)
      panelConfirmData.value.set('agent-1', { message: '确认' })
      api.handlePanelConfirm({ agentId: 'agent-1' })
      expect(JSON.parse(ws.sent[0]).payload.confirmed).toBe(true)
    })

    it('handlePanelCancelConfirm：无回调时走 sendConfirmResult(false)', () => {
      const { api, sockets, panelConfirmData } = makeHarness()
      const ws = makeWs(true)
      sockets.value.set('agent-1', ws)
      panelConfirmData.value.set('agent-1', { message: '确认' })
      api.handlePanelCancelConfirm({ agentId: 'agent-1' })
      expect(JSON.parse(ws.sent[0]).payload.confirmed).toBe(false)
    })
  })

  describe('submitCompletion', () => {
    it('waiting_multi 时直接发送 Ctrl+C', () => {
      const h = makeHarness()
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_multi' })
      h.showConfirm.mockImplementation((msg, onOk) => { onOk() })
      h.api.submitCompletion()
      expect(h.sendMessageToAgent).toHaveBeenCalledTimes(1)
      const [msg, agentId] = h.sendMessageToAgent.mock.calls[0]
      expect(msg.type).toBe('input_result')
      expect(msg.payload.text).toBe('__CTRL_C_PRESSED__')
      expect(agentId).toBe('agent-1')
    })
  })
})
