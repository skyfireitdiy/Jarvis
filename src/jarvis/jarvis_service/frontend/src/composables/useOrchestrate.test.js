// useOrchestrate 单元测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useOrchestrate } from './useOrchestrate.js'
// 刷新所有微任务（async 函数多层 await 时用）
async function flushPromises() {
  for (let i = 0; i < 20; i++) {
    await Promise.resolve()
  }
}
// 构造 useOrchestrate 依赖注入 harness
function makeHarness(overrides = {}) {
  const agentList = ref([])
  const availableNodeOptions = ref([])
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/nodes/${nodeId}/${path}`)
  const fetchWithAuth = vi.fn()
  const filteredNodeOptionsForCreateAgent = ref([])
  const getDefaultCreateAgentNodeId = vi.fn(() => 'master')
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: 8080 }))
  const hasNoPanel = ref(true)
  const openAgentInPanel = vi.fn()
  const pipelineStore = { addPreview: vi.fn(), getPipeline: vi.fn() }
  const pipelineVersion = ref(0)
  const setWorkspaceSidebarView = vi.fn()
  const showToast = vi.fn()
  const showWorkspaceSidebar = ref(false)
  const readFileAsDataUrl = vi.fn(async (file) => `data:${file.name}`)
  const createAgentWithOptions = vi.fn()
  const fetchAgentList = vi.fn()
  const fetchNodeStatus = vi.fn()
  const dirDialogContext = ref('create-agent')
  const openDirDialog = vi.fn()
  const startAgentListRefresh = vi.fn()
  const api = useOrchestrate({
    agentList,
    availableNodeOptions,
    buildNodeHttpUrl,
    fetchWithAuth,
    filteredNodeOptionsForCreateAgent,
    getDefaultCreateAgentNodeId,
    getGatewayAddress,
    hasNoPanel,
    openAgentInPanel,
    pipelineStore,
    pipelineVersion,
    setWorkspaceSidebarView,
    showToast,
    showWorkspaceSidebar,
    readFileAsDataUrl,
    createAgentWithOptions,
    fetchAgentList,
    fetchNodeStatus,
    dirDialogContext,
    openDirDialog,
    startAgentListRefresh,
    ...overrides,
  })
  return {
    api,
    agentList,
    availableNodeOptions,
    buildNodeHttpUrl,
    fetchWithAuth,
    filteredNodeOptionsForCreateAgent,
    getDefaultCreateAgentNodeId,
    getGatewayAddress,
    hasNoPanel,
    openAgentInPanel,
    pipelineStore,
    pipelineVersion,
    setWorkspaceSidebarView,
    showToast,
    showWorkspaceSidebar,
    readFileAsDataUrl,
    createAgentWithOptions,
    fetchAgentList,
    fetchNodeStatus,
    dirDialogContext,
    openDirDialog,
    startAgentListRefresh,
  }
}
describe('useOrchestrate', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })
  it('初始状态：所有 ref 默认值正确', () => {
    const { api } = makeHarness()
    expect(api.showOrchestrateModal.value).toBe(false)
    expect(api.orchestrateNodeId.value).toBe('master')
    expect(api.orchestrateFilePath.value).toBe('')
    expect(api.orchestratePluginTemplates.value).toEqual([])
    expect(api.orchestratePluginTemplatesLoading.value).toBe(false)
    expect(api.orchestrateRecentFiles.value).toEqual([])
    expect(api.orchestrateAgents.value).toEqual([])
    expect(api.orchestrateHasFlow.value).toBe(false)
    expect(api.orchestrateNodes.value).toEqual([])
    expect(api.orchestrateActiveIndex.value).toBe(0)
    expect(api.orchestrateLoading.value).toBe(false)
    expect(api.orchestrateError.value).toBe('')
    expect(api.orchestrateCreating.value).toBe(false)
    expect(api.orchestrateResults.value).toEqual([])
    expect(api.orchestrateRunWorkingDir.value).toBe('')
    expect(api.orchestrateRunning.value).toBe(false)
    expect(api.orchestrateFileEntries.value).toEqual([])
    expect(api.orchestrateSelectedFile.value).toBe('')
    expect(api.orchestrateDialogRef.value).toBe(null)
    expect(api.orchestrateShowBrowser.value).toBe(false)
    expect(api.orchestrateCurrentDirPath.value).toBe('')
    expect(api.orchestrateLocalFileInput.value).toBe(null)
    expect(api.orchestrateDirSearchText.value).toBe('')
    expect(api.orchestrateSelectedIndex.value).toBe(-1)
    expect(api.ORCHESTRATE_RECENT_KEY).toBe('jarvis_recent_orchestrations')
    expect(api.ORCHESTRATE_RECENT_MAX).toBe(20)
    expect(api.ORCHESTRATE_FILE_EXTENSIONS).toEqual(['.yaml', '.yml', '.flow'])
  })
  it('buildOrchestrateAgentForm：字段映射与默认值兜底', () => {
    const { api } = makeHarness()
    const form = api.buildOrchestrateAgentForm({
      name: 'foo',
      working_dir: '/tmp',
      llm_group: 'g1',
      tool_group: 't1',
      task: 'do it',
      additional_args: '--x',
      quick_mode: true,
      restore_session: true,
      no_interaction_mode: true,
      node_id: 'node1',
      proxy_node: 'p1',
      access_acl: { read: ['u1'], interact: ['u2'] },
    }, 'fallback')
    expect(form).toEqual({
      name: 'foo',
      workingDir: '/tmp',
      llmGroup: 'g1',
      toolGroup: 't1',
      task: 'do it',
      additionalArgs: '--x',
      quickMode: true,
      restoreSession: true,
      noInteractionMode: true,
      nodeId: 'node1',
      proxyNode: 'p1',
      accessAclRead: ['u1'],
      accessAclInteract: ['u2'],
    })
    // 空 raw 时用 fallbackNodeId
    const empty = api.buildOrchestrateAgentForm({}, 'fb-node')
    expect(empty.nodeId).toBe('fb-node')
    expect(empty.workingDir).toBe('.')
    expect(empty.llmGroup).toBe('default')
  })
  it('openOrchestrateModal：打开弹窗、初始化状态、加载模板与最近历史', async () => {
    const { api, fetchNodeStatus, getDefaultCreateAgentNodeId, loadOrchestratePluginTemplates } = makeHarness()
    // 不 mock loadOrchestratePluginTemplates，让它真实执行（无 fetchWithAuth mock 时返回空）
    api.showOrchestrateModal.value = false
    await api.openOrchestrateModal()
    expect(api.showOrchestrateModal.value).toBe(true)
    expect(api.orchestrateError.value).toBe('')
    expect(api.orchestrateResults.value).toEqual([])
    expect(api.orchestrateAgents.value).toEqual([])
    expect(api.orchestrateHasFlow.value).toBe(false)
    expect(api.orchestrateActiveIndex.value).toBe(0)
    expect(api.orchestrateFilePath.value).toBe('')
    expect(getDefaultCreateAgentNodeId).toHaveBeenCalled()
  })
  it('openOrchestrateModal：节点选项为空时拉取节点状态', async () => {
    const { api, fetchNodeStatus } = makeHarness()
    await api.openOrchestrateModal()
    expect(fetchNodeStatus).toHaveBeenCalled()
  })
  it('closeOrchestrateModal：复位所有状态并把目录场景复位为 create-agent', () => {
    const { api, dirDialogContext } = makeHarness()
    api.showOrchestrateModal.value = true
    api.orchestrateAgents.value = [{ name: 'x' }]
    api.orchestrateHasFlow.value = true
    api.orchestrateNodes.value = [{ id: 'n1' }]
    api.orchestrateShowBrowser.value = true
    api.orchestrateFileEntries.value = [{ name: 'a' }]
    api.orchestrateSelectedFile.value = '/a.yaml'
    api.orchestrateCurrentDirPath.value = '/tmp'
    api.orchestrateDirSearchText.value = 'foo'
    api.orchestrateSelectedIndex.value = 3
    dirDialogContext.value = 'orchestrate'
    api.closeOrchestrateModal()
    expect(api.showOrchestrateModal.value).toBe(false)
    expect(api.orchestrateAgents.value).toEqual([])
    expect(api.orchestrateHasFlow.value).toBe(false)
    expect(api.orchestrateNodes.value).toEqual([])
    expect(api.orchestrateShowBrowser.value).toBe(false)
    expect(api.orchestrateFileEntries.value).toEqual([])
    expect(api.orchestrateSelectedFile.value).toBe('')
    expect(api.orchestrateCurrentDirPath.value).toBe('')
    expect(api.orchestrateDirSearchText.value).toBe('')
    expect(api.orchestrateSelectedIndex.value).toBe(-1)
    expect(dirDialogContext.value).toBe('create-agent')
  })
  it('loadOrchestrateRecentFiles：读取 localStorage 有效数据', () => {
    const { api } = makeHarness()
    localStorage.setItem('jarvis_recent_orchestrations', JSON.stringify([{ path: '/a.yaml', nodeId: 'master' }]))
    api.loadOrchestrateRecentFiles()
    expect(api.orchestrateRecentFiles.value).toEqual([{ path: '/a.yaml', nodeId: 'master' }])
  })
  it('loadOrchestrateRecentFiles：非法数据时回退为空数组', () => {
    const { api } = makeHarness()
    localStorage.setItem('jarvis_recent_orchestrations', JSON.stringify([{ path: 123 }]))
    api.loadOrchestrateRecentFiles()
    expect(api.orchestrateRecentFiles.value).toEqual([])
  })
  it('saveOrchestrateRecentFile：去重并置顶、持久化、限长', () => {
    const { api } = makeHarness()
    api.orchestrateRecentFiles.value = [
      { path: '/a.yaml', nodeId: 'master' },
      { path: '/b.yaml', nodeId: 'master' },
    ]
    api.saveOrchestrateRecentFile('/a.yaml', 'master')
    expect(api.orchestrateRecentFiles.value[0]).toEqual({ path: '/a.yaml', nodeId: 'master' })
    expect(api.orchestrateRecentFiles.value).toHaveLength(2)
    expect(JSON.parse(localStorage.getItem('jarvis_recent_orchestrations'))[0].path).toBe('/a.yaml')
    // 空路径不保存
    api.saveOrchestrateRecentFile('', 'master')
    expect(api.orchestrateRecentFiles.value).toHaveLength(2)
  })
  it('removeOrchestrateRecentFile：删除指定项并持久化', () => {
    const { api } = makeHarness()
    api.orchestrateRecentFiles.value = [
      { path: '/a.yaml', nodeId: 'master' },
      { path: '/b.yaml', nodeId: 'master' },
    ]
    api.removeOrchestrateRecentFile('/a.yaml', 'master')
    expect(api.orchestrateRecentFiles.value).toEqual([{ path: '/b.yaml', nodeId: 'master' }])
    expect(JSON.parse(localStorage.getItem('jarvis_recent_orchestrations'))).toHaveLength(1)
  })
  it('parseOrchestrationFile：成功解析后填充 agents/hasFlow/nodes 并记录最近历史', async () => {
    const { api, fetchWithAuth } = makeHarness()
    api.orchestrateFilePath.value = '/tmp/team.yaml'
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          path: '/tmp/team.yaml',
          agents: [{ name: 'a1', working_dir: '/w1' }],
          has_flow: false,
          nodes: [],
        },
      }),
    })
    await api.parseOrchestrationFile()
    expect(api.orchestrateLoading.value).toBe(false)
    expect(api.orchestrateError.value).toBe('')
    expect(api.orchestrateAgents.value).toHaveLength(1)
    expect(api.orchestrateAgents.value[0].name).toBe('a1')
    expect(api.orchestrateAgents.value[0].workingDir).toBe('/w1')
    expect(api.orchestrateHasFlow.value).toBe(false)
    expect(api.orchestrateRecentFiles.value[0].path).toBe('/tmp/team.yaml')
  })
  it('parseOrchestrationFile：.flow 且 has_flow 时 orchestrateHasFlow 为 true', async () => {
    const { api, fetchWithAuth } = makeHarness()
    api.orchestrateFilePath.value = '/tmp/flow.flow'
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          path: '/tmp/flow.flow',
          agents: [{ name: 'a1' }],
          has_flow: true,
          nodes: [{ id: 'n1' }],
        },
      }),
    })
    await api.parseOrchestrationFile()
    expect(api.orchestrateHasFlow.value).toBe(true)
    expect(api.orchestrateNodes.value).toEqual([{ id: 'n1' }])
  })
  it('parseOrchestrationFile：空路径时报错', async () => {
    const { api } = makeHarness()
    api.orchestrateFilePath.value = ''
    await api.parseOrchestrationFile()
    expect(api.orchestrateError.value).toBe('请输入编排文件路径')
  })
  it('parseOrchestrationFile：后端失败时报错', async () => {
    const { api, fetchWithAuth } = makeHarness()
    api.orchestrateFilePath.value = '/tmp/team.yaml'
    fetchWithAuth.mockResolvedValue({
      ok: false,
      json: async () => ({ success: false, error: { message: '文件不存在' } }),
    })
    await api.parseOrchestrationFile()
    expect(api.orchestrateError.value).toBe('文件不存在')
  })
  it('addOrchestrateAgent/removeOrchestrateAgent：标签页增删与激活索引调整', () => {
    const { api } = makeHarness()
    api.addOrchestrateAgent()
    api.addOrchestrateAgent()
    expect(api.orchestrateAgents.value).toHaveLength(2)
    expect(api.orchestrateActiveIndex.value).toBe(1)
    api.removeOrchestrateAgent(0)
    expect(api.orchestrateAgents.value).toHaveLength(1)
    expect(api.orchestrateActiveIndex.value).toBe(0)
    // 越界删除不生效
    api.removeOrchestrateAgent(5)
    expect(api.orchestrateAgents.value).toHaveLength(1)
  })
  it('createAllOrchestrateAgents：无 Agent 时报错', async () => {
    const { api } = makeHarness()
    await api.createAllOrchestrateAgents()
    expect(api.orchestrateError.value).toBe('没有可创建的 Agent')
  })
  it('createAllOrchestrateAgents：工作目录为空时报错并定位到该标签页', async () => {
    const { api } = makeHarness()
    api.orchestrateAgents.value = [
      { name: 'a1', workingDir: '', task: '', noInteractionMode: false, llmGroup: 'default', quickMode: false, restoreSession: false, nodeId: 'master', proxyNode: '', accessAclRead: [], accessAclInteract: [], toolGroup: 'default', additionalArgs: '' },
    ]
    await api.createAllOrchestrateAgents()
    expect(api.orchestrateError.value).toContain('工作目录不能为空')
    expect(api.orchestrateActiveIndex.value).toBe(0)
  })
  it('createAllOrchestrateAgents：无交互模式无任务时报错', async () => {
    const { api } = makeHarness()
    api.orchestrateAgents.value = [
      { name: 'a1', workingDir: '/w', task: '', noInteractionMode: true, llmGroup: 'default', quickMode: false, restoreSession: false, nodeId: 'master', proxyNode: '', accessAclRead: [], accessAclInteract: [], toolGroup: 'default', additionalArgs: '' },
    ]
    await api.createAllOrchestrateAgents()
    expect(api.orchestrateError.value).toContain('必须填写任务描述')
  })
  it('createAllOrchestrateAgents：全部成功时关闭弹窗、加入列表、刷新并提示', async () => {
    const { api, createAgentWithOptions, agentList, fetchAgentList, startAgentListRefresh, showToast, hasNoPanel, openAgentInPanel } = makeHarness()
    api.orchestrateAgents.value = [
      { name: 'a1', workingDir: '/w1', task: '', noInteractionMode: false, llmGroup: 'default', quickMode: false, restoreSession: false, nodeId: 'master', proxyNode: '', accessAclRead: [], accessAclInteract: [], toolGroup: 'default', additionalArgs: '' },
    ]
    createAgentWithOptions.mockResolvedValue({ ok: true, agent: { agent_id: 'ag1', name: 'a1' } })
    hasNoPanel.value = false
    await api.createAllOrchestrateAgents()
    expect(api.orchestrateCreating.value).toBe(false)
    expect(api.showOrchestrateModal.value).toBe(false)
    expect(api.orchestrateResults.value).toEqual([])
    expect(agentList.value[0]).toEqual({ agent_id: 'ag1', name: 'a1' })
    expect(fetchAgentList).toHaveBeenCalled()
    expect(startAgentListRefresh).toHaveBeenCalled()
    expect(openAgentInPanel).toHaveBeenCalledWith({ agent_id: 'ag1', name: 'a1' })
    expect(showToast).toHaveBeenCalledWith('已创建 1 个 Agent', 'success')
  })
  it('createAllOrchestrateAgents：部分成功时保留失败项并提示', async () => {
    const { api, createAgentWithOptions, showToast } = makeHarness()
    api.orchestrateAgents.value = [
      { name: 'a1', workingDir: '/w1', task: '', noInteractionMode: false, llmGroup: 'default', quickMode: false, restoreSession: false, nodeId: 'master', proxyNode: '', accessAclRead: [], accessAclInteract: [], toolGroup: 'default', additionalArgs: '' },
      { name: 'a2', workingDir: '/w2', task: '', noInteractionMode: false, llmGroup: 'default', quickMode: false, restoreSession: false, nodeId: 'master', proxyNode: '', accessAclRead: [], accessAclInteract: [], toolGroup: 'default', additionalArgs: '' },
    ]
    createAgentWithOptions
      .mockResolvedValueOnce({ ok: true, agent: { agent_id: 'ag1' } })
      .mockResolvedValueOnce({ ok: false, error: '失败' })
    await api.createAllOrchestrateAgents()
    expect(api.orchestrateResults.value).toEqual([
      { name: 'a1', ok: true, error: '' },
      { name: 'a2', ok: false, error: '失败' },
    ])
    // 部分成功：不关闭弹窗（保持原打开状态），保留失败项供修正后重试
    expect(api.showOrchestrateModal.value).toBe(false)
    expect(showToast).toHaveBeenCalledWith('创建完成：成功 1/2', 'warning')
  })
  it('openOrchestrateDirDialog：无 Agent 时不打开目录弹窗', () => {
    const { api, openDirDialog } = makeHarness()
    api.openOrchestrateDirDialog()
    expect(openDirDialog).not.toHaveBeenCalled()
  })
  it('openOrchestrateDirDialog：有 Agent 时设置场景并打开', () => {
    const { api, openDirDialog, dirDialogContext } = makeHarness()
    api.orchestrateAgents.value = [{ name: 'a1', workingDir: '/w' }]
    api.openOrchestrateDirDialog()
    expect(dirDialogContext.value).toBe('orchestrate')
    expect(openDirDialog).toHaveBeenCalled()
  })
  it('runOrchestration：无文件时报错', async () => {
    const { api } = makeHarness()
    api.orchestrateFilePath.value = ''
    await api.runOrchestration()
    expect(api.orchestrateError.value).toBe('请先选择并解析编排文件')
  })
  it('runOrchestration：成功后关闭弹窗并切到编排查看', async () => {
    const { api, fetchWithAuth, showToast, showWorkspaceSidebar, setWorkspaceSidebarView } = makeHarness()
    api.orchestrateFilePath.value = '/tmp/flow.flow'
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    })
    await api.runOrchestration()
    expect(api.orchestrateRunning.value).toBe(false)
    expect(api.showOrchestrateModal.value).toBe(false)
    expect(showToast).toHaveBeenCalledWith('流水线已启动，可在「编排查看」中查看进度', 'success')
    expect(showWorkspaceSidebar.value).toBe(true)
    expect(setWorkspaceSidebarView).toHaveBeenCalledWith('orchestration')
  })
  it('previewOrchestration：无 DAG 节点时报错', () => {
    const { api } = makeHarness()
    api.orchestrateNodes.value = []
    api.previewOrchestration()
    expect(api.orchestrateError.value).toBe('没有可预览的 DAG 节点，请先解析编排文件')
  })
  it('previewOrchestration：生成预览并切到编排查看', () => {
    const { api, pipelineStore, pipelineVersion, setWorkspaceSidebarView, showToast } = makeHarness()
    api.orchestrateNodes.value = [{ id: 'n1' }]
    api.orchestrateFilePath.value = '/tmp/flow.flow'
    api.previewOrchestration()
    expect(pipelineStore.addPreview).toHaveBeenCalled()
    expect(pipelineVersion.value).toBe(1)
    expect(showToast).toHaveBeenCalled()
    expect(api.showOrchestrateModal.value).toBe(false)
    expect(setWorkspaceSidebarView).toHaveBeenCalledWith('orchestration')
  })
  it('handleApproval：无 pipelineId 时直接返回', async () => {
    const { api, pipelineStore } = makeHarness()
    await api.handleApproval('approve', {})
    expect(pipelineStore.getPipeline).not.toHaveBeenCalled()
  })
  it('handleApproval：找不到流水线时提示', async () => {
    const { api, pipelineStore, showToast } = makeHarness()
    pipelineStore.getPipeline.mockReturnValue(undefined)
    await api.handleApproval('approve', { pipelineId: 'p1' })
    expect(showToast).toHaveBeenCalledWith('未找到该流水线记录', 'error')
  })
  it('handleApproval：拒绝时只记录决定', async () => {
    const { api, pipelineStore, fetchWithAuth, showToast } = makeHarness()
    pipelineStore.getPipeline.mockReturnValue({ orchestrationFile: '/f.flow', workingDir: '/w' })
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    await api.handleApproval('reject', { pipelineId: 'p1' })
    expect(fetchWithAuth).toHaveBeenCalledTimes(1)
    expect(showToast).toHaveBeenCalledWith('已拒绝', 'success')
  })
  it('handleApproval：放行时记录决定并重跑流水线', async () => {
    const { api, pipelineStore, fetchWithAuth, showToast } = makeHarness()
    pipelineStore.getPipeline.mockReturnValue({ orchestrationFile: '/f.flow', workingDir: '/w' })
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    await api.handleApproval('approve', { pipelineId: 'p1' })
    expect(fetchWithAuth).toHaveBeenCalledTimes(2)
    expect(showToast).toHaveBeenCalledWith('已放行，流水线已重跑', 'success')
  })
  it('isOrchestrateFile：识别允许的扩展名', () => {
    const { api } = makeHarness()
    expect(api.isOrchestrateFile('a.yaml')).toBe(true)
    expect(api.isOrchestrateFile('b.yml')).toBe(true)
    expect(api.isOrchestrateFile('c.flow')).toBe(true)
    expect(api.isOrchestrateFile('d.txt')).toBe(false)
    expect(api.isOrchestrateFile('e.YAML')).toBe(true)
  })
  it('filterOrchestrateEntries：按搜索关键词过滤', () => {
    const { api } = makeHarness()
    api.orchestrateDirSearchText.value = 'foo'
    const items = [
      { name: 'foo.yaml', path: '/foo.yaml' },
      { name: 'bar.yaml', path: '/bar.yaml' },
    ]
    const filtered = api.filterOrchestrateEntries(items)
    expect(filtered).toHaveLength(1)
    expect(filtered[0].name).toBe('foo.yaml')
  })
  it('fetchOrchestrateEntries：成功拉取目录与文件', async () => {
    const { api, fetchWithAuth } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          current_path: '/tmp',
          items: [
            { name: 'sub', path: '/tmp/sub', type: 'directory' },
            { name: 'a.yaml', path: '/tmp/a.yaml', type: 'file' },
          ],
        },
      }),
    })
    await api.fetchOrchestrateEntries('/tmp')
    expect(api.orchestrateCurrentDirPath.value).toBe('/tmp')
    expect(api.orchestrateFileEntries.value).toHaveLength(2)
  })
  it('toggleOrchestrateBrowser：展开时拉取初始路径', async () => {
    const { api, fetchWithAuth } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { current_path: '~', items: [] } }),
    })
    await api.toggleOrchestrateBrowser()
    expect(api.orchestrateShowBrowser.value).toBe(true)
    expect(fetchWithAuth).toHaveBeenCalled()
  })
  it('orchestrateInitialBrowsePath：文件路径取父目录，空取家目录', () => {
    const { api } = makeHarness()
    api.orchestrateFilePath.value = ''
    expect(api.orchestrateInitialBrowsePath()).toBe('~')
    api.orchestrateFilePath.value = '/a/b/team.yaml'
    expect(api.orchestrateInitialBrowsePath()).toBe('/a/b')
    api.orchestrateFilePath.value = '/dir'
    expect(api.orchestrateInitialBrowsePath()).toBe('/dir')
  })
  it('onOrchestrateSelectFile：回填路径', () => {
    const { api } = makeHarness()
    api.onOrchestrateSelectFile('/tmp/a.yaml')
    expect(api.orchestrateSelectedFile.value).toBe('/tmp/a.yaml')
    expect(api.orchestrateFilePath.value).toBe('/tmp/a.yaml')
  })
  it('onOrchestrateLocalSelect：触发隐藏文件输入框点击', () => {
    const { api } = makeHarness()
    const click = vi.fn()
    api.orchestrateLocalFileInput.value = { value: '/old', click }
    api.onOrchestrateLocalSelect()
    expect(click).toHaveBeenCalled()
  })
  it('onOrchestrateLocalFileChange：上传成功后回填路径并解析', async () => {
    const { api, fetchWithAuth, readFileAsDataUrl, showToast } = makeHarness()
    api.orchestrateCurrentDirPath.value = '/tmp'
    const file = { name: 'team.yaml' }
    const event = { target: { files: [file], value: '/x' } }
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    })
    await api.onOrchestrateLocalFileChange(event)
    expect(readFileAsDataUrl).toHaveBeenCalledWith(file)
    expect(api.orchestrateFilePath.value).toBe('/tmp/team.yaml')
    expect(showToast).toHaveBeenCalledWith('已上传到 /tmp/team.yaml', 'success')
  })
  it('handleOrchestrateSearchKeydown：Esc 收起面板', () => {
    const { api } = makeHarness()
    api.orchestrateShowBrowser.value = true
    const event = { key: 'Escape', preventDefault: vi.fn() }
    api.handleOrchestrateSearchKeydown(event)
    expect(api.orchestrateShowBrowser.value).toBe(false)
    expect(event.preventDefault).toHaveBeenCalled()
  })
  it('handleOrchestrateSearchKeydown：ArrowDown 选中下一项并同步高亮', () => {
    const { api } = makeHarness()
    api.orchestrateFileEntries.value = [
      { name: 'd1', path: '/d1', type: 'directory' },
      { name: 'a.yaml', path: '/a.yaml', type: 'file' },
    ]
    const event = { key: 'ArrowDown', preventDefault: vi.fn(), ctrlKey: false, altKey: false, metaKey: false }
    api.handleOrchestrateSearchKeydown(event)
    expect(api.orchestrateSelectedIndex.value).toBe(0)
    expect(event.preventDefault).toHaveBeenCalled()
    api.handleOrchestrateSearchKeydown(event)
    expect(api.orchestrateSelectedIndex.value).toBe(1)
    expect(api.orchestrateSelectedFile.value).toBe('/a.yaml')
  })
  it('handleOrchestrateSearchKeydown：Enter 进入目录', async () => {
    const { api, fetchWithAuth } = makeHarness()
    api.orchestrateFileEntries.value = [
      { name: 'd1', path: '/d1', type: 'directory' },
    ]
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { current_path: '/d1', items: [] } }),
    })
    const event = { key: 'ArrowDown', preventDefault: vi.fn(), ctrlKey: false, altKey: false, metaKey: false }
    api.handleOrchestrateSearchKeydown(event)
    const enterEvent = { key: 'Enter', preventDefault: vi.fn(), ctrlKey: false, altKey: false, metaKey: false }
    api.handleOrchestrateSearchKeydown(enterEvent)
    await flushPromises()
    expect(fetchWithAuth).toHaveBeenCalled()
  })
  it('onOrchestrateNodeChange：重置路径并重新拉取模板', async () => {
    const { api, fetchWithAuth } = makeHarness()
    api.orchestrateFilePath.value = '/old.yaml'
    api.orchestrateSelectedFile.value = '/old.yaml'
    api.orchestrateSelectedIndex.value = 2
    api.orchestrateShowBrowser.value = false
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { current_path: '~', items: [] } }),
    })
    await api.onOrchestrateNodeChange()
    expect(api.orchestrateFilePath.value).toBe('')
    expect(api.orchestrateSelectedFile.value).toBe('')
    expect(api.orchestrateSelectedIndex.value).toBe(-1)
  })
  it('loadOrchestratePluginTemplates：成功拉取模板并过滤无 file 项', async () => {
    const { api, fetchWithAuth } = makeHarness()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { orchestrations: [{ name: 't1', file: '/t1.yaml' }, { name: 't2' }] },
      }),
    })
    await api.loadOrchestratePluginTemplates()
    expect(api.orchestratePluginTemplatesLoading.value).toBe(false)
    expect(api.orchestratePluginTemplates.value).toEqual([{ name: 't1', file: '/t1.yaml' }])
  })
  it('selectOrchestratePluginTemplate：填入路径并解析', async () => {
    const { api, fetchWithAuth } = makeHarness()
    api.orchestrateFilePath.value = ''
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { path: '/t1.yaml', agents: [{ name: 'a1' }], has_flow: false, nodes: [] },
      }),
    })
    api.selectOrchestratePluginTemplate({ file: '/t1.yaml' })
    expect(api.orchestrateFilePath.value).toBe('/t1.yaml')
    await flushPromises()
    expect(api.orchestrateAgents.value).toHaveLength(1)
  })
})
