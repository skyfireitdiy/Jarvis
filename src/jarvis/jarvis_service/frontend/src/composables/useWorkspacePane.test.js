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
    pluginPaneViews: null,
    pluginSidebarTitle: vi.fn((view) => ''),
    pluginToolPanelTitle: vi.fn((view) => ''),
    pluginPaneTitle: vi.fn((view) => ''),
    WORKSPACE_SIDEBAR_TITLES: {},
    workspaceSidebarTitle: null,
    loadPluginExtensionsForUi: vi.fn(async () => {}),
    resolvePluginExtensionComponent: vi.fn(() => null),
    isPluginSidebarView: vi.fn(() => false),
    isPluginToolView: vi.fn(() => false),
    isPluginPaneView: vi.fn(() => false),
    pluginSidebarCompCache: new Map(),
    activePluginSidebarComp: null,
    activePluginToolPanelComp: null,
    resolvePluginPaneComp: vi.fn(() => null),
    activePluginPaneComp: null,
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
    pluginPaneViews: computed(() => pluginState.pluginExtensions.value.filter(e => e.extType === 'pane_views')),
    workspaceSidebarTitle: computed(() => ''),
    activePluginSidebarComp: computed(() => null),
    activePluginToolPanelComp: computed(() => null),
    activePluginPaneComp: computed(() => null),
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

  it('activateWorkspacePane：激活 session pane 同步 activePanelId，即使 activePaneId 已指向该 pane（Issue #160 回归）', () => {
    const { api, activePanelId, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }]
    // 构造 session pane 承载 panel-1
    api.setActivePaneView('session', 'panel-1')
    // 首次激活：同步 activePanelId
    api.activateWorkspacePane(rootId)
    expect(activePanelId.value).toBe('panel-1')
    // 模拟其它路径把 activePanelId 改乱（点击面板只更新 activePaneId 不同步 activePanelId 的旧缺陷）
    activePanelId.value = 'other-panel'
    // 再次激活同一 pane（触发早退路径），activePanelId 仍须被同步回 panel-1
    api.activateWorkspacePane(rootId)
    expect(activePanelId.value).toBe('panel-1')
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

  it('ensurePaneForView：plugin-pane 视图 host 单例复用', () => {
    const { api } = makeHarness()
    // 模拟 isPluginPaneView 识别 plugin-pane: 前缀
    pluginStateShell.isPluginPaneView.mockImplementation((view) => typeof view === 'string' && view.startsWith('plugin-pane:'))
    const id1 = api.ensurePaneForView('plugin-pane:p1')
    expect(id1).toBeTruthy()
    // 再次打开同一插件 pane：复用同一 pane，不新增
    const id2 = api.ensurePaneForView('plugin-pane:p1')
    expect(id2).toBe(id1)
    expect(api.workspacePaneCount.value).toBe(1)
    // 不同 id 的插件 pane：分割新建
    const id3 = api.ensurePaneForView('plugin-pane:p2')
    expect(id3).toBeTruthy()
    expect(id3).not.toBe(id1)
    expect(api.workspacePaneCount.value).toBe(2)
  })

  it('getWorkspacePaneTitle：plugin-pane 视图标题', () => {
    const { api } = makeHarness()
    const pane = api.workspacePaneTree.value
    pane.view = 'plugin-pane:p1'
    // 未找到插件 → 回退通用文案
    expect(api.getWorkspacePaneTitle(pane)).toBe('插件面板')
    // 找到插件 → 返回声明的 title
    pluginStateShell.pluginPaneTitle.mockReturnValue('我的插件面板')
    expect(api.getWorkspacePaneTitle(pane)).toBe('我的插件面板')
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
    expect(payload.version).toBe(3)
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

  it('restoreWorkspacePaneLayout：plugin-pane 视图布局恢复', () => {
    // 分割树：一个 file leaf + 一个 plugin-pane leaf
    localStorage.setItem('jarvis_workspace_pane_layout', JSON.stringify({
      version: 3,
      activePaneId: 'pane-2',
      tree: {
        type: 'split', direction: 'row', ratio: 0.5,
        children: [
          { type: 'leaf', id: 'pane-1', view: 'file' },
          { type: 'leaf', id: 'pane-2', view: 'plugin-pane:p1' },
        ],
      },
    }))
    const { api } = makeHarness()
    api.restoreWorkspacePaneLayout()
    expect(api.workspacePaneCount.value).toBe(2)
    // 找到 plugin-pane leaf
    const pluginPane = api.findWorkspacePaneByView('plugin-pane:p1')
    expect(pluginPane).toBeTruthy()
    expect(pluginPane.view).toBe('plugin-pane:p1')
  })

  it('restoreWorkspacePaneLayout：重复 plugin-pane 同 id 视为非法回退', () => {
    // 两个 leaf 都是 plugin-pane:p1（违反 host 单例）→ 非法 → 回退默认
    localStorage.setItem('jarvis_workspace_pane_layout', JSON.stringify({
      version: 3,
      activePaneId: 'pane-1',
      tree: {
        type: 'split', direction: 'row', ratio: 0.5,
        children: [
          { type: 'leaf', id: 'pane-1', view: 'plugin-pane:p1' },
          { type: 'leaf', id: 'pane-2', view: 'plugin-pane:p1' },
        ],
      },
    }))
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

  // ===== session 多 tab（Issue #287）=====
  it('addSessionTabToPane：非 session pane 返回 false', () => {
    const { api } = makeHarness()
    const root = api.workspacePaneTree.value
    expect(api.addSessionTabToPane(root, 'panel-1')).toBe(false)
  })

  it('addSessionTabToPane：向 session pane 追加 tab，激活新 tab 并同步兼容字段', () => {
    const { api, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }]
    api.setActivePaneView('session', 'panel-1')
    const pane = api.workspacePaneTree.value
    expect(pane.sessionPanelIds).toEqual(['panel-1'])
    // 追加第二个 tab
    panels.value.push({ id: 'panel-2', agentId: 'agent-2' })
    expect(api.addSessionTabToPane(pane, 'panel-2')).toBe(true)
    expect(pane.sessionPanelIds).toEqual(['panel-1', 'panel-2'])
    expect(pane.activeSessionPanelId).toBe('panel-2')
    expect(pane.sessionPanelId).toBe('panel-2') // 兼容字段同步
    // 重复追加不生效
    expect(api.addSessionTabToPane(pane, 'panel-2')).toBe(true)
    expect(pane.sessionPanelIds).toEqual(['panel-1', 'panel-2'])
  })

  it('activateSessionTabInPane：激活已有 tab，忽略不存在的 tab', () => {
    const { api, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }, { id: 'panel-2', agentId: 'agent-2' }]
    api.setActivePaneView('session', 'panel-1')
    const pane = api.workspacePaneTree.value
    api.addSessionTabToPane(pane, 'panel-2')
    expect(api.activateSessionTabInPane(pane, 'panel-1')).toBe(true)
    expect(pane.activeSessionPanelId).toBe('panel-1')
    expect(pane.sessionPanelId).toBe('panel-1')
    expect(api.activateSessionTabInPane(pane, 'panel-gone')).toBe(false)
    expect(pane.activeSessionPanelId).toBe('panel-1')
  })

  it('closeSessionTabInPane：关闭非激活 tab 不影响激活 tab', () => {
    const { api, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }, { id: 'panel-2', agentId: 'agent-2' }]
    api.setActivePaneView('session', 'panel-1')
    const pane = api.workspacePaneTree.value
    api.addSessionTabToPane(pane, 'panel-2')
    // 激活 panel-2，关闭 panel-1（非激活）
    api.activateSessionTabInPane(pane, 'panel-2')
    api.closeSessionTabInPane(pane, 'panel-1')
    expect(pane.sessionPanelIds).toEqual(['panel-2'])
    expect(pane.activeSessionPanelId).toBe('panel-2')
    expect(pane.view).toBe('session')
  })

  it('closeSessionTabInPane：关闭激活 tab 自动切到相邻 tab', () => {
    const { api, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }, { id: 'panel-2', agentId: 'agent-2' }]
    api.setActivePaneView('session', 'panel-1')
    const pane = api.workspacePaneTree.value
    api.addSessionTabToPane(pane, 'panel-2')
    // 激活 panel-1，关闭它 → 切到 panel-2
    api.closeSessionTabInPane(pane, 'panel-1')
    expect(pane.sessionPanelIds).toEqual(['panel-2'])
    expect(pane.activeSessionPanelId).toBe('panel-2')
    expect(pane.sessionPanelId).toBe('panel-2')
  })

  it('closeSessionTabInPane：全部关闭后 pane 清成 empty', () => {
    const { api, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }]
    api.setActivePaneView('session', 'panel-1')
    const pane = api.workspacePaneTree.value
    api.closeSessionTabInPane(pane, 'panel-1')
    expect(pane.view).toBe('empty')
    expect(pane.sessionPanelIds).toEqual([])
    expect(pane.activeSessionPanelId).toBeNull()
    expect(pane.sessionPanelId).toBeNull()
    expect(pane.agentId).toBeNull()
  })

  it('setActivePaneViewForPane：session pane 上追加 tab（不关闭旧 panel）', () => {
    const { api, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }, { id: 'panel-2', agentId: 'agent-2' }]
    api.setActivePaneView('session', 'panel-1')
    const pane = api.workspacePaneTree.value
    // 在已是 session 的 pane 上再放 panel-2 → 追加 tab
    expect(api.setActivePaneViewForPane(pane, 'session', 'panel-2')).toBe(true)
    expect(pane.sessionPanelIds).toEqual(['panel-1', 'panel-2'])
    expect(pane.activeSessionPanelId).toBe('panel-2')
  })

  it('setActivePaneViewForPane：从 session 切到 file 清空多 tab 字段', () => {
    const { api, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }]
    api.setActivePaneView('session', 'panel-1')
    const pane = api.workspacePaneTree.value
    api.setActivePaneViewForPane(pane, 'file')
    expect(pane.view).toBe('file')
    expect(pane.sessionPanelIds).toEqual([])
    expect(pane.activeSessionPanelId).toBeNull()
    expect(pane.sessionPanelId).toBeNull()
  })

  it('paneSessionPanelIds：兼容单 tab 的 sessionPanelId 字段', () => {
    const { api, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }]
    api.setActivePaneView('session', 'panel-1')
    const pane = api.workspacePaneTree.value
    // 模拟旧结构：只有 sessionPanelId，无 sessionPanelIds
    delete pane.sessionPanelIds
    delete pane.activeSessionPanelId
    expect(api.paneSessionPanelIds(pane)).toEqual(['panel-1'])
    expect(api.paneActiveSessionPanelId(pane)).toBe('panel-1')
  })

  it('persistWorkspacePaneLayout：version 3 序列化 session 多 tab agentIds', () => {
    const { api, panels } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }, { id: 'panel-2', agentId: 'agent-2' }]
    api.splitWorkspacePane(rootId, 'row')
    // 左 pane 承载两个 tab
    api.setActivePaneViewForPane(api.workspacePaneTree.value.children[0], 'session', 'panel-1')
    api.setActivePaneViewForPane(api.workspacePaneTree.value.children[0], 'session', 'panel-2')
    api.persistWorkspacePaneLayout()
    const raw = localStorage.getItem('jarvis_workspace_pane_layout')
    expect(raw).toBeTruthy()
    const parsed = JSON.parse(raw)
    expect(parsed.version).toBe(3)
    // 找到 session leaf 的 content.agentIds
    const sessionLeaf = parsed.tree.children.find(c => c.view === 'session')
    expect(sessionLeaf.content.agentIds).toEqual(['agent-1', 'agent-2'])
  })

  it('persistWorkspacePaneLayout：未分割但唯一 leaf 是 session 时也写入（多 tab 刷新恢复）', () => {
    const { api, panels } = makeHarness()
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }, { id: 'panel-2', agentId: 'agent-2' }]
    // 未分割：唯一 leaf 直接承载两个 tab
    api.setActivePaneView('session', 'panel-1')
    const pane = api.workspacePaneTree.value
    api.addSessionTabToPane(pane, 'panel-2')
    api.persistWorkspacePaneLayout()
    const raw = localStorage.getItem('jarvis_workspace_pane_layout')
    expect(raw).toBeTruthy()
    const parsed = JSON.parse(raw)
    expect(parsed.version).toBe(3)
    expect(parsed.tree.type).toBe('leaf')
    expect(parsed.tree.view).toBe('session')
    expect(parsed.tree.content.agentIds).toEqual(['agent-1', 'agent-2'])
  })

  it('persistWorkspacePaneLayout：未分割且非 session 时不写入', () => {
    const { api } = makeHarness()
    api.persistWorkspacePaneLayout()
    expect(localStorage.getItem('jarvis_workspace_pane_layout')).toBeNull()
  })

  it('restoreWorkspacePaneLayout：恢复未分割单 leaf session 布局', async () => {
    const { api, agentList, panels } = makeHarness()
    const layout = {
      version: 3,
      activePaneId: 'pane-1',
      tree: { type: 'leaf', id: 'pane-1', view: 'session', sessionPanelId: null, agentId: 'agent-1', content: { agentIds: ['agent-1', 'agent-2'] } },
    }
    localStorage.setItem('jarvis_workspace_pane_layout', JSON.stringify(layout))
    api.restoreWorkspacePaneLayout()
    expect(api.workspacePaneTree.value.type).toBe('leaf')
    expect(api.workspacePaneTree.value.view).toBe('session')
    agentList.value = [
      { agent_id: 'agent-1', name: 'Agent 1' },
      { agent_id: 'agent-2', name: 'Agent 2' },
    ]
    await api.restoreWorkspacePaneContents()
    const pane = api.workspacePaneTree.value
    expect(pane.sessionPanelIds.length).toBe(2)
    expect(panels.value.length).toBe(2)
  })

  it('restoreWorkspacePaneLayout：旧版单 agentId 迁移到多 tab agentIds', async () => {
    const { api, agentList, panels } = makeHarness()
    // 写入 version 2 旧布局：session leaf 只有 content.agentId
    const oldLayout = {
      version: 2,
      activePaneId: 'pane-2',
      tree: {
        type: 'split',
        direction: 'row',
        ratio: 0.5,
        children: [
          { type: 'leaf', id: 'pane-1', view: 'file', sessionPanelId: null, agentId: null, content: null },
          { type: 'leaf', id: 'pane-2', view: 'session', sessionPanelId: null, agentId: 'agent-1', content: { agentId: 'agent-1' } },
        ],
      },
    }
    localStorage.setItem('jarvis_workspace_pane_layout', JSON.stringify(oldLayout))
    api.restoreWorkspacePaneLayout()
    agentList.value = [{ agent_id: 'agent-1', name: 'Agent 1' }]
    await api.restoreWorkspacePaneContents()
    const pane = api.findWorkspacePaneById(api.workspacePaneTree.value, 'pane-2')
    expect(pane.view).toBe('session')
    expect(pane.sessionPanelIds).toEqual([pane.sessionPanelId])
    expect(panels.value.length).toBe(1)
    expect(panels.value[0].agentId).toBe('agent-1')
  })

  it('restoreWorkspacePaneContents：恢复多 tab session pane（agentIds 列表）', async () => {
    const { api, agentList, panels } = makeHarness()
    const tree = {
      type: 'split',
      direction: 'row',
      ratio: 0.5,
      children: [
        { type: 'leaf', id: 'pane-1', view: 'file', sessionPanelId: null, agentId: null, content: null },
        { type: 'leaf', id: 'pane-2', view: 'session', sessionPanelId: null, agentId: 'agent-1', content: { agentIds: ['agent-1', 'agent-2'] } },
      ],
    }
    api.workspacePaneTree.value = tree
    api.activePaneId.value = 'pane-2'
    agentList.value = [
      { agent_id: 'agent-1', name: 'Agent 1' },
      { agent_id: 'agent-2', name: 'Agent 2' },
    ]
    await api.restoreWorkspacePaneContents()
    const pane = api.findWorkspacePaneById(tree, 'pane-2')
    expect(pane.view).toBe('session')
    expect(pane.sessionPanelIds.length).toBe(2)
    expect(panels.value.length).toBe(2)
    // 激活第一个 tab
    expect(pane.activeSessionPanelId).toBe(pane.sessionPanelIds[0])
    expect(pane.sessionPanelId).toBe(pane.sessionPanelIds[0])
    expect(pane.content).toBeNull()
  })
  // ===== 临时折叠（隐藏）=====
  it('togglePaneCollapse：折叠记录父 split 的 side/size，pane 与内容不销毁', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const tree = api.workspacePaneTree.value
    tree.ratio = 0.3
    const collapsed = api.togglePaneCollapse(rootId)
    expect(collapsed).toBe(true)
    expect(tree.collapsed).toEqual({ side: 0, size: 0.3 })
    // leaf 仍在树中（内容不销毁），只是不可见
    expect(api.findWorkspacePaneById(tree, rootId)).toBeTruthy()
    expect(api.workspacePaneCount.value).toBe(2)
    expect(api.visibleWorkspacePaneCount.value).toBe(1)
    expect(api.isWorkspacePaneCollapsed(rootId)).toBe(true)
    expect(api.isCollapsedSide(tree, 0)).toBe(true)
    expect(api.isCollapsedSide(tree, 1)).toBe(false)
  })
  it('togglePaneCollapse：再次调用展开并恢复折叠前 ratio', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const tree = api.workspacePaneTree.value
    tree.ratio = 0.25
    api.togglePaneCollapse(rootId)
    const expanded = api.togglePaneCollapse(rootId)
    expect(expanded).toBe(false)
    expect(tree.collapsed).toBeNull()
    expect(tree.ratio).toBe(0.25)
    expect(api.visibleWorkspacePaneCount.value).toBe(2)
    // 展开后激活态交给被展开的 pane
    expect(api.activePaneId.value).toBe(rootId)
  })
  it('togglePaneCollapse：折叠激活 pane 时激活态转移到兄弟子树', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const newId = api.activePaneId.value
    expect(newId).not.toBe(rootId)
    api.togglePaneCollapse(newId)
    expect(api.activePaneId.value).toBe(rootId)
    expect(api.isWorkspacePaneCollapsed(newId)).toBe(true)
  })
  it('togglePaneCollapse：未分割（无父 split）返回 null', () => {
    const { api } = makeHarness()
    expect(api.togglePaneCollapse(api.workspacePaneTree.value.id)).toBeNull()
  })
  it('togglePaneCollapse：折叠时清除该 pane 的最大化', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const newId = api.activePaneId.value
    api.toggleMaximizeWorkspacePane(newId)
    expect(api.maximizedPaneId.value).toBe(newId)
    api.togglePaneCollapse(newId)
    expect(api.maximizedPaneId.value).toBeNull()
  })
  it('togglePaneCollapse：折叠状态持久化并在恢复后保留', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'column')
    const tree = api.workspacePaneTree.value
    tree.ratio = 0.4
    api.togglePaneCollapse(rootId)
    const payload = JSON.parse(localStorage.getItem('jarvis_workspace_pane_layout'))
    expect(payload.tree.collapsed).toEqual({ side: 0, size: 0.4 })
    const { api: api2 } = makeHarness()
    api2.restoreWorkspacePaneLayout()
    expect(api2.workspacePaneTree.value.collapsed).toEqual({ side: 0, size: 0.4 })
    expect(api2.isWorkspacePaneCollapsed(rootId)).toBe(true)
  })
  it('restoreWorkspacePaneLayout：非法 collapsed 被丢弃', () => {
    localStorage.setItem('jarvis_workspace_pane_layout', JSON.stringify({
      version: 3,
      activePaneId: 'pane-1',
      tree: {
        type: 'split',
        direction: 'row',
        ratio: 0.5,
        collapsed: { side: 5, size: 'bad' },
        children: [
          { type: 'leaf', id: 'pane-1', view: 'file' },
          { type: 'leaf', id: 'pane-2', view: 'file' },
        ],
      },
    }))
    const { api } = makeHarness()
    api.restoreWorkspacePaneLayout()
    expect(api.workspacePaneTree.value.collapsed).toBeUndefined()
    expect(api.visibleWorkspacePaneCount.value).toBe(2)
  })
  it('restoreWorkspacePaneLayout：collapsed.size 越界时 clamp 到合法区间', () => {
    localStorage.setItem('jarvis_workspace_pane_layout', JSON.stringify({
      version: 3,
      activePaneId: 'pane-1',
      tree: {
        type: 'split',
        direction: 'row',
        ratio: 0.5,
        collapsed: { side: 1, size: 0.99 },
        children: [
          { type: 'leaf', id: 'pane-1', view: 'file' },
          { type: 'leaf', id: 'pane-2', view: 'file' },
        ],
      },
    }))
    const { api } = makeHarness()
    api.restoreWorkspacePaneLayout()
    expect(api.workspacePaneTree.value.collapsed).toEqual({ side: 1, size: 0.85 })
  })
  it('expandAllCollapsedPanes：展开所有折叠区域并恢复尺寸', () => {
    const { api } = makeHarness()
    expect(api.expandAllCollapsedPanes()).toBe(false)
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const tree = api.workspacePaneTree.value
    tree.ratio = 0.2
    api.togglePaneCollapse(rootId)
    expect(api.visibleWorkspacePaneCount.value).toBe(1)
    expect(api.expandAllCollapsedPanes()).toBe(true)
    expect(tree.collapsed).toBeNull()
    expect(tree.ratio).toBe(0.2)
    expect(api.visibleWorkspacePaneCount.value).toBe(2)
  })
  it('moveActivePaneInDirection：目标区域折叠时先展开再激活', () => {
    const { api } = makeHarness()
    const leftId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(leftId, 'row')
    const rightId = api.activePaneId.value
    // 折叠右侧（激活态转移到左侧）
    api.togglePaneCollapse(rightId)
    expect(api.activePaneId.value).toBe(leftId)
    expect(api.isWorkspacePaneCollapsed(rightId)).toBe(true)
    const moved = api.moveActivePaneInDirection('right')
    expect(moved).toBe(true)
    expect(api.isWorkspacePaneCollapsed(rightId)).toBe(false)
    expect(api.activePaneId.value).toBe(rightId)
  })
  // ===== togglePaneCollapseSide：直接以 split + side 折叠（折叠条点击路径）=====
  it('togglePaneCollapseSide：嵌套 split 时折叠条点击折叠的是渲染它的 split，而非边缘 leaf 的父 split', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row') // 根：row split [pane-1, pane-2]
    const tree = api.workspacePaneTree.value
    const rightId = api.activePaneId.value // pane-2
    // 再对右侧 pane 做 column 分割 → 右侧子树成为嵌套 split（tree.children[1]）
    api.splitWorkspacePane(rightId, 'column')
    const rightSplit = tree.children[1]
    expect(rightSplit.type).toBe('split')
    expect(rightSplit.direction).toBe('column')
    // 嵌套 split：children[0] = pane-2（原 rightId），children[1] = pane-3（激活）
    const pane2Id = rightSplit.children[0].id
    const pane3Id = rightSplit.children[1].id
    expect(api.activePaneId.value).toBe(pane3Id)
    // 折叠「嵌套 split」的 side 0（pane-2 所在侧）：直接操作该 split 节点
    const result = api.togglePaneCollapseSide(rightSplit, 0)
    expect(result).toBe(true)
    expect(rightSplit.collapsed).toEqual({ side: 0, size: 0.5 })
    // 根 split 不受影响
    expect(tree.collapsed).toBeUndefined()
    // 被折叠的是 pane-2（side 0），pane-3（side 1）不受影响
    expect(api.isWorkspacePaneCollapsed(pane2Id)).toBe(true)
    expect(api.isWorkspacePaneCollapsed(pane3Id)).toBe(false)
    // 展开：恢复 ratio 并激活该侧边缘 leaf（pane-2）
    const expanded = api.togglePaneCollapseSide(rightSplit, 0)
    expect(expanded).toBe(false)
    expect(rightSplit.collapsed).toBeNull()
    expect(api.activePaneId.value).toBe(pane2Id)
  })
  it('togglePaneCollapseSide：折叠侧子树含激活 pane 时激活态转移到兄弟子树', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const tree = api.workspacePaneTree.value
    const rightId = api.activePaneId.value
    api.splitWorkspacePane(rightId, 'column')
    const rightSplit = tree.children[1]
    const pane2Id = rightSplit.children[0].id
    const pane3Id = rightSplit.children[1].id
    expect(api.activePaneId.value).toBe(pane3Id)
    // 折叠含激活 pane 的 side 1（pane-3 所在侧）→ 激活态转移到 side 0（pane-2）
    api.togglePaneCollapseSide(rightSplit, 1)
    expect(api.isWorkspacePaneCollapsed(pane3Id)).toBe(true)
    expect(api.activePaneId.value).toBe(pane2Id)
    expect(api.isWorkspacePaneCollapsed(pane2Id)).toBe(false)
  })
  it('togglePaneCollapseSide：非法参数返回 null', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const tree = api.workspacePaneTree.value
    expect(api.togglePaneCollapseSide(tree, 5)).toBeNull()
    expect(api.togglePaneCollapseSide({ type: 'leaf' }, 0)).toBeNull()
    expect(api.togglePaneCollapseSide(null, 0)).toBeNull()
  })
  it('moveActivePaneInDirection：嵌套 split 中目标侧折叠时展开的是外层 split 而非边缘 leaf 的父 split', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row') // 根 row [pane-1, pane-2]
    const tree = api.workspacePaneTree.value
    const rightId = api.activePaneId.value // pane-2
    api.splitWorkspacePane(rightId, 'column') // 右侧嵌套 column [pane-2, pane-3]
    const rightSplit = tree.children[1]
    const pane2Id = rightSplit.children[0].id
    const pane3Id = rightSplit.children[1].id
    // 折叠根 split 的右侧（side 1 = 嵌套 split 整棵子树）
    api.togglePaneCollapseSide(tree, 1)
    expect(tree.collapsed).toEqual({ side: 1, size: 0.5 })
    expect(api.isCollapsedSide(tree, 1)).toBe(true)
    // 激活态转移到根 split 左侧（pane-1）
    expect(api.activePaneId.value).toBe(rootId)
    // 向右导航：应展开「根 split 的 side 1」（而非嵌套 split 内层），并激活其边缘 leaf（pane-2）
    const moved = api.moveActivePaneInDirection('right')
    expect(moved).toBe(true)
    expect(tree.collapsed).toBeNull()
    expect(rightSplit.collapsed).toBeUndefined()
    expect(api.isWorkspacePaneCollapsed(pane2Id)).toBe(false)
    expect(api.activePaneId.value).toBe(pane2Id)
  })
  it('findEmptyWorkspacePane：能识别 view=file 但未绑定文件的空 pane（回归：仅按 empty 查找会漏掉）', () => {
    const { api, workspaceViewPanes } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const tree = api.workspacePaneTree.value
    const left = tree.children[0]
    const right = tree.children[1]
    // 左侧承载 session（非空区域）
    left.view = 'session'
    left.sessionPanelId = 'panel-1'
    // 右侧是 file 视图但未绑定文件（关闭文件后遗留的空 file pane，标题显示「空区域」）
    right.view = 'file'
    // 不应把 session pane 当空区域；应找到右侧 file 空 pane
    expect(api.findEmptyWorkspacePane()).toBe(right)
    // 一旦右侧绑定文件（进入 workspaceViewPanes），就不再是空区域
    workspaceViewPanes.set(right.id, { path: '/a.js' })
    expect(api.findEmptyWorkspacePane()).toBeNull()
  })

  it('findEmptyWorkspacePane：优先返回 view=empty 的显式空 pane，且跳过承载 session 的 pane', () => {
    const { api } = makeHarness()
    const rootId = api.workspacePaneTree.value.id
    api.splitWorkspacePane(rootId, 'row')
    const tree = api.workspacePaneTree.value
    const left = tree.children[0]
    const right = tree.children[1]
    // 两个都是 empty 时返回第一个
    expect(api.findEmptyWorkspacePane()).toBe(left)
    // 左侧设为 session 后，返回右侧 empty
    left.view = 'session'
    left.sessionPanelId = 'panel-1'
    expect(api.findEmptyWorkspacePane()).toBe(right)
  })
})
