// useAgents 单元测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useAgents } from './useAgents.js'
// 刷新所有微任务（async 函数多层 await 时用）
async function flushPromises() {
  for (let i = 0; i < 20; i++) {
    await Promise.resolve()
  }
}
// 构造 useAgents 依赖注入 harness
function makeHarness(overrides = {}) {
  // —— 早期 ref（App.vue 顶层创建）——
  const agentList = ref([])
  const currentAgentId = ref(null)
  const agentStatuses = ref(new Map())
  const isStoppedAgent = vi.fn((agent) => agent?.status === 'stopped')
  const currentAgent = ref(null)
  const agentGroups = ref([])
  const selectedAgents = ref(new Set())
  const isBatchMode = ref(false)
  const inputText = ref('')
  const inputMode = ref('multi')
  const inputRequests = ref(new Map())
  const inputTip = ref('')
  const panelInputTexts = ref(new Map())
  const panelInputModes = ref(new Map())
  const panelInputTips = ref(new Map())
  const panelConfirmData = ref(new Map())
  const pendingInputAgentId = ref(null)
  const pendingConfirmAgentId = ref(null)
  const inputBuffers = ref(new Map())
  const allOutputs = ref(new Map())
  const outputs = ref([])
  const outputList = ref(null)
  const panelOutputLists = new Map()
  const panels = ref([])
  const sessionPanelRefs = ref(new Map())
  const showToast = vi.fn()
  const showConfirm = vi.fn()
  const showSettingsModal = ref(false)
  const showWorkspacePanel = ref(false)
  const activeWorkspaceSession = ref(null)
  const hasNoPanel = ref(true)
  const isAutoFocusSuppressed = vi.fn(() => false)
  const isAnyModalOpen = vi.fn(() => false)
  const socket = ref(null)
  const sockets = ref(new Map())
  const auth = ref({ userInfo: null })
  const username = ref('testuser')
  const getHttpProtocol = vi.fn(() => 'http')
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/nodes/${nodeId}/${path}`)
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: 8080 }))
  const fetchWithAuth = vi.fn()
  const escapeHtml = vi.fn((text) => String(text).replace(/</g, '&lt;').replace(/>/g, '&gt;'))
  const historyStorage = {
    getHistoryForAgent: vi.fn(() => []),
    clearHistoryForAgent: vi.fn(),
    pruneHistory: vi.fn(),
  }
  const loadHistoryMessages = vi.fn()
  const sendMessageToAgent = vi.fn()
  const setupHistoryScrollListener = vi.fn()
  const openAgentInPanel = vi.fn()
  const closePanel = vi.fn()
  const closeAgentInPanel = vi.fn()
  const closeOpenDirDialog = vi.fn()
  const confirmOpenDir = vi.fn()
  const restoreWorkspacePaneContents = vi.fn()
  const saveRecentWorkDir = vi.fn()
  const loadRecentWorkDirs = vi.fn()
  const filteredDirList = ref([])
  const sortCompletionItems = vi.fn((items) => items)
  const recordCompletionSelection = vi.fn()
  const switchGeneration = ref(0)
  const windowWidth = ref(1024)
  const agentListLoaded = ref(false)
  const setModalAutoFocusSuppressUntil = vi.fn()
  const MODAL_AUTOFOCUS_SUPPRESS_MS = 600
  const hasMoreHistory = ref(true)
  const historyOffset = ref(0)
  const showCompletions = ref(false)
  const completionCursorPos = ref(-1)
  const completionHasAtSymbol = ref(false)
  const completionAgentId = ref(null)
  const completionSource = ref('panel')
  const petLobbyRef = ref(null)
  const completions = ref([])
  const completionSearch = ref('')
  const fileCompletions = ref([])
  const completionSearchInput = ref(null)
  const completionsModalRef = ref(null)
  const selectedIndex = ref(-1)
  const showCreateAgentModal = ref(false)
  const showQuickCreateAgentModal = ref(false)
  const quickCreateAgentLoading = ref(false)
  const quickCreateAgentError = ref('')
  const showRenameAgentModal = ref(false)
  const renamingAgent = ref(null)
  const renameAgentName = ref('')
  const showDirDialog = ref(false)
  const currentDirPath = ref('')
  const dirList = ref([])
  const selectedDir = ref(null)
  const dirSearchText = ref('')
  const dirSearchInput = ref(null)
  const selectedDirIndex = ref(-1)
  const dirDialogRef = ref(null)
  const saveAgentGroups = vi.fn()
  const renameInput = ref(null)
  const openDirNodeId = ref('')
  const openDirPath = ref('')
  const openDirDialogRef = ref(null)
  const newAgentType = ref('agent')
  const newAgentDir = ref('~')
  const newAgentName = ref('')
  const modelGroups = ref([])
  const newAgentModelGroup = ref('default')
  const newCodeAgentWorktree = ref(false)
  const newAgentQuickMode = ref(false)
  const newAgentRestoreSession = ref(false)
  const newAgentNoInteractionMode = ref(false)
  const newAgentTaskDescription = ref('')
  const newAgentCreateError = ref('')
  const newAgentProxyNode = ref('')
  const newAgentAccessAclRead = ref([])
  const newAgentAccessAclInteract = ref([])
  const availableUserOptions = ref([])
  const availableNodeOptions = ref([])
  const userAccessibleNodes = ref([])
  const userPermissions = ref({ allowed: [], denied: [] })
  const getNodeDisplayName = vi.fn((id) => id)
  const newAgentNodeId = ref('master')
  const filteredNodeOptionsForCreateAgent = ref([])
  const getDefaultCreateAgentNodeId = vi.fn(() => 'master')
  const generateAgentName = vi.fn((type) => `agent-${type}-${Date.now()}`)
  const skipNameWatch = ref(false)
  const rulesLoading = ref(false)
  const showRulesModal = ref(false)
  const rulesContent = ref([])
  const rulesLoadedContent = ref('')
  const selectedTerminalNodeId = ref('')
  const chatName = ref('')
  const saveToHistory = vi.fn()
  const lobbyHistoryIndex = new Map()
  const lobbyHistoryTemp = new Map()
  const maybeStartTour = vi.fn()
  const fileTreeState = ref(new Map())
  const fileTreeExpanded = ref(new Map())
  const fileTreeLoading = ref(new Map())
  // —— getter 注入（晚期求值）——
  const orchestrateAgents = ref([])
  const orchestrateActiveIndex = ref(0)
  const orchestrateNodeId = ref('master')
  const terminals = ref([])
  const terminalHosts = ref(new Map())
  const disposeExecutionTerminal = vi.fn()
  const connectToAgent = vi.fn()
  const autoConnectToOnlineAgents = vi.fn()
  const renderMessageHtml = vi.fn((item) => `<p>${item.text}</p>`)
  const appendOutput = vi.fn()
  const sendInputDirectly = vi.fn()
  const sendBufferedInput = vi.fn()
  const sendConfirmResult = vi.fn()
  const restoreWaitingConfirmUI = vi.fn()
  const pushOverlayState = vi.fn()
  const api = useAgents({
    agentList,
    currentAgentId,
    agentStatuses,
    isStoppedAgent,
    currentAgent,
    agentGroups,
    selectedAgents,
    isBatchMode,
    inputText,
    inputMode,
    inputRequests,
    inputTip,
    panelInputTexts,
    panelInputModes,
    panelInputTips,
    panelConfirmData,
    pendingInputAgentId,
    pendingConfirmAgentId,
    inputBuffers,
    allOutputs,
    outputs,
    outputList,
    panelOutputLists,
    panels,
    sessionPanelRefs,
    showToast,
    showConfirm,
    showSettingsModal,
    showWorkspacePanel,
    activeWorkspaceSession,
    hasNoPanel,
    isAutoFocusSuppressed,
    isAnyModalOpen,
    socket,
    sockets,
    auth,
    username,
    getHttpProtocol,
    buildNodeHttpUrl,
    getGatewayAddress,
    fetchWithAuth,
    escapeHtml,
    historyStorage,
    loadHistoryMessages,
    sendMessageToAgent,
    setupHistoryScrollListener,
    openAgentInPanel,
    closePanel,
    closeAgentInPanel,
    closeOpenDirDialog,
    confirmOpenDir,
    restoreWorkspacePaneContents,
    saveRecentWorkDir,
    loadRecentWorkDirs,
    filteredDirList,
    sortCompletionItems,
    recordCompletionSelection,
    switchGeneration,
    windowWidth,
    agentListLoaded,
    setModalAutoFocusSuppressUntil,
    MODAL_AUTOFOCUS_SUPPRESS_MS,
    hasMoreHistory,
    historyOffset,
    showCompletions,
    completionCursorPos,
    completionHasAtSymbol,
    completionAgentId,
    completionSource,
    petLobbyRef,
    completions,
    completionSearch,
    fileCompletions,
    completionSearchInput,
    completionsModalRef,
    selectedIndex,
    showCreateAgentModal,
    showQuickCreateAgentModal,
    quickCreateAgentLoading,
    quickCreateAgentError,
    showRenameAgentModal,
    renamingAgent,
    renameAgentName,
    showDirDialog,
    currentDirPath,
    dirList,
    selectedDir,
    dirSearchText,
    dirSearchInput,
    selectedDirIndex,
    dirDialogRef,
    saveAgentGroups,
    renameInput,
    openDirNodeId,
    openDirPath,
    openDirDialogRef,
    newAgentType,
    newAgentDir,
    newAgentName,
    modelGroups,
    newAgentModelGroup,
    newCodeAgentWorktree,
    newAgentQuickMode,
    newAgentRestoreSession,
    newAgentNoInteractionMode,
    newAgentTaskDescription,
    newAgentCreateError,
    newAgentProxyNode,
    newAgentAccessAclRead,
    newAgentAccessAclInteract,
    availableUserOptions,
    availableNodeOptions,
    userAccessibleNodes,
    userPermissions,
    getNodeDisplayName,
    newAgentNodeId,
    filteredNodeOptionsForCreateAgent,
    getDefaultCreateAgentNodeId,
    generateAgentName,
    skipNameWatch,
    rulesLoading,
    showRulesModal,
    rulesContent,
    rulesLoadedContent,
    selectedTerminalNodeId,
    chatName,
    saveToHistory,
    lobbyHistoryIndex,
    lobbyHistoryTemp,
    maybeStartTour,
    fileTreeState,
    fileTreeExpanded,
    fileTreeLoading,
    orchestrateAgents: () => orchestrateAgents,
    orchestrateActiveIndex: () => orchestrateActiveIndex,
    orchestrateNodeId: () => orchestrateNodeId,
    terminals: () => terminals,
    terminalHosts: () => terminalHosts,
    disposeExecutionTerminal: () => disposeExecutionTerminal,
    connectToAgent: () => connectToAgent,
    autoConnectToOnlineAgents: () => autoConnectToOnlineAgents,
    renderMessageHtml: () => renderMessageHtml,
    appendOutput: () => appendOutput,
    sendInputDirectly: () => sendInputDirectly,
    sendBufferedInput: () => sendBufferedInput,
    sendConfirmResult: () => sendConfirmResult,
    restoreWaitingConfirmUI: () => restoreWaitingConfirmUI,
    pushOverlayState: () => pushOverlayState,
    ...overrides,
  })
  return {
    api,
    agentList,
    currentAgentId,
    agentStatuses,
    isStoppedAgent,
    currentAgent,
    agentGroups,
    selectedAgents,
    isBatchMode,
    inputText,
    inputMode,
    inputRequests,
    inputTip,
    panelInputTexts,
    panelInputModes,
    panelInputTips,
    panelConfirmData,
    pendingInputAgentId,
    pendingConfirmAgentId,
    inputBuffers,
    allOutputs,
    outputs,
    outputList,
    panelOutputLists,
    panels,
    sessionPanelRefs,
    showToast,
    showConfirm,
    showSettingsModal,
    showWorkspacePanel,
    activeWorkspaceSession,
    hasNoPanel,
    isAutoFocusSuppressed,
    isAnyModalOpen,
    socket,
    sockets,
    auth,
    username,
    getHttpProtocol,
    buildNodeHttpUrl,
    getGatewayAddress,
    fetchWithAuth,
    escapeHtml,
    historyStorage,
    loadHistoryMessages,
    sendMessageToAgent,
    setupHistoryScrollListener,
    openAgentInPanel,
    closePanel,
    closeAgentInPanel,
    closeOpenDirDialog,
    confirmOpenDir,
    restoreWorkspacePaneContents,
    saveRecentWorkDir,
    loadRecentWorkDirs,
    filteredDirList,
    sortCompletionItems,
    recordCompletionSelection,
    switchGeneration,
    windowWidth,
    agentListLoaded,
    setModalAutoFocusSuppressUntil,
    MODAL_AUTOFOCUS_SUPPRESS_MS,
    hasMoreHistory,
    historyOffset,
    showCompletions,
    completionCursorPos,
    completionHasAtSymbol,
    completionAgentId,
    completionSource,
    petLobbyRef,
    completions,
    completionSearch,
    fileCompletions,
    completionSearchInput,
    completionsModalRef,
    selectedIndex,
    showCreateAgentModal,
    showQuickCreateAgentModal,
    quickCreateAgentLoading,
    quickCreateAgentError,
    showRenameAgentModal,
    renamingAgent,
    renameAgentName,
    showDirDialog,
    currentDirPath,
    dirList,
    selectedDir,
    dirSearchText,
    dirSearchInput,
    selectedDirIndex,
    dirDialogRef,
    saveAgentGroups,
    renameInput,
    openDirNodeId,
    openDirPath,
    openDirDialogRef,
    newAgentType,
    newAgentDir,
    newAgentName,
    modelGroups,
    newAgentModelGroup,
    newCodeAgentWorktree,
    newAgentQuickMode,
    newAgentRestoreSession,
    newAgentNoInteractionMode,
    newAgentTaskDescription,
    newAgentCreateError,
    newAgentProxyNode,
    newAgentAccessAclRead,
    newAgentAccessAclInteract,
    availableUserOptions,
    availableNodeOptions,
    userAccessibleNodes,
    userPermissions,
    getNodeDisplayName,
    newAgentNodeId,
    filteredNodeOptionsForCreateAgent,
    getDefaultCreateAgentNodeId,
    generateAgentName,
    skipNameWatch,
    rulesLoading,
    showRulesModal,
    rulesContent,
    rulesLoadedContent,
    selectedTerminalNodeId,
    chatName,
    saveToHistory,
    lobbyHistoryIndex,
    lobbyHistoryTemp,
    maybeStartTour,
    fileTreeState,
    fileTreeExpanded,
    fileTreeLoading,
    orchestrateAgents,
    orchestrateActiveIndex,
    orchestrateNodeId,
    terminals,
    terminalHosts,
    disposeExecutionTerminal,
    connectToAgent,
    autoConnectToOnlineAgents,
    renderMessageHtml,
    appendOutput,
    sendInputDirectly,
    sendBufferedInput,
    sendConfirmResult,
    restoreWaitingConfirmUI,
    pushOverlayState,
  }
}
describe('useAgents', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })
  it('初始状态：域内 ref 默认值正确', () => {
    const { api } = makeHarness()
    expect(api.dirDialogContext.value).toBe('create-agent')
    expect(api.showToolsModal.value).toBe(false)
    expect(api.toolsContent.value).toEqual({ all_tools: [], allowed_tools: null })
    expect(api.toolsLoading.value).toBe(false)
    expect(api.showEditAccessModal.value).toBe(false)
    expect(api.editingAccessAgent.value).toBe(null)
    expect(api.editAccessRead.value).toEqual([])
    expect(api.editAccessInteract.value).toEqual([])
  })
  it('getStatusText：停止/无数据/等待状态组合显示', () => {
    const { api, agentStatuses } = makeHarness()
    expect(api.getStatusText({ agent_id: 'a1', status: 'stopped' })).toBe('已完成')
    expect(api.getStatusText({ agent_id: 'a1', status: 'running' })).toBe('运行中')
    agentStatuses.value.set('a1', { execution_status: 'waiting_multi' })
    expect(api.getStatusText({ agent_id: 'a1', status: 'running' })).toBe('运行中（等待多行输入）')
    agentStatuses.value.set('a1', { execution_status: 'waiting_single' })
    expect(api.getStatusText({ agent_id: 'a1', status: 'running' })).toBe('运行中（等待确认）')
    agentStatuses.value.set('a1', { execution_status: 'waiting_confirm' })
    expect(api.getStatusText({ agent_id: 'a1', status: 'running' })).toBe('运行中（等待确认）')
  })
  it('getStatusClass：停止/等待/默认状态', () => {
    const { api, agentStatuses } = makeHarness()
    expect(api.getStatusClass({ agent_id: 'a1', status: 'stopped' })).toBe('stopped')
    expect(api.getStatusClass({ agent_id: 'a1', status: 'running' })).toBe('running')
    agentStatuses.value.set('a1', { execution_status: 'waiting_confirm' })
    expect(api.getStatusClass({ agent_id: 'a1', status: 'running' })).toBe('waiting_confirm')
  })
  it('isWaitingInput：等待态判定', () => {
    const { api, agentStatuses } = makeHarness()
    expect(api.isWaitingInput({ agent_id: 'a1', status: 'running' })).toBe(false)
    agentStatuses.value.set('a1', { execution_status: 'waiting_single' })
    expect(api.isWaitingInput({ agent_id: 'a1', status: 'running' })).toBe(true)
    agentStatuses.value.set('a1', { execution_status: 'waiting_multi' })
    expect(api.isWaitingInput({ agent_id: 'a1', status: 'running' })).toBe(true)
    agentStatuses.value.set('a1', { execution_status: 'waiting_confirm' })
    expect(api.isWaitingInput({ agent_id: 'a1', status: 'running' })).toBe(true)
  })
  it('fetchAgentStatus：成功拉取并更新状态映射', async () => {
    const { api, fetchWithAuth, agentStatuses, currentAgentId } = makeHarness()
    currentAgentId.value = 'a1'
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ execution_status: 'waiting_multi', non_interactive: false }),
    })
    const status = await api.fetchAgentStatus({ agent_id: 'a1', node_id: 'master' })
    expect(status).toBe('waiting_multi')
    expect(agentStatuses.value.get('a1')).toEqual({ execution_status: 'waiting_multi', non_interactive: false })
  })
  it('fetchAgentStatus：本地输入请求优先于轮询的 running', async () => {
    const { api, fetchWithAuth, agentStatuses, inputRequests, currentAgentId } = makeHarness()
    currentAgentId.value = 'a1'
    inputRequests.value.set('a1', { mode: 'single' })
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ execution_status: 'running', non_interactive: false }),
    })
    const status = await api.fetchAgentStatus({ agent_id: 'a1', node_id: 'master' })
    expect(status).toBe('waiting_single')
    expect(agentStatuses.value.get('a1')).toEqual({ execution_status: 'waiting_single', non_interactive: false })
  })
  it('fetchAgentStatus：本地等待态不被过期 running 覆盖', async () => {
    const { api, fetchWithAuth, agentStatuses, currentAgentId } = makeHarness()
    currentAgentId.value = 'a1'
    agentStatuses.value.set('a1', { execution_status: 'waiting_multi', non_interactive: false })
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ execution_status: 'running', non_interactive: false }),
    })
    const status = await api.fetchAgentStatus({ agent_id: 'a1', node_id: 'master' })
    expect(status).toBe('waiting_multi')
  })
  it('fetchAgentStatus：无 agent 时返回 running', async () => {
    const { api } = makeHarness()
    const status = await api.fetchAgentStatus(null)
    expect(status).toBe('running')
  })
  it('fetchAgentStatus：HTTP 失败返回 running', async () => {
    const { api, fetchWithAuth } = makeHarness()
    fetchWithAuth.mockResolvedValue({ ok: false, status: 500 })
    const status = await api.fetchAgentStatus({ agent_id: 'a1', node_id: 'master' })
    expect(status).toBe('running')
  })
  it('matchPermissionPattern：通配与精确匹配', () => {
    const { api } = makeHarness()
    expect(api.matchPermissionPattern('*:*', 'agent:create')).toBe(true)
    expect(api.matchPermissionPattern('agent:*', 'agent:create')).toBe(true)
    expect(api.matchPermissionPattern('agent:create', 'agent:create')).toBe(true)
    expect(api.matchPermissionPattern('agent:*', 'node:view')).toBe(false)
    expect(api.matchPermissionPattern('', 'agent:create')).toBe(false)
    expect(api.matchPermissionPattern('agent:*', '')).toBe(false)
  })
  it('hasPermission：管理员放行、denied 优先、allowed 匹配', () => {
    const { api, auth, userPermissions } = makeHarness()
    auth.value = { userInfo: { is_admin: true } }
    expect(api.hasPermission('anything')).toBe(true)
    auth.value = { userInfo: { is_admin: false } }
    userPermissions.value = { allowed: ['agent:*'], denied: ['agent:delete'] }
    expect(api.hasPermission('agent:create')).toBe(true)
    expect(api.hasPermission('agent:delete')).toBe(false)
    expect(api.hasPermission('')).toBe(false)
  })
  it('getCreateAgentDirectoryNodeId：按场景返回节点', () => {
    const { api, newAgentNodeId, openDirNodeId, orchestrateNodeId } = makeHarness()
    expect(api.getCreateAgentDirectoryNodeId()).toBe('master')
    api.dirDialogContext.value = 'open-dir'
    openDirNodeId.value = 'node1'
    expect(api.getCreateAgentDirectoryNodeId()).toBe('node1')
    api.dirDialogContext.value = 'orchestrate'
    orchestrateNodeId.value = 'node2'
    expect(api.getCreateAgentDirectoryNodeId()).toBe('node2')
  })
  it('resetDirectorySelectionState：复位目录选择状态', () => {
    const { api, showDirDialog, currentDirPath, dirList, selectedDir, dirSearchText, selectedDirIndex } = makeHarness()
    showDirDialog.value = true
    currentDirPath.value = '/tmp'
    dirList.value = [{ path: '/a' }]
    selectedDir.value = '/a'
    dirSearchText.value = 'x'
    selectedDirIndex.value = 2
    api.resetDirectorySelectionState()
    expect(showDirDialog.value).toBe(false)
    expect(currentDirPath.value).toBe('')
    expect(dirList.value).toEqual([])
    expect(selectedDir.value).toBe(null)
    expect(dirSearchText.value).toBe('')
    expect(selectedDirIndex.value).toBe(-1)
  })
  it('checkCodeAgentDirConflict：同目录 code_agent 冲突检测', () => {
    const { api, agentList, isStoppedAgent } = makeHarness()
    agentList.value = [
      { agent_id: 'a1', agent_type: 'code_agent', node_id: 'master', working_dir: '/w', name: '冲突Agent', status: 'running', worktree: false },
    ]
    const conflict = api.checkCodeAgentDirConflict({ agentType: 'code_agent', worktree: false, workingDir: '/w', nodeId: 'master' })
    expect(conflict).toContain('工作目录冲突')
    expect(conflict).toContain('冲突Agent')
    // 不同目录不冲突
    expect(api.checkCodeAgentDirConflict({ agentType: 'code_agent', worktree: false, workingDir: '/other', nodeId: 'master' })).toBe('')
    // 非 code_agent 不冲突
    expect(api.checkCodeAgentDirConflict({ agentType: 'agent', worktree: false, workingDir: '/w', nodeId: 'master' })).toBe('')
    // worktree 启用不冲突
    expect(api.checkCodeAgentDirConflict({ agentType: 'code_agent', worktree: true, workingDir: '/w', nodeId: 'master' })).toBe('')
    // 已停止的 agent 不冲突
    agentList.value[0].status = 'stopped'
    expect(api.checkCodeAgentDirConflict({ agentType: 'code_agent', worktree: false, workingDir: '/w', nodeId: 'master' })).toBe('')
    expect(isStoppedAgent).toHaveBeenCalled()
  })
  it('createAgentWithOptions：工作目录为空时报错', async () => {
    const { api } = makeHarness()
    const result = await api.createAgentWithOptions({ workingDir: '' })
    expect(result).toEqual({ ok: false, error: '工作目录不能为空' })
  })
  it('createAgentWithOptions：无交互模式无任务时报错', async () => {
    const { api } = makeHarness()
    const result = await api.createAgentWithOptions({ workingDir: '/w', noInteractionMode: true })
    expect(result).toEqual({ ok: false, error: '无交互模式下必须提供任务描述' })
  })
  it('createAgentWithOptions：成功创建返回 agent', async () => {
    const { api, fetchWithAuth } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { agent_id: 'ag1', node_id: 'master' } }),
    })
    const result = await api.createAgentWithOptions({ workingDir: '/w', name: 'foo' })
    expect(result.ok).toBe(true)
    expect(result.agent.agent_id).toBe('ag1')
    expect(result.agent.node_id).toBe('master')
    // 验证请求体
    const [url, opts] = fetchWithAuth.mock.calls[0]
    expect(url).toContain('/agents')
    const body = JSON.parse(opts.body)
    expect(body.agent_type).toBe('agent')
    expect(body.working_dir).toBe('/w')
    expect(body.node_id).toBe('master')
  })
  it('createAgentWithOptions：后端失败返回错误', async () => {
    const { api, fetchWithAuth } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: false,
      json: async () => ({ error: { message: '创建失败' } }),
    })
    const result = await api.createAgentWithOptions({ workingDir: '/w' })
    expect(result).toEqual({ ok: false, error: '创建失败' })
  })
  it('createAgentWithOptions：返回数据格式错误', async () => {
    const { api, fetchWithAuth } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: false, data: null }),
    })
    const result = await api.createAgentWithOptions({ workingDir: '/w' })
    expect(result).toEqual({ ok: false, error: '返回数据格式错误' })
  })
  it('createAgentWithOptions：冲突时返回冲突文案', async () => {
    const { api, agentList, fetchWithAuth } = makeHarness()
    agentList.value = [
      { agent_id: 'a1', agent_type: 'code_agent', node_id: 'master', working_dir: '/w', name: 'X', status: 'running', worktree: false },
    ]
    const result = await api.createAgentWithOptions({ agentType: 'code_agent', workingDir: '/w', nodeId: 'master' })
    expect(result.ok).toBe(false)
    expect(result.error).toContain('工作目录冲突')
    expect(fetchWithAuth).not.toHaveBeenCalled()
  })
  it('afterAgentCreated：加入列表并刷新', async () => {
    const { api, agentList, fetchWithAuth, hasNoPanel, openAgentInPanel, maybeStartTour } = makeHarness()
    hasNoPanel.value = false
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: [{ agent_id: 'ag1', node_id: 'master' }] }),
    })
    await api.afterAgentCreated({ agent_id: 'ag1' })
    // fetchAgentList 会用后端数据覆盖列表（反转后 ag1 仍在）
    expect(agentList.value.map(a => a.agent_id)).toContain('ag1')
    expect(fetchWithAuth).toHaveBeenCalled()
    expect(openAgentInPanel).toHaveBeenCalledWith({ agent_id: 'ag1' })
    await nextTick()
    expect(maybeStartTour).toHaveBeenCalledWith('agent')
  })
  it('afterAgentCreated：无 Panel 时保持在大厅', async () => {
    const { api, hasNoPanel, openAgentInPanel, fetchWithAuth } = makeHarness()
    hasNoPanel.value = true
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: [] }),
    })
    await api.afterAgentCreated({ agent_id: 'ag1' })
    expect(openAgentInPanel).not.toHaveBeenCalled()
    expect(fetchWithAuth).toHaveBeenCalled()
  })
  it('createAgent：无目录时直接返回', async () => {
    const { api, newAgentDir, showCreateAgentModal } = makeHarness()
    newAgentDir.value = ''
    await api.createAgent()
    expect(showCreateAgentModal.value).toBe(false)
    expect(newAgentDir.value).toBe('')
  })
  it('createAgent：成功创建后关闭弹窗并重置表单', async () => {
    const { api, fetchWithAuth, newAgentDir, newAgentName, newAgentNodeId, getDefaultCreateAgentNodeId, newAgentType, showCreateAgentModal, generateAgentName, hasNoPanel } = makeHarness()
    newAgentDir.value = '/w'
    newAgentType.value = 'agent'
    hasNoPanel.value = true
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { agent_id: 'ag1', node_id: 'master' } }),
    })
    await api.createAgent()
    expect(showCreateAgentModal.value).toBe(false)
    expect(newAgentDir.value).toBe('~')
    expect(getDefaultCreateAgentNodeId).toHaveBeenCalled()
    expect(newAgentName.value).toContain('agent-agent')
  })
  it('openQuickCreateAgent：打开快捷弹窗并调用 pushOverlayState', () => {
    const { api, pushOverlayState, showQuickCreateAgentModal } = makeHarness()
    api.openQuickCreateAgent()
    expect(showQuickCreateAgentModal.value).toBe(true)
    expect(pushOverlayState).toHaveBeenCalled()
  })
  it('submitQuickCreateAgent：空任务直接返回', async () => {
    const { api, quickCreateAgentLoading } = makeHarness()
    await api.submitQuickCreateAgent({ task: '' })
    expect(quickCreateAgentLoading.value).toBe(false)
  })
  it('submitQuickCreateAgent：成功创建后关闭弹窗', async () => {
    const { api, fetchWithAuth, showQuickCreateAgentModal, quickCreateAgentLoading } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { agent_id: 'ag1', node_id: 'master' } }),
    })
    await api.submitQuickCreateAgent({ task: 'do something' })
    expect(showQuickCreateAgentModal.value).toBe(false)
    expect(quickCreateAgentLoading.value).toBe(false)
  })
  it('submitQuickCreateAgent：失败显示错误', async () => {
    const { api, fetchWithAuth, quickCreateAgentError, quickCreateAgentLoading } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: false,
      json: async () => ({ error: { message: '创建失败' } }),
    })
    await api.submitQuickCreateAgent({ task: 'do something' })
    expect(quickCreateAgentError.value).toBe('创建失败')
    expect(quickCreateAgentLoading.value).toBe(false)
  })
  it('openCompletions：无当前 Agent 时提示', async () => {
    const { api, currentAgent } = makeHarness()
    currentAgent.value = null
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    await api.openCompletions()
    expect(alertSpy).toHaveBeenCalledWith('请先选择一个 Agent')
    alertSpy.mockRestore()
  })
  it('openCompletions：成功拉取补全列表', async () => {
    const { api, currentAgent, currentAgentId, fetchWithAuth, showCompletions, completions } = makeHarness()
    currentAgent.value = { agent_id: 'a1', node_id: 'master' }
    currentAgentId.value = 'a1'
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: [{ value: 'foo', display: 'foo' }] }),
    })
    await api.openCompletions()
    expect(showCompletions.value).toBe(true)
    expect(completions.value).toEqual([{ value: 'foo', display: 'foo' }])
  })
  it('closeCompletionsWithoutSelect：复位补全状态', () => {
    const { api, showCompletions, completionCursorPos, completionHasAtSymbol, completionAgentId, completionSource } = makeHarness()
    showCompletions.value = true
    completionCursorPos.value = 3
    completionHasAtSymbol.value = true
    completionAgentId.value = 'a1'
    completionSource.value = 'lobby'
    api.closeCompletionsWithoutSelect()
    expect(showCompletions.value).toBe(false)
    expect(completionCursorPos.value).toBe(-1)
    expect(completionHasAtSymbol.value).toBe(false)
    expect(completionAgentId.value).toBe(null)
    expect(completionSource.value).toBe('panel')
  })
  it('handleCompletionKeydown：ArrowDown/ArrowUp 导航', () => {
    const { api, completions, selectedIndex } = makeHarness()
    completions.value = [{ value: 'a' }, { value: 'b' }]
    const down = { key: 'ArrowDown', preventDefault: vi.fn(), ctrlKey: false, altKey: false, metaKey: false }
    api.handleCompletionKeydown(down)
    expect(selectedIndex.value).toBe(0)
    api.handleCompletionKeydown(down)
    expect(selectedIndex.value).toBe(1)
    const up = { key: 'ArrowUp', preventDefault: vi.fn(), ctrlKey: false, altKey: false, metaKey: false }
    api.handleCompletionKeydown(up)
    expect(selectedIndex.value).toBe(0)
  })
  it('handleCompletionKeydown：Escape 关闭', () => {
    const { api, showCompletions } = makeHarness()
    showCompletions.value = true
    const esc = { key: 'Escape', preventDefault: vi.fn(), ctrlKey: false, altKey: false, metaKey: false }
    api.handleCompletionKeydown(esc)
    expect(showCompletions.value).toBe(false)
  })
  it('fetchAgentList：拉取并反转列表、自动连接在线 agent', async () => {
    const { api, fetchWithAuth, agentList, autoConnectToOnlineAgents, showWorkspacePanel, agentListLoaded } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: [{ agent_id: 'a1', node_id: 'master' }, { agent_id: 'a2', node_id: 'master' }] }),
    })
    await api.fetchAgentList()
    expect(agentList.value).toHaveLength(2)
    expect(agentList.value[0].agent_id).toBe('a2') // 反转后 a2 在前
    expect(autoConnectToOnlineAgents).toHaveBeenCalled()
    expect(showWorkspacePanel.value).toBe(true)
    expect(agentListLoaded.value).toBe(true)
  })
  it('fetchAgentList：无 Agent 时不打开工作区', async () => {
    const { api, fetchWithAuth, showWorkspacePanel, agentListLoaded } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: [] }),
    })
    await api.fetchAgentList()
    expect(showWorkspacePanel.value).toBe(false)
    expect(agentListLoaded.value).toBe(true)
  })
  it('buildCopiedAgentPayload：构造复制请求参数', () => {
    const { api } = makeHarness()
    const payload = api.buildCopiedAgentPayload({
      agent_type: 'code_agent',
      working_dir: '/w',
      llm_group: 'g1',
      worktree: true,
      quick_mode: true,
      restore_session: false,
      no_interaction_mode: false,
      task: 't',
      node_id: 'n1',
      proxy_node: 'p1',
    }, 'copy-name', 'n2')
    expect(payload).toEqual({
      agent_type: 'code_agent',
      working_dir: '/w',
      name: 'copy-name',
      llm_group: 'g1',
      worktree: true,
      quick_mode: true,
      restore_session: false,
      no_interaction_mode: false,
      task: 't',
      node_id: 'n2',
      proxy_node: 'p1',
    })
  })
  it('copyAgent：填充表单并打开创建弹窗', async () => {
    const { api, fetchWithAuth, newAgentType, newAgentDir, newAgentName, showCreateAgentModal, skipNameWatch } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: [] }),
    })
    await api.copyAgent({ agent_id: 'a1', agent_type: 'code_agent', working_dir: '/w', llm_group: 'g1', node_id: 'master' })
    expect(newAgentType.value).toBe('code_agent')
    expect(newAgentDir.value).toBe('/w')
    expect(showCreateAgentModal.value).toBe(true)
    expect(newAgentName.value).toBeTruthy()
    await nextTick()
    expect(skipNameWatch.value).toBe(false)
  })
  it('batchCopyAgents：无选中时提示', async () => {
    const { api, showToast, selectedAgents } = makeHarness()
    selectedAgents.value = new Set()
    await api.batchCopyAgents()
    expect(showToast).toHaveBeenCalledWith('请先选择要复制的 Agent', 'warning')
  })
  it('batchCopyAgents：全部成功复制', async () => {
    const { api, agentList, selectedAgents, fetchWithAuth, showToast, isBatchMode } = makeHarness()
    agentList.value = [{ agent_id: 'a1', node_id: 'master' }]
    selectedAgents.value = new Set(['a1'])
    fetchWithAuth.mockResolvedValue({ ok: true })
    await api.batchCopyAgents()
    expect(showToast).toHaveBeenCalledWith('成功复制 1 个 Agent', 'success')
    expect(isBatchMode.value).toBe(false)
    expect(selectedAgents.value.size).toBe(0)
  })
  it('onLobbyAddAgentToGroup：无 agentId 时返回', () => {
    const { api, showToast } = makeHarness()
    api.onLobbyAddAgentToGroup({})
    expect(showToast).not.toHaveBeenCalled()
  })
  it('onLobbyAddAgentToGroup：加入现有分组', () => {
    const { api, agentList, agentGroups, saveAgentGroups, showToast } = makeHarness()
    agentList.value = [{ agent_id: 'a1', status: 'running' }]
    agentGroups.value = [{ id: 'g1', name: '组1', agentIds: [] }]
    api.onLobbyAddAgentToGroup({ agentId: 'a1', groupId: 'g1' })
    expect(agentGroups.value[0].agentIds).toContain('a1')
    expect(saveAgentGroups).toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith('已加入「组1」', 'success')
  })
  it('onLobbyAddAgentToGroup：新建分组', () => {
    const { api, agentList, agentGroups, saveAgentGroups } = makeHarness()
    agentList.value = [{ agent_id: 'a1', status: 'running' }]
    api.onLobbyAddAgentToGroup({ agentId: 'a1', newGroupName: '新组' })
    expect(agentGroups.value).toHaveLength(1)
    expect(agentGroups.value[0].name).toBe('新组')
    expect(agentGroups.value[0].agentIds).toContain('a1')
    expect(saveAgentGroups).toHaveBeenCalled()
  })
  it('onLobbyAddAgentToGroup：已停止的 Agent 不能加入', () => {
    const { api, agentList, showToast, agentGroups } = makeHarness()
    agentList.value = [{ agent_id: 'a1', status: 'stopped' }]
    api.onLobbyAddAgentToGroup({ agentId: 'a1', groupId: 'g1' })
    expect(showToast).toHaveBeenCalledWith('已停止的 Agent 不能加入分组', 'warning')
    expect(agentGroups.value).toHaveLength(0)
  })
  it('onLobbyRemoveAgentFromGroup：移出分组', () => {
    const { api, agentGroups, saveAgentGroups, showToast } = makeHarness()
    agentGroups.value = [{ id: 'g1', name: '组1', agentIds: ['a1', 'a2'] }]
    api.onLobbyRemoveAgentFromGroup({ agentId: 'a1', groupId: 'g1' })
    expect(agentGroups.value[0].agentIds).toEqual(['a2'])
    expect(saveAgentGroups).toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith('已从「组1」移出', 'success')
  })
  it('addSelectedToGroup：无活跃选中时提示', () => {
    const { api, agentGroups, showToast } = makeHarness()
    agentGroups.value = [{ id: 'g1', name: '组1', agentIds: [] }]
    api.addSelectedToGroup('g1')
    expect(showToast).toHaveBeenCalledWith('没有可加入分组的活跃 Agent', 'warning')
  })
  it('addSelectedToGroup：添加选中活跃 agent', () => {
    const { api, agentList, agentGroups, selectedAgents, saveAgentGroups, isBatchMode } = makeHarness()
    agentList.value = [{ agent_id: 'a1', status: 'running' }, { agent_id: 'a2', status: 'stopped' }]
    agentGroups.value = [{ id: 'g1', name: '组1', agentIds: [] }]
    selectedAgents.value = new Set(['a1', 'a2'])
    api.addSelectedToGroup('g1')
    expect(agentGroups.value[0].agentIds).toEqual(['a1'])
    expect(saveAgentGroups).toHaveBeenCalled()
    expect(isBatchMode.value).toBe(false)
  })
  it('createGroupWithAgents：创建分组并加入选中', () => {
    const { api, agentList, agentGroups, selectedAgents, saveAgentGroups } = makeHarness()
    agentList.value = [{ agent_id: 'a1', status: 'running' }]
    selectedAgents.value = new Set(['a1'])
    api.createGroupWithAgents('新分组')
    expect(agentGroups.value).toHaveLength(1)
    expect(agentGroups.value[0].name).toBe('新分组')
    expect(agentGroups.value[0].agentIds).toEqual(['a1'])
    expect(saveAgentGroups).toHaveBeenCalled()
  })
  it('renameAgentGroup：重命名分组', () => {
    const { api, agentGroups, saveAgentGroups, showToast } = makeHarness()
    agentGroups.value = [{ id: 'g1', name: '旧名', agentIds: [] }]
    api.renameAgentGroup({ groupId: 'g1', name: '新名' })
    expect(agentGroups.value[0].name).toBe('新名')
    expect(saveAgentGroups).toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith('分组已重命名为「新名」', 'success')
  })
  it('deleteAgentGroup：确认后删除分组', () => {
    const { api, agentGroups, showConfirm, saveAgentGroups } = makeHarness()
    agentGroups.value = [{ id: 'g1', name: '组1', agentIds: [] }]
    api.deleteAgentGroup('g1')
    expect(showConfirm).toHaveBeenCalled()
    // 触发确认回调
    const confirmCb = showConfirm.mock.calls[0][1]
    confirmCb()
    expect(agentGroups.value).toHaveLength(0)
    expect(saveAgentGroups).toHaveBeenCalled()
  })
  it('viewRules：成功拉取规则并置顶已加载', async () => {
    const { api, fetchWithAuth, rulesContent, rulesLoadedContent, rulesLoading, showRulesModal } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ rules: [{ name: 'r1', is_loaded: false }, { name: 'r2', is_loaded: true }], loaded_rules_content: 'content' }),
    })
    await api.viewRules({ agent_id: 'a1', node_id: 'master' })
    expect(showRulesModal.value).toBe(true)
    expect(rulesContent.value[0].name).toBe('r2') // 已加载置顶
    expect(rulesLoadedContent.value).toBe('content')
    expect(rulesLoading.value).toBe(false)
  })
  it('viewTools：成功拉取工具并排序', async () => {
    const { api, fetchWithAuth } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ all_tools: [{ name: 'b' }, { name: 'a' }], allowed_tools: ['a'] }),
    })
    await api.viewTools({ agent_id: 'a1', node_id: 'master' })
    expect(api.showToolsModal.value).toBe(true)
    expect(api.toolsContent.value.all_tools[0].name).toBe('a') // 允许的工具排顶
    expect(api.toolsLoading.value).toBe(false)
  })
  it('renameAgent：填充重命名弹窗', () => {
    const { api, renamingAgent, renameAgentName, showRenameAgentModal } = makeHarness()
    api.renameAgent({ agent_id: 'a1', name: '旧名' })
    expect(renamingAgent.value).toEqual({ agent_id: 'a1', name: '旧名' })
    expect(renameAgentName.value).toBe('旧名')
    expect(showRenameAgentModal.value).toBe(true)
  })
  it('confirmRename：成功重命名', async () => {
    const { api, renamingAgent, renameAgentName, fetchWithAuth, showRenameAgentModal, showToast } = makeHarness()
    renamingAgent.value = { agent_id: 'a1', node_id: 'master' }
    renameAgentName.value = '新名'
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) })
    await api.confirmRename()
    expect(showRenameAgentModal.value).toBe(false)
    expect(showToast).toHaveBeenCalledWith('重命名成功', 'success')
    expect(fetchWithAuth).toHaveBeenCalled()
  })
  it('editAgentAccess：填充 ACL 弹窗', async () => {
    const { api, fetchWithAuth, availableUserOptions } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ data: { users: [{ username: 'u1' }] } }),
    })
    await api.editAgentAccess({ agent_id: 'a1', access_acl: { read: ['u1'], interact: ['u2'] } })
    expect(api.editingAccessAgent.value.agent_id).toBe('a1')
    expect(api.editAccessRead.value).toEqual(['u1'])
    expect(api.editAccessInteract.value).toEqual(['u2'])
    expect(api.showEditAccessModal.value).toBe(true)
    expect(fetchWithAuth).toHaveBeenCalled()
    expect(availableUserOptions.value).toEqual([{ username: 'u1' }])
  })
  it('saveAgentAccess：保存权限', async () => {
    const { api, fetchWithAuth, showToast } = makeHarness()
    api.editingAccessAgent.value = { agent_id: 'a1', node_id: 'master' }
    api.editAccessRead.value = ['u1']
    api.editAccessInteract.value = ['u2']
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) })
    await api.saveAgentAccess()
    expect(showToast).toHaveBeenCalledWith('权限更新成功', 'success')
    expect(api.showEditAccessModal.value).toBe(false)
    const [url, opts] = fetchWithAuth.mock.calls[0]
    expect(url).toContain('/access')
    const body = JSON.parse(opts.body)
    expect(body.access_acl).toEqual({ read: ['u1'], interact: ['u2'] })
  })
  it('deleteAgent：确认后删除并清理状态', async () => {
    const { api, showConfirm, agentList, fetchWithAuth, historyStorage, fileTreeState, fileTreeExpanded, fileTreeLoading, currentAgentId } = makeHarness()
    agentList.value = [{ agent_id: 'a1', node_id: 'master' }]
    currentAgentId.value = 'a1'
    // 预置一些文件树状态，验证删除后被清除
    fileTreeState.value.set('a1', {})
    fileTreeExpanded.value.set('a1', {})
    fileTreeLoading.value.set('a1', {})
    const deleteSpy1 = vi.spyOn(fileTreeState.value, 'delete')
    const deleteSpy2 = vi.spyOn(fileTreeExpanded.value, 'delete')
    const deleteSpy3 = vi.spyOn(fileTreeLoading.value, 'delete')
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    api.deleteAgent('a1')
    const confirmCb = showConfirm.mock.calls[0][1]
    await confirmCb()
    expect(historyStorage.clearHistoryForAgent).toHaveBeenCalledWith('a1')
    expect(historyStorage.pruneHistory).toHaveBeenCalled()
    expect(deleteSpy1).toHaveBeenCalledWith('a1')
    expect(deleteSpy2).toHaveBeenCalledWith('a1')
    expect(deleteSpy3).toHaveBeenCalledWith('a1')
    expect(currentAgentId.value).toBe(null)
    expect(fetchWithAuth).toHaveBeenCalled()
  })
  it('regenerateAgent：确认后重生（保存会话→删除→重建）', async () => {
    const { api, showConfirm, fetchWithAuth, showToast } = makeHarness()
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    api.regenerateAgent({ agent_id: 'a1', node_id: 'master', name: 'x', agent_type: 'agent', working_dir: '/w' })
    const confirmCb = showConfirm.mock.calls[0][1]
    await confirmCb()
    expect(showToast).toHaveBeenCalledWith('Agent 无损重生成功', 'success')
    expect(fetchWithAuth).toHaveBeenCalled()
  })
  it('batchDeleteAgents：无选中时提示', async () => {
    const { api, showToast, selectedAgents } = makeHarness()
    selectedAgents.value = new Set()
    await api.batchDeleteAgents()
    expect(showToast).toHaveBeenCalledWith('请先选择要删除的 Agent', 'warning')
  })
  it('batchDeleteAgents：全部成功删除', async () => {
    const { api, agentList, selectedAgents, fetchWithAuth, showToast, isBatchMode, showConfirm } = makeHarness()
    agentList.value = [{ agent_id: 'a1', node_id: 'master' }]
    selectedAgents.value = new Set(['a1'])
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    api.batchDeleteAgents()
    const confirmCb = showConfirm.mock.calls[0][1]
    await confirmCb()
    expect(showToast).toHaveBeenCalledWith('成功删除 1 个 Agent', 'success')
    expect(isBatchMode.value).toBe(false)
  })
  it('onLobbySelectAgent：打开对应 Agent 面板', () => {
    const { api, agentList, openAgentInPanel } = makeHarness()
    agentList.value = [{ agent_id: 'a1', node_id: 'master' }]
    api.onLobbySelectAgent('a1')
    expect(openAgentInPanel).toHaveBeenCalledWith({ agent_id: 'a1', node_id: 'master' })
  })
  it('onLobbySelectAgent：找不到 Agent 不打开', () => {
    const { api, openAgentInPanel } = makeHarness()
    api.onLobbySelectAgent('nonexistent')
    expect(openAgentInPanel).not.toHaveBeenCalled()
  })
  it('getLobbyInputState：waiting_confirm 返回确认态', () => {
    const { api, agentStatuses, panelConfirmData } = makeHarness()
    agentStatuses.value.set('a1', { execution_status: 'waiting_confirm' })
    panelConfirmData.value.set('a1', { message: '确认吗', defaultConfirm: false })
    const state = api.getLobbyInputState('a1')
    expect(state.mode).toBe('confirm')
    expect(state.confirmMessage).toBe('确认吗')
    expect(state.confirmDefault).toBe(false)
    expect(state.hasRequest).toBe(true)
  })
  it('getLobbyInputState：有输入请求返回对应模式', () => {
    const { api, inputRequests } = makeHarness()
    inputRequests.value.set('a1', { mode: 'single', tip: '输入', preset: 'pre', is_password: true })
    const state = api.getLobbyInputState('a1')
    expect(state.mode).toBe('single')
    expect(state.tip).toBe('输入')
    expect(state.preset).toBe('pre')
    expect(state.isPassword).toBe(true)
    expect(state.hasRequest).toBe(true)
  })
  it('getLobbyInputState：无请求返回默认多行', () => {
    const { api } = makeHarness()
    const state = api.getLobbyInputState('a1')
    expect(state.mode).toBe('multi')
    expect(state.hasRequest).toBe(false)
  })
  it('sendLobbyInput：confirm 模式发送确认结果', () => {
    const { api, sendConfirmResult } = makeHarness()
    api.sendLobbyInput('a1', 'y', 'confirm')
    expect(sendConfirmResult).toHaveBeenCalledWith(true, 'a1')
  })
  it('sendLobbyInput：single 模式直接发送', () => {
    const { api, sendInputDirectly, saveToHistory } = makeHarness()
    api.sendLobbyInput('a1', 'hello', 'single')
    expect(saveToHistory).toHaveBeenCalledWith('hello')
    expect(sendInputDirectly).toHaveBeenCalledWith('hello', 'single', 'a1')
  })
  it('sendLobbyInput：multi 模式直接发送', () => {
    const { api, sendInputDirectly, saveToHistory } = makeHarness()
    api.sendLobbyInput('a1', 'hello', 'multi')
    expect(sendInputDirectly).toHaveBeenCalledWith('hello', 'multi', 'a1')
  })
  it('getLobbyLatestOutput：优先返回 STREAM 输出', () => {
    const { api, allOutputs } = makeHarness()
    allOutputs.value.set('a1', [
      { output_type: 'STREAM', text: 'hello', html: '<p>hello</p>' },
    ])
    const out = api.getLobbyLatestOutput('a1')
    expect(out.html).toBe('<p>hello</p>')
    expect(out.outputType).toBe('STREAM')
  })
  it('getLobbyLatestOutput：无输出时回退历史', () => {
    const { api, historyStorage } = makeHarness()
    historyStorage.getHistoryForAgent.mockReturnValue([{ text: 'hist', output_type: 'STREAM' }])
    const out = api.getLobbyLatestOutput('a1')
    expect(out).not.toBe(null)
    expect(out.outputType).toBe('STREAM')
  })
  it('getLobbyLatestOutput：无任何输出返回 null', () => {
    const { api } = makeHarness()
    expect(api.getLobbyLatestOutput('a1')).toBe(null)
  })
  it('onLobbyComplete：waiting_multi 发送 Ctrl+C 信号', () => {
    const { api, agentStatuses, sendMessageToAgent, chatName, username } = makeHarness()
    agentStatuses.value.set('a1', { execution_status: 'waiting_multi' })
    chatName.value = 'chat'
    username.value = 'user'
    api.onLobbyComplete('a1')
    expect(sendMessageToAgent).toHaveBeenCalled()
    const [msg, agentId] = sendMessageToAgent.mock.calls[0]
    expect(msg.type).toBe('input_result')
    expect(msg.payload.text).toBe('__CTRL_C_PRESSED__')
    expect(agentId).toBe('a1')
  })
  it('onLobbyComplete：running 发送人工介入', () => {
    const { api, agentStatuses, sendMessageToAgent } = makeHarness()
    agentStatuses.value.set('a1', { execution_status: 'running' })
    api.onLobbyComplete('a1')
    expect(sendMessageToAgent).toHaveBeenCalledWith({ type: 'manual_interrupt', payload: {} }, 'a1')
  })
  it('onLobbyComplete：无 agentId 直接返回', () => {
    const { api, sendMessageToAgent } = makeHarness()
    api.onLobbyComplete(null)
    expect(sendMessageToAgent).not.toHaveBeenCalled()
  })
  it('switchAgent：已停止的 Agent 只加载本地历史', async () => {
    const { api, currentAgentId, loadHistoryMessages, sockets, panels, panelOutputLists, outputList } = makeHarness()
    const agent = { agent_id: 'a1', node_id: 'master', status: 'stopped' }
    panels.value = [{ id: 'p1', agentId: 'a1' }]
    panelOutputLists.set('p1', {})
    await api.switchAgent(agent)
    expect(currentAgentId.value).toBe('a1')
    expect(loadHistoryMessages).toHaveBeenCalledWith(false)
    // outputList 是 ref，Vue 深响应式代理后引用不同，用 toEqual 比较内容
    expect(outputList.value).toEqual(panelOutputLists.get('p1'))
  })
  it('switchAgent：同 Agent 且已连接时恢复本地状态', async () => {
    const { api, currentAgentId, agentStatuses, inputRequests, sockets, inputTip, inputMode, inputText, pendingInputAgentId } = makeHarness()
    currentAgentId.value = 'a1'
    const fakeWs = { readyState: WebSocket.OPEN }
    sockets.value.set('a1', fakeWs)
    agentStatuses.value.set('a1', { execution_status: 'waiting_single' })
    inputRequests.value.set('a1', { mode: 'single', tip: 'tip', preset: 'preset' })
    await api.switchAgent({ agent_id: 'a1', node_id: 'master', status: 'running' })
    expect(inputTip.value).toBe('tip')
    expect(inputMode.value).toBe('single')
    expect(inputText.value).toBe('preset')
    expect(pendingInputAgentId.value).toBe('a1')
  })
  it('switchAgent：不同 Agent 时切换并清理旧终端', async () => {
    const { api, currentAgentId, terminals, terminalHosts, disposeExecutionTerminal, inputRequests, loadHistoryMessages, fetchWithAuth, sockets } = makeHarness()
    currentAgentId.value = 'old'
    terminals.value = [{ agentId: 'old', terminal: {} }]
    terminalHosts.value = new Map([['old:e1', {}]])
    inputRequests.value.set('old', { mode: 'single' })
    loadHistoryMessages.mockResolvedValue()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ execution_status: 'running' }),
    })
    sockets.value = new Map()
    // 不连接 WebSocket（connectToAgent 返回），让 while 循环快速退出
    const agent = { agent_id: 'new', node_id: 'master', status: 'running' }
    // 用 fake timers 避免真实 2s 等待
    vi.useFakeTimers()
    const promise = api.switchAgent(agent)
    // 每轮循环有 await，先 flush 一轮
    await flushPromises()
    // 由于没有 ws，会进入 retry 分支等待 2s，直接推进时间（最多 20 次重试 = 40s）
    await vi.advanceTimersByTimeAsync(50000)
    await flushPromises()
    expect(currentAgentId.value).toBe('new')
    expect(disposeExecutionTerminal).toHaveBeenCalled()
    expect(inputRequests.value.has('old')).toBe(false)
    vi.useRealTimers()
  })
  it('fetchModelGroups：成功拉取并自动选择默认组', async () => {
    const { api, fetchWithAuth, modelGroups, newAgentModelGroup } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: [{ name: 'g1' }, { name: 'g2' }], default_llm_group: 'g2' }),
    })
    await api.fetchModelGroups('master')
    expect(modelGroups.value).toHaveLength(2)
    expect(newAgentModelGroup.value).toBe('g2')
  })
  it('fetchNodeStatus：成功拉取并确保 master 存在', async () => {
    const { api, fetchWithAuth, availableNodeOptions } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { nodes: [{ node_id: 'node1', status: 'running' }] } }),
    })
    await api.fetchNodeStatus()
    expect(availableNodeOptions.value.some(n => n.node_id === 'master')).toBe(true)
    expect(availableNodeOptions.value).toHaveLength(2)
  })
  it('fetchUserList：成功拉取用户列表', async () => {
    const { api, fetchWithAuth, availableUserOptions } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { users: [{ user_id: 'u1' }] } }),
    })
    await api.fetchUserList()
    expect(availableUserOptions.value).toEqual([{ user_id: 'u1' }])
  })
  it('fetchUserPermissions：成功拉取权限', async () => {
    const { api, fetchWithAuth, userPermissions, auth } = makeHarness()
    auth.value = { userInfo: { user_id: 'u1' } }
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { permissions: { allowed: ['agent:*'], denied: [] } } }),
    })
    await api.fetchUserPermissions()
    expect(userPermissions.value.allowed).toEqual(['agent:*'])
  })
  it('fetchUserAccessibleNodes：成功拉取可访问节点', async () => {
    const { api, fetchWithAuth, userAccessibleNodes, auth } = makeHarness()
    auth.value = { userInfo: { user_id: 'u1' } }
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { accessible_nodes: ['n1'] } }),
    })
    await api.fetchUserAccessibleNodes()
    expect(userAccessibleNodes.value).toEqual(['n1'])
  })
  it('formatNodeOptionLabel：带状态显示', () => {
    const { api, getNodeDisplayName } = makeHarness()
    getNodeDisplayName.mockReturnValue('节点1')
    expect(api.formatNodeOptionLabel({ node_id: 'n1', status: 'running' })).toBe('节点1 (running)')
    expect(api.formatNodeOptionLabel({ node_id: 'n1' })).toBe('节点1')
  })
  it('getDefaultTerminalNodeId：优先 master', () => {
    const { api } = makeHarness()
    expect(api.getDefaultTerminalNodeId([{ node_id: 'n1' }, { node_id: 'master' }])).toBe('master')
    expect(api.getDefaultTerminalNodeId([{ node_id: 'n1' }])).toBe('n1')
    expect(api.getDefaultTerminalNodeId([])).toBe('')
  })
  it('getAgentNodeLabel/getAgentProxyNodeLabel/getCurrentAgentNodeId/getWorkspaceTargetNodeId', () => {
    const { api, currentAgent, activeWorkspaceSession } = makeHarness()
    expect(api.getAgentNodeLabel({ node_id: 'n1' })).toBe('n1')
    expect(api.getAgentNodeLabel({})).toBe('master')
    expect(api.getAgentProxyNodeLabel({ proxy_node: 'p1' })).toBe('p1')
    currentAgent.value = { node_id: 'n2' }
    expect(api.getCurrentAgentNodeId()).toBe('n2')
    activeWorkspaceSession.value = { agent: { node_id: 'n3' } }
    expect(api.getWorkspaceTargetNodeId()).toBe('n3')
  })
  it('exitNonInteractiveMode：成功后更新本地状态', async () => {
    const { api, fetchWithAuth, agentStatuses } = makeHarness()
    agentStatuses.value.set('a1', { execution_status: 'running', non_interactive: true })
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    await api.exitNonInteractiveMode({ agent_id: 'a1', node_id: 'master' })
    expect(agentStatuses.value.get('a1').non_interactive).toBe(false)
  })
  it('openCreateAgentModal：加载数据并打开弹窗', async () => {
    const { api, fetchWithAuth, showCreateAgentModal, newAgentNodeId, getDefaultCreateAgentNodeId } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: [] }),
    })
    await api.openCreateAgentModal('master')
    expect(showCreateAgentModal.value).toBe(true)
    expect(newAgentNodeId.value).toBe('master')
  })
  it('openDirDialog：创建场景打开目录弹窗', async () => {
    const { api, fetchWithAuth, showDirDialog, newAgentDir, selectedDir } = makeHarness()
    newAgentDir.value = '/w'
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { current_path: '/', items: [{ type: 'directory', path: '/w' }] } }),
    })
    await api.openDirDialog()
    expect(showDirDialog.value).toBe(true)
    expect(api.dirDialogContext.value).toBe('create-agent')
    expect(selectedDir.value).toBe('/w')
  })
  it('confirmDirectory：创建场景回填目录并保存历史', async () => {
    const { api, selectedDir, newAgentDir, showDirDialog, saveRecentWorkDir } = makeHarness()
    api.dirDialogContext.value = 'create-agent'
    selectedDir.value = '/w'
    api.confirmDirectory()
    expect(newAgentDir.value).toBe('/w')
    expect(showDirDialog.value).toBe(false)
    expect(saveRecentWorkDir).toHaveBeenCalledWith('/w', 'master')
  })
  it('cancelDirDialog：复位场景', () => {
    const { api, showDirDialog, selectedDir } = makeHarness()
    showDirDialog.value = true
    api.dirDialogContext.value = 'open-dir'
    selectedDir.value = '/x'
    api.cancelDirDialog()
    expect(showDirDialog.value).toBe(false)
    expect(api.dirDialogContext.value).toBe('create-agent')
    expect(selectedDir.value).toBe(null)
  })
  it('selectDirectory：更新选中目录与索引', () => {
    const { api, filteredDirList, selectedDir, selectedDirIndex } = makeHarness()
    filteredDirList.value = [{ path: '/a' }, { path: '/b' }]
    api.selectDirectory('/b')
    expect(selectedDir.value).toBe('/b')
    expect(selectedDirIndex.value).toBe(1)
  })
  it('startNodeStatusRefresh/stopNodeStatusRefresh：定时刷新', () => {
    const { api, fetchWithAuth } = makeHarness()
    vi.useFakeTimers()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { nodes: [] } }),
    })
    api.startNodeStatusRefresh()
    vi.advanceTimersByTime(10000)
    expect(fetchWithAuth).toHaveBeenCalled()
    api.stopNodeStatusRefresh()
    vi.useRealTimers()
  })
  it('startAgentListRefresh/stopAgentListRefresh：定时刷新列表', async () => {
    const { api, fetchWithAuth } = makeHarness()
    vi.useFakeTimers()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: [] }),
    })
    api.startAgentListRefresh()
    await Promise.resolve()
    // 立即执行一次 + 3 秒一次
    vi.advanceTimersByTime(3000)
    await Promise.resolve()
    expect(fetchWithAuth.mock.calls.length).toBeGreaterThanOrEqual(2)
    api.stopAgentListRefresh()
    vi.useRealTimers()
  })
  it('getAgentNodeDisplayLabel：使用显示名', () => {
    const { api, getNodeDisplayName } = makeHarness()
    getNodeDisplayName.mockReturnValue('显示名')
    expect(api.getAgentNodeDisplayLabel({ node_id: 'n1' })).toBe('显示名')
  })
})
