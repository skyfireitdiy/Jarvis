// useWorkspacePane 单元测试
// 覆盖：workspace 面板状态、pane 树核心（split/close/collapse/activate/move）、
// 视图路由（ensureAgentEditorPane/ensurePaneForView/setActivePaneView）、
// 布局持久化（sanitize/restore/persist）、内容恢复（restoreWorkspacePaneContents）、
// 插件扩展透传（usePlugins 返回符号）。
// mock usePlugins（内部调用）与 pluginExtensions 加载器，其余依赖注入直传/getter。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, computed } from 'vue'

// ---- mock usePlugins 模块（useWorkspacePane 内部调用）----
// 注意：vi.hoisted 内不能使用 ref/computed（尚未初始化），故 pluginState 在 hoisted 里只放
// 可序列化的 mock 函数与空壳，真正的 ref/computed 由 makeHarness 在运行时重建。
const { usePluginsMock, pluginStateShell } = vi.hoisted(() => {
  const pluginStateShell = {
    pluginExtensions: null,
    pluginAdminTabs: null,
    pluginSidebarViews: null,
    pluginToolPanels: null,
    pluginSidebarTitle: vi.fn((view) => ''),
    pluginToolPanelTitle: vi.fn((view) => ''),
    WORKSPACE_SIDEBAR_TITLES: {},
    workspaceSidebarTitle: null,
    loadPluginExtensionsForUi: vi.fn(async () => {}),
    resolvePluginExtensionComponent: vi.fn(() => null),
    isPluginSidebarView: vi.fn(() => false),
    isPluginToolView: vi.fn(() => false),
    pluginSidebarCompCache: new Map(),
    activePluginSidebarComp: null,
    activePluginToolPanelComp: null,
  }
  const usePluginsMock = vi.fn(() => pluginStateShell)
  return { usePluginsMock, pluginStateShell }
})
vi.mock('./usePlugins.js', () => ({ usePlugins: usePluginsMock }))
// ---- mock pluginExtensions 加载器 ----
const { fetchPluginExtensionsMock, loadExtensionComponentMock } = vi.hoisted(() => {
  return {
    fetchPluginExtensionsMock: vi.fn(async () => []),
    loadExtensionComponentMock: vi.fn(async () => null),
  }
})
vi.mock('../pluginExtensions.js', () => ({
  fetchPluginExtensions: fetchPluginExtensionsMock,
  loadExtensionComponent: loadExtensionComponentMock,
}))

// ---- 引入被测模块（须在 mock 之后）----
const { useWorkspacePane } = await import('./useWorkspacePane.js')

// ---- mock 全局环境 ----
function setupGlobals() {
  globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 0)
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  globalThis.URL.revokeObjectURL = vi.fn()
}

