// usePanel 单元测试
// usePanel 不依赖 monaco，无需 mock monaco 模块。
// 注意：getter 注入的符号（xxxGetter）测试时需传 vi.fn(() => value) 形式；
//       ref 型 getter 内部以 xxxGetter().value 二次求值。
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { usePanel } from './usePanel.js'

// 构造测试 harness，注入全部依赖
function makeHarness(overrides = {}) {
  // 直传（ref 型）
  const showWorkspacePanel = ref(false)
  const sessionPanelRefs = new Map()
  const panels = ref([])
  const activePanelId = ref(null)
  const historyScrollListenerEl = ref(null)
  const historyScrollHandler = ref(null)
  const historyScrollDebounceTimer = ref(null)
  const panelOutputLists = ref(new Map())
  const outputList = ref(null)
  const inputMode = ref('multi')
  const inputText = ref('')
  const inputRequests = ref(new Map())
  const panelInputTexts = ref(new Map())
  const inputTip = ref('')
  const panelInputModes = ref(new Map())
  const panelInputTips = ref(new Map())
  const panelConfirmData = ref(new Map())
  const inputBuffers = ref(new Map())
  const username = ref('test-user')
  const windowWidth = ref(1024)
  const workspaceMainView = ref('file')
  const workspacePaneTree = ref(null)

  // 直传（函数型）
  const sortCompletionItems = vi.fn((x) => x)
  const getPanelAgent = vi.fn()
  const getPanelInputMode = vi.fn(() => 'single')
  const saveToHistory = vi.fn()
  const navigateHistory = vi.fn()
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/node/${nodeId}/${path}`)
  const fetchWithAuth = vi.fn()
  const findWorkspacePaneByView = vi.fn(() => null)
  const findWorkspacePaneBySessionPanelId = vi.fn(() => null)

  // getter 注入（定义在调用点之后的符号）
  const sendMessageToAgent = vi.fn()
  const loadHistoryMessages = vi.fn()
  const agentList = ref([])
  const currentAgentId = ref('agent-1')
  const agentStatuses = ref(new Map())
  const maybeStartTour = vi.fn()
  const chatName = ref('')
  const completionAgentId = ref(null)
  const completionSource = ref(null)
  const completionCursorPos = ref(-1)
  const completionHasAtSymbol = ref(false)
  const completionSearch = ref('')
  const showCompletions = ref(false)
  const completions = ref([])
  const completionSearchInput = ref(null)
  const selectedIndex = ref(-1)
  const streamingMessages = ref(new Map())
  const isLoadingHistory = ref(false)
  const hasMoreHistory = ref(true)
  const terminals = ref([])
  const terminalHosts = ref(new Map())
  const setTerminalRef = vi.fn()
  const appendOutput = vi.fn()
  const uploadImageToNode = vi.fn()
  const closeBufferPanelIfForAgent = vi.fn()
  const sendBufferedInput = vi.fn()
  const sendConfirmResult = vi.fn()
  const handlePanelConfirm = vi.fn()
  const handlePanelCancelConfirm = vi.fn()
  const isCursorAtFirstLine = vi.fn(() => true)
  const isCursorAtLastLine = vi.fn(() => true)

  const api = usePanel({
    showWorkspacePanel,
    sessionPanelRefs,
    panels,
    activePanelId,
    historyScrollListenerEl,
    historyScrollHandler,
    historyScrollDebounceTimer,
    panelOutputLists,
    outputList,
    inputMode,
    inputText,
    inputRequests,
    panelInputTexts,
    inputTip,
    panelInputModes,
    panelInputTips,
    panelConfirmData,
    inputBuffers,
    sortCompletionItems,
    getPanelAgent,
    getPanelInputMode,
    saveToHistory,
    navigateHistory,
    username,
    getGatewayAddress,
    buildNodeHttpUrl,
    fetchWithAuth,
    windowWidth,
    findWorkspacePaneByView,
    findWorkspacePaneBySessionPanelId,
    workspaceMainView,
    workspacePaneTree,
    sendMessageToAgentGetter: () => sendMessageToAgent,
    loadHistoryMessagesGetter: () => loadHistoryMessages,
    agentListGetter: () => agentList,
    currentAgentIdGetter: () => currentAgentId,
    agentStatusesGetter: () => agentStatuses,
    maybeStartTourGetter: () => maybeStartTour,
    chatNameGetter: () => chatName,
    completionAgentIdGetter: () => completionAgentId,
    completionSourceGetter: () => completionSource,
    completionCursorPosGetter: () => completionCursorPos,
    completionHasAtSymbolGetter: () => completionHasAtSymbol,
    completionSearchGetter: () => completionSearch,
    showCompletionsGetter: () => showCompletions,
    completionsGetter: () => completions,
    completionSearchInputGetter: () => completionSearchInput,
    selectedIndexGetter: () => selectedIndex,
    streamingMessagesGetter: () => streamingMessages,
    isLoadingHistoryGetter: () => isLoadingHistory,
    hasMoreHistoryGetter: () => hasMoreHistory,
    terminalsGetter: () => terminals,
    terminalHostsGetter: () => terminalHosts,
    setTerminalRefGetter: () => setTerminalRef,
    appendOutputGetter: () => appendOutput,
    uploadImageToNodeGetter: () => uploadImageToNode,
    closeBufferPanelIfForAgentGetter: () => closeBufferPanelIfForAgent,
    sendBufferedInputGetter: () => sendBufferedInput,
    sendConfirmResultGetter: () => sendConfirmResult,
    handlePanelConfirmGetter: () => handlePanelConfirm,
    handlePanelCancelConfirmGetter: () => handlePanelCancelConfirm,
    isCursorAtFirstLineGetter: () => isCursorAtFirstLine,
    isCursorAtLastLineGetter: () => isCursorAtLastLine,
    ...overrides,
  })

  return {
    api,
    showWorkspacePanel,
    sessionPanelRefs,
    panels,
    activePanelId,
    historyScrollListenerEl,
    historyScrollHandler,
    historyScrollDebounceTimer,
    panelOutputLists,
    outputList,
    inputMode,
    inputText,
    inputRequests,
    panelInputTexts,
    inputTip,
    panelInputModes,
    panelInputTips,
    panelConfirmData,
    inputBuffers,
    sortCompletionItems,
    getPanelAgent,
    getPanelInputMode,
    saveToHistory,
    navigateHistory,
    username,
    getGatewayAddress,
    buildNodeHttpUrl,
    fetchWithAuth,
    windowWidth,
    findWorkspacePaneByView,
    findWorkspacePaneBySessionPanelId,
    workspaceMainView,
    workspacePaneTree,
    sendMessageToAgent,
    loadHistoryMessages,
    agentList,
    currentAgentId,
    agentStatuses,
    maybeStartTour,
    chatName,
    completionAgentId,
    completionSource,
    completionCursorPos,
    completionHasAtSymbol,
    completionSearch,
    showCompletions,
    completions,
    completionSearchInput,
    selectedIndex,
    streamingMessages,
    isLoadingHistory,
    hasMoreHistory,
    terminals,
    terminalHosts,
    setTerminalRef,
    appendOutput,
    uploadImageToNode,
    closeBufferPanelIfForAgent,
    sendBufferedInput,
    sendConfirmResult,
    handlePanelConfirm,
    handlePanelCancelConfirm,
    isCursorAtFirstLine,
    isCursorAtLastLine,
  }
}

function makePanel(agentId = 'agent-1') {
  return { id: 'panel-1', agentId }
}

describe('usePanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('暴露预期接口（30 个符号）', () => {
    const { api } = makeHarness()
    expect(api).toHaveProperty('getPanelTerminals')
    expect(api).toHaveProperty('getPanelTerminalHosts')
    expect(api).toHaveProperty('getPanelInputDisabled')
    expect(api).toHaveProperty('getPanelWaitingMultiDisabled')
    expect(api).toHaveProperty('getPanelStreamingMessages')
    expect(api).toHaveProperty('getPanelHistoryState')
    expect(api).toHaveProperty('getPanelLayout')
    expect(api).toHaveProperty('getPanelHasBufferedInput')
    expect(api).toHaveProperty('sendFromPanel')
    expect(api).toHaveProperty('completeFromPanel')
    expect(api).toHaveProperty('openCompletionsFromPanel')
    expect(api).toHaveProperty('onLobbyOpenCompletions')
    expect(api).toHaveProperty('handlePanelInputChange')
    expect(api).toHaveProperty('handlePanelKeydown')
    expect(api).toHaveProperty('handlePanelPaste')
    expect(api).toHaveProperty('clearBufferFromPanel')
    expect(api).toHaveProperty('setupHistoryScrollListener')
    expect(api).toHaveProperty('setPanelOutputList')
    expect(api).toHaveProperty('setPanelTerminalRef')
    expect(api).toHaveProperty('workspaceHostsChat')
    expect(api).toHaveProperty('workspaceHostsTerminal')
    expect(api).toHaveProperty('workspaceHostsSession')
    expect(api).toHaveProperty('workspaceSessionPanelId')
    expect(api).toHaveProperty('workspaceHostedPanel')
    expect(api).toHaveProperty('workspaceSessionPanel')
    expect(api).toHaveProperty('visibleSessionAgentIds')
    expect(api).toHaveProperty('embeddedPanelCount')
    expect(api).toHaveProperty('hasNoPanel')
    expect(api).toHaveProperty('agentListLoaded')
    expect(api).toHaveProperty('panelGridStyle')
    expect(Object.keys(api)).toHaveLength(30)
  })

  describe('查询类', () => {
    it('getPanelTerminals 按 agentId 过滤终端', () => {
      const h = makeHarness()
      h.terminals.value = [
        { agentId: 'agent-1', executionId: 'e1' },
        { agentId: 'agent-2', executionId: 'e2' },
      ]
      const panel = makePanel('agent-1')
      expect(h.api.getPanelTerminals(panel)).toEqual([{ agentId: 'agent-1', executionId: 'e1' }])
    })

    it('getPanelTerminals 无 panel/agentId 返回空数组', () => {
      const h = makeHarness()
      expect(h.api.getPanelTerminals(null)).toEqual([])
      expect(h.api.getPanelTerminals({ id: 'p' })).toEqual([])
    })

    it('getPanelTerminalHosts 按 agentId 过滤终端宿主', () => {
      const h = makeHarness()
      const el1 = { tagName: 'DIV' }
      const el2 = { tagName: 'DIV' }
      h.terminalHosts.value = new Map([
        ['agent-1:e1', el1],
        ['agent-2:e2', el2],
      ])
      const panel = makePanel('agent-1')
      const hosts = h.api.getPanelTerminalHosts(panel)
      expect([...hosts.entries()]).toEqual([['agent-1:e1', el1]])
    })

    it('getPanelTerminalHosts 无 panel 返回空 Map', () => {
      const h = makeHarness()
      expect(h.api.getPanelTerminalHosts(null)).toEqual(new Map())
    })

    it('getPanelInputDisabled：agent 非 running 时禁用', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      expect(h.api.getPanelInputDisabled(makePanel())).toBe(false)
      h.getPanelAgent.mockReturnValue({ status: 'stopped' })
      expect(h.api.getPanelInputDisabled(makePanel())).toBe(true)
      h.getPanelAgent.mockReturnValue(null)
      expect(h.api.getPanelInputDisabled(makePanel())).toBe(true)
    })

    it('getPanelWaitingMultiDisabled：execution_status 为 waiting_multi 时不禁用', () => {
      const h = makeHarness()
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_multi' })
      expect(h.api.getPanelWaitingMultiDisabled(makePanel())).toBe(false)
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      expect(h.api.getPanelWaitingMultiDisabled(makePanel())).toBe(true)
    })

    it('getPanelStreamingMessages 按 agentId 过滤流式消息', () => {
      const h = makeHarness()
      const msg1 = { text: 'a' }
      const msg2 = { text: 'b' }
      h.streamingMessages.value = new Map([
        ['agent-1', msg1],
        ['agent-2', msg2],
      ])
      const msgs = h.api.getPanelStreamingMessages(makePanel())
      expect([...msgs.entries()]).toEqual([['agent-1', msg1]])
    })

    it('getPanelHistoryState 返回加载状态', () => {
      const h = makeHarness()
      h.isLoadingHistory.value = true
      h.hasMoreHistory.value = false
      expect(h.api.getPanelHistoryState(makePanel())).toEqual({ isLoading: true, hasMore: false })
    })

    it('getPanelLayout / panelGridStyle 随 embeddedPanelCount 变化', () => {
      const h = makeHarness()
      // showWorkspacePanel=false → count=0
      expect(h.api.getPanelLayout()).toEqual({})
      expect(h.api.panelGridStyle.value).toEqual({})
      h.showWorkspacePanel.value = true
      expect(h.api.getPanelLayout()).toEqual({ gridTemplateColumns: '1fr', gridTemplateRows: '1fr' })
      expect(h.api.panelGridStyle.value).toEqual({ gridTemplateColumns: '1fr', gridTemplateRows: '1fr' })
    })

    it('getPanelHasBufferedInput 判断缓冲区', () => {
      const h = makeHarness()
      expect(h.api.getPanelHasBufferedInput(makePanel())).toBe(false)
      h.inputBuffers.value.set('agent-1', 'text')
      expect(h.api.getPanelHasBufferedInput(makePanel())).toBe(true)
    })
  })

  describe('sendFromPanel', () => {
    it('单行模式 + running：直接发送 input_result', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('single')
      h.panelInputTexts.value.set('agent-1', 'hello')
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.api.sendFromPanel(makePanel())
      expect(h.sendMessageToAgent).toHaveBeenCalledTimes(1)
      const [message, agentId] = h.sendMessageToAgent.mock.calls[0]
      expect(agentId).toBe('agent-1')
      expect(message.type).toBe('input_result')
      expect(message.payload.text).toBe('hello')
      expect(message.payload.input_mode).toBe('single')
      // 发送后清空输入
      expect(h.panelInputTexts.value.get('agent-1')).toBe('')
      expect(h.inputText.value).toBe('')
      expect(h.saveToHistory).toHaveBeenCalledWith('hello')
    })

    it('agent 不存在或非 running：不发送', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue(null)
      h.api.sendFromPanel(makePanel())
      expect(h.sendMessageToAgent).not.toHaveBeenCalled()
    })

    it('waiting_confirm：y 发送确认结果', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('single')
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_confirm' })
      h.panelInputTexts.value.set('agent-1', 'y')
      h.api.sendFromPanel(makePanel())
      expect(h.sendConfirmResult).toHaveBeenCalledWith(true, 'agent-1')
      expect(h.sendMessageToAgent).not.toHaveBeenCalled()
    })

    it('waiting_confirm：n 视为取消', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('single')
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_confirm' })
      h.panelInputTexts.value.set('agent-1', 'n')
      h.api.sendFromPanel(makePanel())
      expect(h.sendConfirmResult).toHaveBeenCalledWith(false, 'agent-1')
    })

    it('multi 模式空输入且无缓冲：不发送', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('multi')
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.panelInputTexts.value.set('agent-1', '   ')
      h.api.sendFromPanel(makePanel())
      expect(h.sendMessageToAgent).not.toHaveBeenCalled()
      expect(h.sendBufferedInput).not.toHaveBeenCalled()
    })

    it('multi 模式非等待：保存到缓冲区并提示', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('multi')
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.panelInputTexts.value.set('agent-1', 'hello')
      h.api.sendFromPanel(makePanel())
      expect(h.sendMessageToAgent).not.toHaveBeenCalled()
      expect(h.inputBuffers.value.get('agent-1')).toBe('hello')
      expect(h.appendOutput).toHaveBeenCalledTimes(1)
      expect(h.saveToHistory).toHaveBeenCalledWith('hello')
    })

    it('waiting_multi：直接发送（即使 multi 模式）', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('multi')
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_multi' })
      h.panelInputTexts.value.set('agent-1', 'hello')
      h.api.sendFromPanel(makePanel())
      expect(h.sendMessageToAgent).toHaveBeenCalledTimes(1)
      expect(h.inputBuffers.value.has('agent-1')).toBe(false)
    })

    it('有缓冲 + waiting_multi：先发缓冲再拼输入', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('multi')
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_multi' })
      h.inputBuffers.value.set('agent-1', 'buffered')
      h.panelInputTexts.value.set('agent-1', 'extra')
      h.api.sendFromPanel(makePanel())
      expect(h.sendMessageToAgent).toHaveBeenCalledTimes(1)
      const [message] = h.sendMessageToAgent.mock.calls[0]
      expect(message.payload.text).toBe('buffered\nextra')
      expect(h.closeBufferPanelIfForAgent).toHaveBeenCalledWith('agent-1')
      expect(h.inputBuffers.value.has('agent-1')).toBe(false)
    })

    it('有缓冲 + 非等待：发送缓冲并追加输入', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('multi')
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.inputBuffers.value.set('agent-1', 'buffered')
      h.panelInputTexts.value.set('agent-1', 'extra')
      h.api.sendFromPanel(makePanel())
      expect(h.sendBufferedInput).toHaveBeenCalledWith('agent-1')
      expect(h.inputBuffers.value.get('agent-1')).toBe('buffered\nextra')
      expect(h.appendOutput).toHaveBeenCalledTimes(1)
    })
  })

  describe('completeFromPanel', () => {
    it('设置 waiting_confirm 状态并写入 panelConfirmData', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.sessionPanelRefs.set('panel-1', { focusInput: vi.fn() })
      h.api.completeFromPanel(makePanel())
      expect(h.agentStatuses.value.get('agent-1').execution_status).toBe('waiting_confirm')
      expect(h.panelConfirmData.value.has('agent-1')).toBe(true)
      const data = h.panelConfirmData.value.get('agent-1')
      expect(data.defaultConfirm).toBe(true)
      expect(data.message).toContain('完成信号')
      expect(h.inputMode.value).toBe('single')
      expect(h.panelInputModes.value.get('agent-1')).toBe('single')
      expect(h.sessionPanelRefs.get('panel-1').focusInput).toHaveBeenCalled()
    })

    it('onConfirm：waiting_multi 时发送 Ctrl+C 信号', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_multi' })
      h.api.completeFromPanel(makePanel())
      const data = h.panelConfirmData.value.get('agent-1')
      data.onConfirm()
      expect(h.sendMessageToAgent).toHaveBeenCalledTimes(1)
      const [message, agentId] = h.sendMessageToAgent.mock.calls[0]
      expect(agentId).toBe('agent-1')
      expect(message.payload.text).toBe('__CTRL_C_PRESSED__')
      // 状态恢复为原始状态
      expect(h.agentStatuses.value.get('agent-1').execution_status).toBe('waiting_multi')
      expect(h.inputMode.value).toBe('multi')
    })

    it('onConfirm：非 waiting_multi 时保存完成信号到缓冲区', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.api.completeFromPanel(makePanel())
      const data = h.panelConfirmData.value.get('agent-1')
      data.onConfirm()
      expect(h.sendMessageToAgent).not.toHaveBeenCalled()
      expect(h.inputBuffers.value.get('agent-1')).toBe('__CTRL_C_PRESSED__')
      expect(h.appendOutput).toHaveBeenCalledTimes(1)
    })

    it('onCancel：恢复状态与输入模式', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.api.completeFromPanel(makePanel())
      const data = h.panelConfirmData.value.get('agent-1')
      data.onCancel()
      expect(h.agentStatuses.value.get('agent-1').execution_status).toBe('running')
      expect(h.inputMode.value).toBe('multi')
      expect(h.panelInputModes.value.get('agent-1')).toBe('multi')
    })
  })

  describe('补全', () => {
    it('openCompletionsFromPanel：设置补全状态并拉取列表', async () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ agent_id: 'agent-1', node_id: 'node-1' })
      h.fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: ['item1', 'item2'] }),
      })
      await h.api.openCompletionsFromPanel(makePanel())
      expect(h.completionAgentId.value).toBe('agent-1')
      expect(h.completionSource.value).toBe('panel')
      expect(h.completionHasAtSymbol.value).toBe(false)
      expect(h.completions.value).toEqual(['item1', 'item2'])
      expect(h.showCompletions.value).toBe(true)
      expect(h.fetchWithAuth).toHaveBeenCalledTimes(1)
      const url = h.fetchWithAuth.mock.calls[0][0]
      expect(url).toContain('/completions/agent-1')
    })

    it('openCompletionsFromPanel：agent 不存在时 alert 并返回', async () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue(null)
      const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
      await h.api.openCompletionsFromPanel(makePanel())
      expect(alertSpy).toHaveBeenCalled()
      expect(h.fetchWithAuth).not.toHaveBeenCalled()
      alertSpy.mockRestore()
    })

    it('openCompletionsFromPanel：响应失败时 alert', async () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ agent_id: 'agent-1' })
      h.fetchWithAuth.mockResolvedValue({
        ok: false,
        json: async () => ({ error: { message: 'boom' } }),
      })
      const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
      await h.api.openCompletionsFromPanel(makePanel())
      expect(alertSpy).toHaveBeenCalled()
      alertSpy.mockRestore()
    })

    it('onLobbyOpenCompletions：从大厅打开补全', async () => {
      const h = makeHarness()
      h.agentList.value = [{ agent_id: 'agent-1', node_id: 'node-1' }]
      h.fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: ['a'] }),
      })
      await h.api.onLobbyOpenCompletions('agent-1', 5)
      expect(h.completionAgentId.value).toBe('agent-1')
      expect(h.completionSource.value).toBe('lobby')
      expect(h.completionCursorPos.value).toBe(5)
      expect(h.completionHasAtSymbol.value).toBe(true)
      expect(h.completions.value).toEqual(['a'])
    })

    it('onLobbyOpenCompletions：agent 不在列表时返回', async () => {
      const h = makeHarness()
      h.agentList.value = []
      await h.api.onLobbyOpenCompletions('agent-1', 0)
      expect(h.fetchWithAuth).not.toHaveBeenCalled()
    })
  })

  describe('handlePanelInputChange / handlePanelKeydown', () => {
    it('handlePanelInputChange 更新输入文本并同步全局', () => {
      const h = makeHarness()
      const event = { target: { value: 'abc', selectionStart: 3 } }
      h.api.handlePanelInputChange(makePanel(), event)
      expect(h.panelInputTexts.value.get('agent-1')).toBe('abc')
      expect(h.inputText.value).toBe('abc')
    })

    it('handlePanelInputChange 输入 @ 时打开补全', async () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ agent_id: 'agent-1' })
      h.fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: [] }),
      })
      const event = { target: { value: 'hello @', selectionStart: 7 } }
      h.api.handlePanelInputChange(makePanel(), event)
      expect(h.completionCursorPos.value).toBe(6)
      expect(h.completionHasAtSymbol.value).toBe(false)
      await new Promise((resolve) => setTimeout(resolve, 10))
      expect(h.completionAgentId.value).toBe('agent-1')
    })

    it('handlePanelKeydown：@ 键打开补全', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ agent_id: 'agent-1' })
      h.fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: [] }),
      })
      const event = { key: '@', preventDefault: vi.fn(), target: { selectionStart: 2 } }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(h.completionCursorPos.value).toBe(2)
      expect(h.completionHasAtSymbol.value).toBe(true)
    })

    it('handlePanelKeydown：waiting_confirm 时 y 走 panelConfirmData.onConfirm', () => {
      const h = makeHarness()
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_confirm' })
      h.panelConfirmData.value.set('agent-1', { onConfirm: vi.fn(), onCancel: vi.fn() })
      const event = { key: 'y', preventDefault: vi.fn() }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(h.handlePanelConfirm).toHaveBeenCalledWith(makePanel())
    })

    it('handlePanelKeydown：waiting_confirm 时 n 走 panelConfirmData.onCancel', () => {
      const h = makeHarness()
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_confirm' })
      h.panelConfirmData.value.set('agent-1', { onConfirm: vi.fn(), onCancel: vi.fn() })
      const event = { key: 'n', preventDefault: vi.fn() }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(h.handlePanelCancelConfirm).toHaveBeenCalledWith(makePanel())
    })

    it('handlePanelKeydown：waiting_confirm 无 panelConfirmData 时直接 sendConfirmResult', () => {
      const h = makeHarness()
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_confirm' })
      const event = { key: 'y', preventDefault: vi.fn() }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(h.sendConfirmResult).toHaveBeenCalledWith(true, 'agent-1')
    })

    it('handlePanelKeydown：单行模式 Enter 提交', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('single')
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.panelInputTexts.value.set('agent-1', 'hello')
      const event = { key: 'Enter', ctrlKey: false, preventDefault: vi.fn() }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(h.sendMessageToAgent).toHaveBeenCalledTimes(1)
    })

    it('handlePanelKeydown：Ctrl+Enter 提交', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('multi')
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.panelInputTexts.value.set('agent-1', 'hello')
      const event = { key: 'Enter', ctrlKey: true, preventDefault: vi.fn() }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      // multi 模式 + 非等待：保存到缓冲区而非直接发送
      expect(h.inputBuffers.value.get('agent-1')).toBe('hello')
      expect(h.sendMessageToAgent).not.toHaveBeenCalled()
    })

    it('handlePanelKeydown：Alt+T 触发终端命令', () => {
      const h = makeHarness()
      h.getPanelAgent.mockReturnValue({ status: 'running' })
      h.getPanelInputMode.mockReturnValue('single')
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      const event = { altKey: true, code: 'KeyT', key: 't', preventDefault: vi.fn(), stopPropagation: vi.fn() }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(event.stopPropagation).toHaveBeenCalled()
      expect(h.sendMessageToAgent).toHaveBeenCalledTimes(1)
      const [message] = h.sendMessageToAgent.mock.calls[0]
      expect(message.payload.text).toBe('__ALT_T_PRESSED__')
    })

    it('handlePanelKeydown：waiting_multi + Ctrl+C 空输入触发 completeFromPanel', () => {
      const h = makeHarness()
      h.agentStatuses.value.set('agent-1', { execution_status: 'waiting_multi' })
      h.panelInputTexts.value.set('agent-1', '')
      const event = { ctrlKey: true, key: 'c', preventDefault: vi.fn() }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(h.agentStatuses.value.get('agent-1').execution_status).toBe('waiting_confirm')
    })

    it('handlePanelKeydown：running + Ctrl+C 空输入发送 manual_interrupt', () => {
      const h = makeHarness()
      h.agentStatuses.value.set('agent-1', { execution_status: 'running' })
      h.panelInputTexts.value.set('agent-1', '')
      const event = { ctrlKey: true, key: 'c', preventDefault: vi.fn() }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      const [message, agentId] = h.sendMessageToAgent.mock.calls[0]
      expect(agentId).toBe('agent-1')
      expect(message.type).toBe('manual_interrupt')
    })

    it('handlePanelKeydown：ArrowUp 在第一行时触发历史导航', () => {
      const h = makeHarness()
      h.isCursorAtFirstLine.mockReturnValue(true)
      const event = { key: 'ArrowUp', ctrlKey: false, altKey: false, metaKey: false, preventDefault: vi.fn(), target: {} }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(h.navigateHistory).toHaveBeenCalledWith('up', 'agent-1')
    })

    it('handlePanelKeydown：ArrowDown 在最后一行时触发历史导航', () => {
      const h = makeHarness()
      h.isCursorAtLastLine.mockReturnValue(true)
      const event = { key: 'ArrowDown', ctrlKey: false, altKey: false, metaKey: false, preventDefault: vi.fn(), target: {} }
      h.api.handlePanelKeydown(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(h.navigateHistory).toHaveBeenCalledWith('down', 'agent-1')
    })
  })

  describe('handlePanelPaste / clearBufferFromPanel', () => {
    it('handlePanelPaste：粘贴图片触发 uploadImageToNode', () => {
      const h = makeHarness()
      const file = new File(['x'], 'x.png', { type: 'image/png' })
      const item = { type: 'image/png', getAsFile: vi.fn(() => file) }
      const event = { clipboardData: { items: [item] }, preventDefault: vi.fn() }
      h.api.handlePanelPaste(makePanel(), event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(h.uploadImageToNode).toHaveBeenCalledWith(file, 'agent-1')
    })

    it('handlePanelPaste：无图片不处理', () => {
      const h = makeHarness()
      const item = { type: 'text/plain', getAsFile: vi.fn() }
      const event = { clipboardData: { items: [item] }, preventDefault: vi.fn() }
      h.api.handlePanelPaste(makePanel(), event)
      expect(event.preventDefault).not.toHaveBeenCalled()
      expect(h.uploadImageToNode).not.toHaveBeenCalled()
    })

    it('clearBufferFromPanel：清空缓冲区并提示', () => {
      const h = makeHarness()
      h.inputBuffers.value.set('agent-1', 'text')
      h.api.clearBufferFromPanel(makePanel())
      expect(h.inputBuffers.value.has('agent-1')).toBe(false)
      expect(h.closeBufferPanelIfForAgent).toHaveBeenCalledWith('agent-1')
      expect(h.appendOutput).toHaveBeenCalledTimes(1)
    })
  })

  describe('setupHistoryScrollListener / setPanelOutputList / setPanelTerminalRef', () => {
    it('setupHistoryScrollListener：绑定滚动监听并触发加载历史', () => {
      const h = makeHarness()
      const el = {
        scrollTop: 0,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }
      h.api.setupHistoryScrollListener(el)
      expect(h.historyScrollListenerEl.value).toStrictEqual(el)
      expect(el.addEventListener).toHaveBeenCalledWith('scroll', expect.any(Function))
      // 触发滚动回调 → 防抖后加载历史
      h.isLoadingHistory.value = false
      h.hasMoreHistory.value = true
      el.addEventListener.mock.calls[0][1]()
      // 500ms 防抖
      vi.useFakeTimers()
      el.addEventListener.mock.calls[0][1]()
      vi.advanceTimersByTime(600)
      expect(h.loadHistoryMessages).toHaveBeenCalledWith(true)
      vi.useRealTimers()
    })

    it('setupHistoryScrollListener：滚动未到顶部不加载', () => {
      const h = makeHarness()
      const el = {
        scrollTop: 100,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }
      h.api.setupHistoryScrollListener(el)
      vi.useFakeTimers()
      el.addEventListener.mock.calls[0][1]()
      vi.advanceTimersByTime(600)
      expect(h.loadHistoryMessages).not.toHaveBeenCalled()
      vi.useRealTimers()
    })

    it('setupHistoryScrollListener：el 为 null 时清理', () => {
      const h = makeHarness()
      const oldEl = { removeEventListener: vi.fn() }
      h.historyScrollListenerEl.value = oldEl
      h.historyScrollHandler.value = vi.fn()
      h.api.setupHistoryScrollListener(null)
      expect(oldEl.removeEventListener).toHaveBeenCalled()
      expect(h.historyScrollListenerEl.value).toBe(null)
      expect(h.historyScrollHandler.value).toBe(null)
    })

    it('setPanelOutputList：绑定输出列表并设置当前 agent 的输出', () => {
      const h = makeHarness()
      const el = { scrollTop: 0, addEventListener: vi.fn(), removeEventListener: vi.fn() }
      h.api.setPanelOutputList(makePanel(), el)
      expect(h.panelOutputLists.value.get('panel-1')).toStrictEqual(el)
      expect(h.outputList.value).toStrictEqual(el)
      // 当前 agent 会补绑滚动监听
      expect(el.addEventListener).toHaveBeenCalledWith('scroll', expect.any(Function))
    })

    it('setPanelOutputList：非当前 agent 不设置全局 outputList', () => {
      const h = makeHarness()
      h.currentAgentId.value = 'agent-2'
      const el = { scrollTop: 0, addEventListener: vi.fn(), removeEventListener: vi.fn() }
      h.api.setPanelOutputList(makePanel(), el)
      expect(h.panelOutputLists.value.get('panel-1')).toStrictEqual(el)
      expect(h.outputList.value).toBe(null)
    })

    it('setPanelTerminalRef：委托 setTerminalRef', () => {
      const h = makeHarness()
      const el = {}
      h.api.setPanelTerminalRef(makePanel(), 'exec-1', el)
      expect(h.setTerminalRef).toHaveBeenCalledWith('exec-1', el, 'agent-1')
    })

    it('setPanelTerminalRef：无 executionId 不委托', () => {
      const h = makeHarness()
      h.api.setPanelTerminalRef(makePanel(), null, {})
      expect(h.setTerminalRef).not.toHaveBeenCalled()
    })
  })

  describe('工作区承载状态', () => {
    it('workspaceHostsChat / workspaceHostsTerminal：pane 树承载 chat/terminal', () => {
      const h = makeHarness()
      h.showWorkspacePanel.value = true
      // 用响应式 ref 驱动 mock，使 computed 依赖变化可触发重算
      const hostedPaneView = ref(null)
      h.findWorkspacePaneByView.mockImplementation((view) => hostedPaneView.value === view ? {} : null)
      expect(h.api.workspaceHostsChat.value).toBe(false)
      expect(h.api.workspaceHostsTerminal.value).toBe(false)
      hostedPaneView.value = 'chat'
      expect(h.api.workspaceHostsChat.value).toBe(true)
      hostedPaneView.value = 'terminal'
      expect(h.api.workspaceHostsTerminal.value).toBe(true)
    })

    it('workspaceHostsSession：主视图为 session 时承载', () => {
      const h = makeHarness()
      h.showWorkspacePanel.value = true
      h.workspaceMainView.value = 'session'
      expect(h.api.workspaceHostsSession.value).toBe(true)
      h.workspaceMainView.value = 'file'
      expect(h.api.workspaceHostsSession.value).toBe(false)
    })

    it('workspaceSessionPanelId 可读写', () => {
      const h = makeHarness()
      h.api.workspaceSessionPanelId.value = 'panel-1'
      expect(h.api.workspaceSessionPanelId.value).toBe('panel-1')
    })

    it('workspaceHostedPanel：pane 承载时返回对应 panel', () => {
      const h = makeHarness()
      h.showWorkspacePanel.value = true
      h.api.workspaceSessionPanelId.value = 'panel-1'
      h.panels.value = [{ id: 'panel-1', agentId: 'agent-1' }]
      // 用响应式 ref 驱动 mock，使 computed 依赖变化可触发重算
      const hasHostingPane = ref(true)
      h.findWorkspacePaneBySessionPanelId.mockImplementation(() => hasHostingPane.value ? { id: 'pane-1' } : null)
      expect(h.api.workspaceHostedPanel.value).toEqual({ id: 'panel-1', agentId: 'agent-1' })
      // 无 pane 承载时返回 null（回到网格）
      hasHostingPane.value = false
      expect(h.api.workspaceHostedPanel.value).toBe(null)
    })

    it('visibleSessionAgentIds：遍历 pane 树收集会话 agent', () => {
      const h = makeHarness()
      h.panels.value = [
        { id: 'panel-1', agentId: 'agent-1' },
        { id: 'panel-2', agentId: 'agent-2' },
      ]
      h.workspacePaneTree.value = {
        type: 'branch',
        children: [
          { type: 'leaf', view: 'session', sessionPanelId: 'panel-1' },
          { type: 'leaf', view: 'file' },
        ],
      }
      const ids = h.api.visibleSessionAgentIds.value
      expect(ids.has('agent-1')).toBe(true)
      expect(ids.has('agent-2')).toBe(false)
    })

    it('embeddedPanelCount / hasNoPanel：随 showWorkspacePanel 变化', () => {
      const h = makeHarness()
      expect(h.api.embeddedPanelCount.value).toBe(0)
      expect(h.api.hasNoPanel.value).toBe(true)
      h.showWorkspacePanel.value = true
      expect(h.api.embeddedPanelCount.value).toBe(1)
      expect(h.api.hasNoPanel.value).toBe(false)
    })

    it('agentListLoaded 初始为 false', () => {
      const h = makeHarness()
      expect(h.api.agentListLoaded.value).toBe(false)
    })
  })
})