// 构造 useWorkspacePane 依赖注入 harness
function makeHarness(overrides = {}) {
  // —— 重建 pluginState 的 ref/computed（vi.hoisted 内无法使用 ref/computed）——
  const pluginState = {
    ...pluginStateShell,
    pluginExtensions: ref([]),
    pluginAdminTabs: computed(() => pluginState.pluginExtensions.value.filter(e => e.extType === 'admin_tabs')),
    pluginSidebarViews: computed(() => pluginState.pluginExtensions.value.filter(e => e.extType === 'sidebar_views')),
    pluginToolPanels: computed(() => pluginState.pluginExtensions.value.filter(e => e.extType === 'tool_panels')),
    workspaceSidebarTitle: computed(() => ''),
    activePluginSidebarComp: computed(() => null),
    activePluginToolPanelComp: computed(() => null),
  }
  usePluginsMock.mockReturnValue(pluginState)
  // —— 直传依赖（定义在调用点之前）——
  const fetchWithAuth = vi.fn()
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const getHttpProtocol = vi.fn(() => 'http')
  const hasAuthToken = vi.fn(() => true)
  const windowWidth = ref(1200)
  const clamp = vi.fn((v, min, max) => Math.min(Math.max(v, min), max))
  const focusWindow = vi.fn()
  const getWorkspaceTabByPath = vi.fn(() => null)
  const activeWorkspaceTab = ref(null)
  const editorViews = new Map()
  const workspaceViewPanes = new Map()
  const diffEditorViews = new Map()
  const workspacePaneTabs = new Map()
  const workspacePaneTabsVersion = ref(0)
  const remountMonacoEditor = vi.fn()
  const scheduleWorkspaceLayout = vi.fn()
  const layoutMonacoEditor = vi.fn()
  const activateWorkspaceTab = vi.fn()
  const openWorkspaceFile = vi.fn(async () => {})
  const layoutGitDiffEditor = vi.fn()
  const disposeDiffEditorForPane = vi.fn()
  const disposeAllDiffEditors = vi.fn()
  const loadDiffForPane = vi.fn(async () => {})
  // —— getter 注入依赖（定义在调用点之后，内部 xxx() 二次求值）——
  const panels = ref([])
  const activePanelId = ref(null)
  const closePanel = vi.fn()
  const getPanelAgent = vi.fn(() => null)
  const workspaceSessionPanelId = ref(null)
  const agentList = ref([])
  const gitAgentId = ref(null)
  const switchAgent = vi.fn(async () => {})
  const activeTerminalId = ref(null)
  const terminalSessions = ref([])
  const restoreTerminalSessions = vi.fn(() => vi.fn(async () => {}))
  const focusFirstIn = vi.fn()

  const api = useWorkspacePane({
    fetchWithAuth,
    getGatewayAddress,
    getHttpProtocol,
    hasAuthToken,
    windowWidth,
    // getter 注入（useWorkspaceEditor B 域符号，useWorkspacePane 内部 xxx() 二次求值）
    clamp: () => clamp,
    focusWindow: () => focusWindow,
    getWorkspaceTabByPath: () => getWorkspaceTabByPath,
    activeWorkspaceTab: () => activeWorkspaceTab,
    editorViews: () => editorViews,
    workspaceViewPanes: () => workspaceViewPanes,
    diffEditorViews: () => diffEditorViews,
    workspacePaneTabs: () => workspacePaneTabs,
    workspacePaneTabsVersion: () => workspacePaneTabsVersion,
    remountMonacoEditor: () => remountMonacoEditor,
    scheduleWorkspaceLayout: () => scheduleWorkspaceLayout,
    layoutMonacoEditor: () => layoutMonacoEditor,
    activateWorkspaceTab: () => activateWorkspaceTab,
    openWorkspaceFile: () => openWorkspaceFile,
    // getter 注入（useWorkspacePane 内部 xxx()() 二次求值）
    layoutGitDiffEditor: () => layoutGitDiffEditor,
    disposeDiffEditorForPane: () => disposeDiffEditorForPane,
    disposeAllDiffEditors: () => disposeAllDiffEditors,
    loadDiffForPane: () => loadDiffForPane,
    // getter 注入
    panels: () => panels,
    activePanelId: () => activePanelId,
    closePanel: () => closePanel,
    getPanelAgent: () => getPanelAgent,
    workspaceSessionPanelId: () => workspaceSessionPanelId,
    agentList: () => agentList,
    gitAgentId: () => gitAgentId,
    switchAgent: () => switchAgent,
    activeTerminalId: () => activeTerminalId,
    terminalSessions: () => terminalSessions,
    restoreTerminalSessions: () => restoreTerminalSessions,
    focusFirstIn: () => focusFirstIn,
    ...overrides,
  })
  return {
    api,
    fetchWithAuth,
    getGatewayAddress,
    getHttpProtocol,
    hasAuthToken,
    windowWidth,
    clamp,
    focusWindow,
    getWorkspaceTabByPath,
    activeWorkspaceTab,
    editorViews,
    workspaceViewPanes,
    diffEditorViews,
    workspacePaneTabs,
    workspacePaneTabsVersion,
    remountMonacoEditor,
    scheduleWorkspaceLayout,
    layoutMonacoEditor,
    activateWorkspaceTab,
    openWorkspaceFile,
    layoutGitDiffEditor,
    disposeDiffEditorForPane,
    disposeAllDiffEditors,
    loadDiffForPane,
    panels,
    activePanelId,
    closePanel,
    getPanelAgent,
    workspaceSessionPanelId,
    agentList,
    gitAgentId,
    switchAgent,
    activeTerminalId,
    terminalSessions,
    restoreTerminalSessions,
    focusFirstIn,
  }
}

// 统计 pane 树 leaf 数量
function countLeaves(tree) {
  if (!tree) return 0
  if (tree.type === 'leaf') return 1
  return (tree.children || []).reduce((acc, c) => acc + countLeaves(c), 0)
}

beforeEach(() => {
  setupGlobals()
  localStorage.clear()
  usePluginsMock.mockClear()
  fetchPluginExtensionsMock.mockClear()
  loadExtensionComponentMock.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useWorkspacePane', () => {
  it('暴露预期接口（refs / computed / 函数 / 插件符号）', () => {
    const { api } = makeHarness()
    // refs
    expect(typeof api.workspacePaneTree).toBe('object')
    expect(typeof api.activePaneId).toBe('object')
    expect(typeof api.workspaceSessions).toBe('object')
    expect(typeof api.workspaceTabs).toBe('object')
    expect(typeof api.workspaceMainView).toBe('object')
    expect(typeof api.workspacePaneCount).toBe('object')
    expect(typeof api.activePane).toBe('object')
    expect(typeof api.workspaceSidebarView).toBe('object')
    // 函数
    expect(typeof api.findWorkspacePaneById).toBe('function')
    expect(typeof api.activateWorkspacePane).toBe('function')
    expect(typeof api.splitWorkspacePane).toBe('function')
    expect(typeof api.closeWorkspacePane).toBe('function')
    expect(typeof api.collapseWorkspacePanes).toBe('function')
    expect(typeof api.restoreWorkspacePaneLayout).toBe('function')
    expect(typeof api.restoreWorkspacePaneContents).toBe('function')
    // 插件符号
    expect(typeof api.pluginExtensions).toBe('object')
    expect(typeof api.loadPluginExtensionsForUi).toBe('function')
    expect(typeof api.workspaceSidebarTitle).toBe('object')
  })

  it('初始状态：单 leaf file 视图，workspaceMainView 派生', () => {
    const { api } = makeHarness()
    expect(api.workspacePaneCount.value).toBe(1)
    expect(api.workspacePaneTree.value.type).toBe('leaf')
    expect(api.workspacePaneTree.value.view).toBe('file')
    expect(api.activePaneId.value).toBe(api.workspacePaneTree.value.id)
    expect(api.workspaceMainView.value).toBe('file')
    expect(api.activePane.value.id).toBe(api.workspacePaneTree.value.id)
  })

  it('splitWorkspacePane：切分单 leaf 为 row split，新 leaf 激活', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const tree = api.workspacePaneTree.value
    expect(tree.type).toBe('split')
    expect(tree.direction).toBe('row')
    expect(tree.ratio).toBe(0.5)
    expect(countLeaves(tree)).toBe(2)
    // 新 leaf 是激活 pane，view 为 empty
    expect(api.activePane.value.view).toBe('empty')
    expect(api.activePaneId.value).not.toBe(rootId)
    // 原 leaf 保留在首位
    expect(tree.children[0].id).toBe(rootId)
    // 首次分割：全局标签固化到原 pane
    expect(api.workspacePaneCount.value).toBe(2)
  })

  it('splitWorkspacePane：column 方向', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'column')
    expect(api.workspacePaneTree.value.direction).toBe('column')
  })

  it('splitWorkspacePane：windowWidth <= 768 时返回（移动端不支持）', () => {
    const { api, windowWidth } = makeHarness()
    windowWidth.value = 700
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    expect(api.workspacePaneCount.value).toBe(1)
  })

  it('closeWorkspacePane：关闭一个 leaf 后回到单 leaf', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    expect(api.workspacePaneCount.value).toBe(2)
    // 关闭新 leaf（激活 pane）
    const newId = api.activePaneId.value
    api.closeWorkspacePane(newId)
    expect(api.workspacePaneCount.value).toBe(1)
    expect(api.workspacePaneTree.value.type).toBe('leaf')
    expect(api.workspacePaneTree.value.id).toBe(rootId)
  })

  it('closeWorkspacePane：仅剩一个 leaf 时不允许关闭', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.closeWorkspacePane(rootId)
    expect(api.workspacePaneCount.value).toBe(1)
    expect(api.workspacePaneTree.value.id).toBe(rootId)
  })

  it('collapseWorkspacePanes：收起所有分割回到单 file leaf', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    api.splitWorkspacePane(api.activePaneId.value, 'column')
    expect(api.workspacePaneCount.value).toBe(3)
    api.collapseWorkspacePanes()
    expect(api.workspacePaneCount.value).toBe(1)
    expect(api.workspacePaneTree.value.type).toBe('leaf')
    expect(api.workspacePaneTree.value.view).toBe('file')
  })

  it('activateWorkspacePane：激活存在的 pane，忽略不存在的', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const newId = api.activePaneId.value
    // 激活原 leaf
    api.activateWorkspacePane(rootId)
    expect(api.activePaneId.value).toBe(rootId)
    // 激活新 leaf
    api.activateWorkspacePane(newId)
    expect(api.activePaneId.value).toBe(newId)
    // 不存在的 pane 忽略
    api.activateWorkspacePane('pane-nonexistent')
    expect(api.activePaneId.value).toBe(newId)
  })

  it('moveActivePaneInDirection：未分割时返回 false', () => {
    const { api } = makeHarness()
    expect(api.moveActivePaneInDirection('right')).toBe(false)
  })

  it('moveActivePaneInDirection：row split 时向右切换到另一 pane', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    // 新 leaf 是激活的（右侧），向左切换回 root
    expect(api.moveActivePaneInDirection('left')).toBe(true)
    expect(api.activePaneId.value).toBe(rootId)
    // 再向右切回新 leaf
    expect(api.moveActivePaneInDirection('right')).toBe(true)
    expect(api.activePaneId.value).not.toBe(rootId)
  })

  it('toggleMaximizeWorkspacePane：最大化/还原', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.toggleMaximizeWorkspacePane(rootId)
    expect(api.maximizedPaneId.value).toBe(rootId)
    api.toggleMaximizeWorkspacePane(rootId)
    expect(api.maximizedPaneId.value).toBeNull()
  })

  it('setActivePaneView：切换激活 pane 视图', () => {
    const { api } = makeHarness()
    const ok = api.setActivePaneView('terminal')
    expect(ok).toBe(true)
    expect(api.activePane.value.view).toBe('terminal')
    // 切到 session 需要 sessionPanelId
    expect(api.setActivePaneView('session')).toBe(false)
    expect(api.setActivePaneView('session', 'panel-1')).toBe(true)
    expect(api.activePane.value.view).toBe('session')
    expect(api.activePane.value.sessionPanelId).toBe('panel-1')
  })

  it('setActivePaneView：session 面板去重（同一 panel 只允许一个 pane）', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    // 两个 pane 都承载 panel-1
    api.setActivePaneViewForPane(api.workspacePaneTree.value.children[0], 'session', 'panel-1')
    api.setActivePaneViewForPane(api.workspacePaneTree.value.children[1], 'session', 'panel-1')
    // 第二个 pane 设置时，第一个被清空
    const first = api.workspacePaneTree.value.children[0]
    const second = api.workspacePaneTree.value.children[1]
    expect(first.view).toBe('empty')
    expect(second.view).toBe('session')
    expect(second.sessionPanelId).toBe('panel-1')
  })

  it('ensureAgentEditorPane：Agent 已有 file pane 时复用', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.ensureAgentEditorPane('agent-1')
    // 未分割时当前是 file view，直接复用
    expect(api.activePane.value.view).toBe('file')
    expect(api.activePane.value.agentId).toBe('agent-1')
    expect(api.activePaneId.value).toBe(rootId)
  })

  it('ensureAgentEditorPane：当前非 file 视图时分割出新 pane', () => {
    const { api } = makeHarness()
    api.setActivePaneView('terminal')
    const paneId = api.ensureAgentEditorPane('agent-1')
    expect(paneId).toBeTruthy()
    expect(api.workspacePaneCount.value).toBe(2)
    const pane = api.findWorkspacePaneById(api.workspacePaneTree.value, paneId)
    expect(pane.view).toBe('file')
    expect(pane.agentId).toBe('agent-1')
  })

  it('ensurePaneForView：chat/terminal host 单例复用', () => {
    const { api } = makeHarness()
    const id1 = api.ensurePaneForView('terminal')
    expect(id1).toBeTruthy()
    // 再次打开 terminal：复用同一 pane，不新增
    const id2 = api.ensurePaneForView('terminal')
    expect(id2).toBe(id1)
    expect(api.workspacePaneCount.value).toBe(1)
  })

  it('getWorkspacePaneTitle：各视图标题', () => {
    const { api } = makeHarness()
    const pane = api.workspacePaneTree.value
    // file 无绑定文件 → 空区域
    expect(api.getWorkspacePaneTitle(pane)).toBe('空区域')
    pane.view = 'chat'
    expect(api.getWorkspacePaneTitle(pane)).toBe('聊天室')
    pane.view = 'terminal'
    expect(api.getWorkspacePaneTitle(pane)).toBe('终端')
    pane.view = 'empty'
    expect(api.getWorkspacePaneTitle(pane)).toBe('空区域')
    // diff
    pane.view = 'diff'
    pane.diff = { filePath: '/home/user/a.js' }
    expect(api.getWorkspacePaneTitle(pane)).toBe('diff: a.js')
    // session：找到 panel agent
    pane.view = 'session'
    pane.sessionPanelId = 'panel-1'
    expect(api.getWorkspacePaneTitle(pane)).toBe('会话')
  })

  it('getWorkspacePaneStatus：file pane 状态', () => {
    const { api, getWorkspaceTabByPath } = makeHarness()
    const pane = api.workspacePaneTree.value
    pane.view = 'file'
    // 无绑定文件 → ''
    expect(api.getWorkspacePaneStatus(pane)).toBe('')
    // 绑定文件但无 tab → ''
    api.workspaceSessions.value = [{ agent_id: 'agent-1', tabs: [], activeTabPath: '/a.js' }]
    api.activeWorkspaceSessionId.value = 'agent-1'
    getWorkspaceTabByPath.mockReturnValue(null)
    expect(api.getWorkspacePaneStatus(pane)).toBe('')
    // 有 tab：dirty / saved / loading / error
    getWorkspaceTabByPath.mockReturnValue({ isDirty: true })
    expect(api.getWorkspacePaneStatus(pane)).toBe('未保存修改')
    getWorkspaceTabByPath.mockReturnValue({ isDirty: false })
    expect(api.getWorkspacePaneStatus(pane)).toBe('已保存')
    getWorkspaceTabByPath.mockReturnValue({ loading: true })
    expect(api.getWorkspacePaneStatus(pane)).toBe('加载中...')
    getWorkspaceTabByPath.mockReturnValue({ error: 'boom' })
    expect(api.getWorkspacePaneStatus(pane)).toBe('boom')
  })

  it('isPaneActive：判断 pane 是否激活', () => {
    const { api } = makeHarness()
    const pane = api.workspacePaneTree.value
    expect(api.isPaneActive(pane)).toBe(true)
    const other = { id: 'pane-other', type: 'leaf', view: 'file' }
    expect(api.isPaneActive(other)).toBe(false)
  })

  it('persistWorkspacePaneLayout：未分割时不写入 localStorage', () => {
    const { api } = makeHarness()
    api.persistWorkspacePaneLayout()
    expect(localStorage.getItem('jarvis_workspace_pane_layout')).toBeNull()
  })

  it('persistWorkspacePaneLayout：分割后写入并恢复', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    api.persistWorkspacePaneLayout()
    const raw = localStorage.getItem('jarvis_workspace_pane_layout')
    expect(raw).toBeTruthy()
    const payload = JSON.parse(raw)
    expect(payload.version).toBe(2)
    expect(payload.tree.type).toBe('split')
    // 恢复到新 harness
    const { api: api2 } = makeHarness()
    api2.restoreWorkspacePaneLayout()
    expect(api2.workspacePaneCount.value).toBe(2)
    expect(api2.workspacePaneTree.value.type).toBe('split')
  })

  it('restoreWorkspacePaneLayout：脏数据回退默认单 leaf', () => {
    localStorage.setItem('jarvis_workspace_pane_layout', JSON.stringify({ version: 2, activePaneId: 'x', tree: { type: 'split', direction: 'row', ratio: 0.5, children: [{ type: 'leaf', id: 'pane-1', view: 'file' }, { type: 'leaf', id: 'pane-1', view: 'file' }] } }))
    const { api } = makeHarness()
    api.restoreWorkspacePaneLayout()
    // 重复 leaf id → 非法 → 回退默认
    expect(api.workspacePaneCount.value).toBe(1)
  })

  it('restoreWorkspacePaneLayout：非法 JSON 回退默认', () => {
    localStorage.setItem('jarvis_workspace_pane_layout', '{invalid json')
    const { api } = makeHarness()
    api.restoreWorkspacePaneLayout()
    expect(api.workspacePaneCount.value).toBe(1)
  })

  it('restoreWorkspacePaneContents：agentList 为空时不恢复', async () => {
    const { api } = makeHarness()
    await api.restoreWorkspacePaneContents()
    // 未置位，后续 agentList 就绪后可再调用
    expect(api.workspacePaneCount.value).toBe(1)
  })

  it('restoreWorkspacePaneContents：恢复 session pane', async () => {
    const { api, agentList, panels, activePanelId, workspaceSessionPanelId, switchAgent } = makeHarness()
    // 构造一个带 content 的 session leaf 树
    const tree = {
      type: 'split',
      direction: 'row',
      ratio: 0.5,
      children: [
        { type: 'leaf', id: 'pane-1', view: 'file', sessionPanelId: null, agentId: null, content: null },
        { type: 'leaf', id: 'pane-2', view: 'session', sessionPanelId: null, agentId: 'agent-1', content: { agentId: 'agent-1' } },
      ],
    }
    api.workspacePaneTree.value = tree
    api.activePaneId.value = 'pane-2'
    agentList.value = [{ agent_id: 'agent-1', name: 'Agent 1' }]
    await api.restoreWorkspacePaneContents()
    const pane = api.findWorkspacePaneById(tree, 'pane-2')
    expect(pane.view).toBe('session')
    expect(pane.sessionPanelId).toBeTruthy()
    expect(panels.value.length).toBe(1)
    expect(activePanelId.value).toBe(pane.sessionPanelId)
    expect(workspaceSessionPanelId.value).toBe(pane.sessionPanelId)
    expect(switchAgent).toHaveBeenCalled()
    // content 已清空
    expect(pane.content).toBeNull()
  })

  it('restoreWorkspacePaneContents：session Agent 不存在时降级为空 pane', async () => {
    const { api, agentList } = makeHarness()
    const tree = {
      type: 'leaf',
      id: 'pane-1',
      view: 'session',
      sessionPanelId: null,
      agentId: 'agent-gone',
      content: { agentId: 'agent-gone' },
    }
    api.workspacePaneTree.value = tree
    agentList.value = [{ agent_id: 'agent-1', name: 'Agent 1' }]
    await api.restoreWorkspacePaneContents()
    expect(tree.view).toBe('empty')
    expect(tree.agentId).toBeNull()
  })

  it('restoreWorkspacePaneContents：恢复 file pane 的 tabs', async () => {
    const { api, agentList, openWorkspaceFile, activateWorkspaceTab } = makeHarness()
    const tree = {
      type: 'leaf',
      id: 'pane-1',
      view: 'file',
      sessionPanelId: null,
      agentId: 'agent-1',
      content: { tabs: ['/a.js', '/b.js'], activePath: '/a.js', agentId: 'agent-1' },
    }
    api.workspacePaneTree.value = tree
    agentList.value = [{ agent_id: 'agent-1', name: 'Agent 1' }]
    await api.restoreWorkspacePaneContents()
    expect(openWorkspaceFile).toHaveBeenCalledTimes(2)
    expect(openWorkspaceFile).toHaveBeenCalledWith('/a.js', 'agent-1')
    expect(openWorkspaceFile).toHaveBeenCalledWith('/b.js', 'agent-1')
    expect(activateWorkspaceTab).toHaveBeenCalledWith('/a.js')
    expect(tree.content).toBeNull()
  })

  it('restoreWorkspacePaneContents：恢复 diff pane，失败降级为空', async () => {
    const { api, agentList, loadDiffForPane, gitAgentId } = makeHarness()
    const tree = {
      type: 'leaf',
      id: 'pane-1',
      view: 'diff',
      sessionPanelId: null,
      agentId: 'agent-1',
      diff: null,
      content: { commitHash: 'abc123', filePath: '/a.js', agentId: 'agent-1' },
    }
    api.workspacePaneTree.value = tree
    agentList.value = [{ agent_id: 'agent-1', name: 'Agent 1' }]
    loadDiffForPane.mockImplementation(async () => {
      const pane = api.findWorkspacePaneById(api.workspacePaneTree.value, 'pane-1')
      pane.diff = { error: 'commit not found' }
    })
    await api.restoreWorkspacePaneContents()
    expect(loadDiffForPane).toHaveBeenCalledWith('pane-1', 'abc123', '/a.js')
    // diff 拉取失败 → 降级为空 pane
    expect(tree.view).toBe('empty')
    expect(tree.diff).toBeNull()
    expect(gitAgentId.value).toBeNull()
  })

  it('restoreWorkspacePaneContents：恢复 terminal pane', async () => {
    const { api, agentList, terminalSessions, activeTerminalId } = makeHarness()
    const tree = {
      type: 'leaf',
      id: 'pane-1',
      view: 'terminal',
      sessionPanelId: null,
      agentId: null,
      content: { terminalId: 'term-1' },
    }
    api.workspacePaneTree.value = tree
    agentList.value = [{ agent_id: 'agent-1', name: 'Agent 1' }]
    terminalSessions.value = [{ terminal_id: 'term-1' }]
    await api.restoreWorkspacePaneContents()
    expect(activeTerminalId.value).toBe('term-1')
    expect(tree.view).toBe('terminal')
    expect(tree.content).toBeNull()
  })

  it('restoreWorkspacePaneContents：terminal 会话不存在时降级为空', async () => {
    const { api, agentList, terminalSessions } = makeHarness()
    const tree = {
      type: 'leaf',
      id: 'pane-1',
      view: 'terminal',
      sessionPanelId: null,
      agentId: null,
      content: { terminalId: 'term-gone' },
    }
    api.workspacePaneTree.value = tree
    agentList.value = [{ agent_id: 'agent-1', name: 'Agent 1' }]
    terminalSessions.value = []
    await api.restoreWorkspacePaneContents()
    expect(tree.view).toBe('empty')
  })

  it('setSplitWorkspaceContainerRef：注册/移除容器并触发 scheduleWorkspaceLayout', () => {
    const { api, scheduleWorkspaceLayout } = makeHarness()
    const el = { isConnected: true }
    api.setSplitWorkspaceContainerRef('pane-1', el)
    // Vue 深响应式代理 Map：get 返回代理对象，用 toStrictEqual 比较内容
    expect(api.splitWorkspaceContainerRefs.value.get('pane-1')).toStrictEqual(el)
    expect(scheduleWorkspaceLayout).toHaveBeenCalled()
    api.setSplitWorkspaceContainerRef('pane-1', null)
    expect(api.splitWorkspaceContainerRefs.value.has('pane-1')).toBe(false)
  })

  it('saveWorkspacePanelRect / workspacePanelRect 持久化', () => {
    const { api } = makeHarness()
    api.workspacePanelRect.value = { top: 10, left: 20, width: 800, height: 600 }
    api.saveWorkspacePanelRect()
    const raw = localStorage.getItem('jarvis_workspace_panel_rect')
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw).width).toBe(800)
  })

  it('usePlugins 被调用且返回符号透传', () => {
    const { api } = makeHarness()
    expect(usePluginsMock).toHaveBeenCalledTimes(1)
    // 透传符号：pluginState 是 makeHarness 内部重建的，这里通过 usePluginsMock 的返回值校验
    const returned = usePluginsMock.mock.results[0].value
    expect(api.pluginExtensions).toBe(returned.pluginExtensions)
    expect(api.pluginAdminTabs).toBe(returned.pluginAdminTabs)
    expect(api.loadPluginExtensionsForUi).toBe(returned.loadPluginExtensionsForUi)
  })

  it('workspaceSidebarView 默认 agents，可切换', () => {
    const { api } = makeHarness()
    expect(api.workspaceSidebarView.value).toBe('agents')
    api.workspaceSidebarView.value = 'git'
    expect(api.workspaceSidebarView.value).toBe('git')
  })

  it('workspaceMainView：分割后返回 file（兼容历史读点）', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    expect(api.workspaceMainView.value).toBe('file')
  })

  it('startWorkspacePaneResize：拖拽调整 split ratio', () => {
    const { api, clamp } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const splitNode = api.workspacePaneTree.value
    const event = {
      currentTarget: { parentElement: { getBoundingClientRect: () => ({ width: 1000, height: 600 }) } },
      clientX: 500,
      clientY: 0,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    }
    api.startWorkspacePaneResize(event, splitNode)
    // 模拟 mousemove：clientX 600 → ratio 0.5 + 100/1000 = 0.6
    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 600 }))
    expect(splitNode.ratio).toBeCloseTo(0.6, 5)
    // 模拟 mouseup：结束拖拽，ratio 保持不变
    document.dispatchEvent(new MouseEvent('mouseup'))
    // 拖拽结束后再 mousemove 不应再改 ratio（上下文已清空）
    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 800 }))
    expect(splitNode.ratio).toBeCloseTo(0.6, 5)
  })
})
