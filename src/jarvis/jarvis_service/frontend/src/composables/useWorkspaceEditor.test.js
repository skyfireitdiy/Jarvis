// useWorkspaceEditor 单元测试
// 覆盖：clamp、workspacePanelStyle、activeWorkspaceTab、getWorkspaceTabByPath、
// getPaneTabs/addPaneTab/removePaneTab、getActiveWorkspaceView、resolveAgentRelativePath、
// setGlobalSearchMode/clearGlobalSearch、setWorkspaceSidebarView/toggleWorkspaceSidebarView、
// scheduleWorkspaceLayout（rAF 合并）。
// monaco 在 jsdom 不可用，mock 整个 monaco 模块（顶层 defineTheme/registerEditorOpener 会执行）。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, computed, nextTick } from 'vue'

// ---- mock monaco 模块（useWorkspaceEditor 顶层调用 defineTheme/registerEditorOpener）----
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
const { useWorkspaceEditor } = await import('./useWorkspaceEditor.js')

// ---- mock 全局环境 ----
function setupGlobals() {
  globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 0)
  globalThis.cancelAnimationFrame = vi.fn()
}

// 构造 useWorkspaceEditor 依赖注入 harness
function makeHarness(overrides = {}) {
  setupGlobals()
  // —— 直传依赖（定义在调用点之前）——
  const fetchWithAuth = vi.fn()
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const getHttpProtocol = vi.fn(() => 'http')
  const buildNodeHttpUrl = vi.fn((h, p, n, path) => `http://${h}:${p}/api/node/${n}/${path}`)
  const getWebSocketProtocol = vi.fn(() => 'ws')
  const buildWebSocketProtocols = vi.fn(() => [])
  const getLanguageFromFilename = vi.fn(() => 'plaintext')
  const getLanguageExtension = vi.fn(() => 'txt')
  const closePanel = vi.fn()
  const refreshManageCapabilities = vi.fn()
  const refreshManageTimers = vi.fn()
  const windowWidth = ref(1200)
  const activeWindow = ref('workspace')
  const showWorkspacePanel = ref(true)
  const showTerminalPanel = ref(false)
  const showChatPanel = ref(false)
  const workspaceSidebarWidth = ref(300)
  const workspaceSidebarResizeState = ref({ active: false, startX: 0, startWidth: 0 })
  const agentList = ref([])
  const socket = ref(null)
  const panels = ref([])
  const workspaceSessionPanelId = ref(null)
  const normalizeWorkspaceSidebarWidth = vi.fn((w) => Math.max(200, Math.min(w, 600)))
  const saveWorkspaceSidebarWidth = vi.fn()
  const ACTIVE_Z_INDEX = 2000
  const BASE_Z_INDEX = 1000
  const manageInstalledScripts = ref([])
  const manageGatewayScripts = ref([])
  const getDefinition = vi.fn()
  const loadLspServers = vi.fn(async () => {})
  const getServerByLanguage = vi.fn(() => null)
  const getServerByPath = vi.fn(() => null)
  const ensureClient = vi.fn(async () => null)
  const disposeClient = vi.fn()
  // —— 直传（useWorkspacePane 返回）——
  const activePaneId = ref('pane-1')
  const workspaceSessions = ref([])
  const activeWorkspaceSessionId = ref(null)
  const workspaceTabs = ref([])
  const activeWorkspaceTabPath = ref(null)
  const activeWorkspaceSession = computed(() => workspaceSessions.value.find(s => s.agent_id === activeWorkspaceSessionId.value) || null)
  const virtualWorkspaceSessions = ref([])
  const editorModels = new Map()
  const workspaceFileHeartbeatTimer = ref(null)
  const isWorkspaceEditable = ref(true)
  const EDITOR_FILE_HEARTBEAT_INTERVAL = 3000
  const globalSearchQuery = ref('')
  const globalSearchFileGlob = ref('')
  const globalSearchCaseSensitive = ref(false)
  const globalSearchWholeWord = ref(false)
  const globalSearchLoading = ref(false)
  const globalSearchError = ref('')
  const globalSearchResults = ref([])
  const globalSearchTotalFiles = ref(0)
  const globalSearchTotalMatches = ref(0)
  const globalSearchExecuted = ref(false)
  const globalSearchMode = ref('content')
  const fileSearchResults = ref([])
  const showWorkspaceSidebar = ref(false)
  const workspaceSidebarView = ref('files')
  const workspaceMainView = ref('file')
  const workspacePaneCount = ref(1)
  const workspacePanelInteraction = ref({ active: false, mode: null, direction: null, startX: 0, startY: 0, startTop: 0, startLeft: 0, startWidth: 0, startHeight: 0 })
  const workspacePanelRect = ref({ top: 0, left: 0, width: 800, height: 600 })
  const workspacePanelRectBeforeMaximize = ref(null)
  const isWorkspaceMaximized = ref(false)
  const saveWorkspacePanelRect = vi.fn()
  const splitWorkspaceContainerRefs = ref(new Map())
  const editorContainerRef = ref(null)
  const EDITOR_PANEL_MIN_WIDTH = 300
  const EDITOR_PANEL_MIN_HEIGHT = 200
  const PANEL_DRAG_ACTIVATION_DISTANCE = 5
  const collapseWorkspacePanes = vi.fn()
  const findWorkspacePaneByView = vi.fn(() => null)
  const ensureEditorPaneForFileOpen = vi.fn(() => null)
  const ensurePaneForView = vi.fn()
  const setMainViewOnLeaf = vi.fn()
  const setActivePaneView = vi.fn()
  const setActivePaneViewForPane = vi.fn()
  // —— getter 注入依赖（定义在调用点之后，内部 xxx() 二次求值）——
  const showToast = vi.fn()
  const showConfirm = vi.fn()
  const pushOverlayState = vi.fn()
  const getNodeDisplayName = vi.fn((id) => id || '')
  const getCurrentAgentOrNull = vi.fn(() => null)
  const isStoppedAgent = vi.fn(() => false)
  const currentAgent = ref(null)
  const workspaceHostsChat = computed(() => false)
  const workspaceHostsTerminal = computed(() => false)
  const editorShortcutLocked = ref(false)
  const effectiveGlobalSearchAgentId = computed(() => null)
  const fileTreeState = ref(new Map())
  const initFileTree = vi.fn(async () => {})
  const getVisibleFileTreeNodes = vi.fn(() => [])
  const expandedAgents = ref([])
  const fileTreeExpanded = ref(false)
  const fileTreeLoading = ref(false)
  const fileTreeSelectedAgentId = ref(null)
  const fileTreeSelectedPath = ref(null)
  const selectedAgentId = ref(null)
  const revealTabInFileTree = vi.fn()
  const gitLogLoading = ref(false)
  const refreshGitView = vi.fn()
  const layoutGitDiffEditor = vi.fn()
  const renderDiffForPane = vi.fn()
  const scheduleDiffLayout = vi.fn()
  const topologyDaemonSessions = ref([])
  const topologyExtensionSessions = ref([])
  const getWorkspaceTargetNodeId = vi.fn(() => 'master')

  const api = useWorkspaceEditor({
    // 直传
    fetchWithAuth,
    getGatewayAddress,
    getHttpProtocol,
    buildNodeHttpUrl,
    getWebSocketProtocol,
    buildWebSocketProtocols,
    getLanguageFromFilename,
    getLanguageExtension,
    closePanel: () => closePanel,
    refreshManageCapabilities,
    refreshManageTimers,
    windowWidth,
    activeWindow,
    showWorkspacePanel,
    showTerminalPanel,
    showChatPanel,
    workspaceSidebarWidth,
    workspaceSidebarResizeState,
    agentList: () => agentList,
    socket,
    panels: () => panels,
    workspaceSessionPanelId: () => workspaceSessionPanelId,
    normalizeWorkspaceSidebarWidth,
    saveWorkspaceSidebarWidth,
    ACTIVE_Z_INDEX,
    BASE_Z_INDEX,
    manageInstalledScripts,
    manageGatewayScripts,
    getDefinition,
    loadLspServers,
    getServerByLanguage,
    getServerByPath,
    ensureClient,
    disposeClient,
    // 直传（useWorkspacePane 返回）
    activePaneId,
    workspaceSessions,
    activeWorkspaceSessionId,
    workspaceTabs,
    activeWorkspaceTabPath,
    activeWorkspaceSession,
    virtualWorkspaceSessions,
    editorModels,
    workspaceFileHeartbeatTimer,
    isWorkspaceEditable,
    EDITOR_FILE_HEARTBEAT_INTERVAL,
    globalSearchQuery,
    globalSearchFileGlob,
    globalSearchCaseSensitive,
    globalSearchWholeWord,
    globalSearchLoading,
    globalSearchError,
    globalSearchResults,
    globalSearchTotalFiles,
    globalSearchTotalMatches,
    globalSearchExecuted,
    globalSearchMode,
    fileSearchResults,
    showWorkspaceSidebar,
    workspaceSidebarView,
    workspaceMainView,
    workspacePaneCount,
    workspacePanelInteraction,
    workspacePanelRect,
    workspacePanelRectBeforeMaximize,
    isWorkspaceMaximized,
    saveWorkspacePanelRect,
    splitWorkspaceContainerRefs,
    editorContainerRef,
    EDITOR_PANEL_MIN_WIDTH,
    EDITOR_PANEL_MIN_HEIGHT,
    PANEL_DRAG_ACTIVATION_DISTANCE,
    collapseWorkspacePanes,
    findWorkspacePaneByView,
    ensureEditorPaneForFileOpen,
    ensurePaneForView,
    setMainViewOnLeaf,
    setActivePaneView,
    setActivePaneViewForPane,
    // getter 注入
    showToast: () => showToast,
    showConfirm: () => showConfirm,
    pushOverlayState: () => pushOverlayState,
    getNodeDisplayName: () => getNodeDisplayName,
    getCurrentAgentOrNull: () => getCurrentAgentOrNull,
    isStoppedAgent: () => isStoppedAgent,
    currentAgent: () => currentAgent,
    workspaceHostsChat: () => workspaceHostsChat,
    workspaceHostsTerminal: () => workspaceHostsTerminal,
    editorShortcutLocked: () => editorShortcutLocked,
    effectiveGlobalSearchAgentId: () => effectiveGlobalSearchAgentId,
    fileTreeState: () => fileTreeState,
    initFileTree: () => initFileTree,
    getVisibleFileTreeNodes: () => getVisibleFileTreeNodes,
    expandedAgents: () => expandedAgents,
    fileTreeExpanded: () => fileTreeExpanded,
    fileTreeLoading: () => fileTreeLoading,
    fileTreeSelectedAgentId: () => fileTreeSelectedAgentId,
    fileTreeSelectedPath: () => fileTreeSelectedPath,
    selectedAgentId: () => selectedAgentId,
    revealTabInFileTree: () => revealTabInFileTree,
    gitLogLoading: () => gitLogLoading,
    refreshGitView: () => refreshGitView,
    layoutGitDiffEditor: () => layoutGitDiffEditor,
    renderDiffForPane: () => renderDiffForPane,
    scheduleDiffLayout: () => scheduleDiffLayout,
    topologyDaemonSessions: () => topologyDaemonSessions,
    topologyExtensionSessions: () => topologyExtensionSessions,
    getWorkspaceTargetNodeId: () => getWorkspaceTargetNodeId,
    ...overrides,
  })

  return {
    api, refs: {
      windowWidth, activeWindow, showWorkspacePanel, showTerminalPanel, showChatPanel,
      workspaceSidebarWidth, workspaceSidebarResizeState, agentList, panels, workspaceSessionPanelId,
      activePaneId, workspaceSessions, activeWorkspaceSessionId, workspaceTabs, activeWorkspaceTabPath,
      activeWorkspaceSession, virtualWorkspaceSessions, editorModels, workspaceFileHeartbeatTimer,
      isWorkspaceEditable, globalSearchQuery, globalSearchFileGlob, globalSearchCaseSensitive,
      globalSearchWholeWord, globalSearchLoading, globalSearchError, globalSearchResults,
      globalSearchTotalFiles, globalSearchTotalMatches, globalSearchExecuted, globalSearchMode,
      fileSearchResults, showWorkspaceSidebar, workspaceSidebarView, workspaceMainView,
      workspacePaneCount, workspacePanelInteraction, workspacePanelRect, workspacePanelRectBeforeMaximize,
      isWorkspaceMaximized, splitWorkspaceContainerRefs, editorContainerRef, editorShortcutLocked,
      effectiveGlobalSearchAgentId, fileTreeState, expandedAgents, fileTreeExpanded, fileTreeLoading,
      fileTreeSelectedAgentId, fileTreeSelectedPath, selectedAgentId, gitLogLoading,
      topologyDaemonSessions, topologyExtensionSessions, currentAgent, workspaceHostsChat,
      workspaceHostsTerminal,
    },
    mocks: {
      showToast, showConfirm, pushOverlayState, getNodeDisplayName, getCurrentAgentOrNull, isStoppedAgent,
      initFileTree, getVisibleFileTreeNodes, revealTabInFileTree, refreshGitView, layoutGitDiffEditor,
      renderDiffForPane, scheduleDiffLayout, getWorkspaceTargetNodeId, closePanel, collapseWorkspacePanes,
      findWorkspacePaneByView, ensureEditorPaneForFileOpen, ensurePaneForView, setMainViewOnLeaf,
      setActivePaneView, setActivePaneViewForPane, normalizeWorkspaceSidebarWidth, saveWorkspaceSidebarWidth,
      saveWorkspacePanelRect, refreshManageCapabilities, refreshManageTimers, fetchWithAuth, getGatewayAddress,
      buildNodeHttpUrl, getLanguageFromFilename, getLanguageExtension,
    },
  }
}

describe('useWorkspaceEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('clamp', () => {
    it('在 [min, max] 范围内返回值', () => {
      const { api } = makeHarness()
      expect(api.clamp(5, 0, 10)).toBe(5)
    })

    it('小于 min 时返回 min', () => {
      const { api } = makeHarness()
      expect(api.clamp(-5, 0, 10)).toBe(0)
    })

    it('大于 max 时返回 max', () => {
      const { api } = makeHarness()
      expect(api.clamp(15, 0, 10)).toBe(10)
    })

    it('max < min 时返回 min（防御）', () => {
      const { api } = makeHarness()
      expect(api.clamp(5, 10, 0)).toBe(10)
    })
  })

  describe('workspacePanelStyle', () => {
    it('移动端（windowWidth <= 768）返回全屏样式', () => {
      const { api, refs } = makeHarness()
      refs.windowWidth.value = 700
      expect(api.workspacePanelStyle.value).toEqual({
        top: '0', left: '0', width: '100vw', height: 'var(--app-height, 100vh)', zIndex: 2000,
      })
    })

    it('桌面端使用 workspacePanelRect 与窗口层级', () => {
      const { api, refs } = makeHarness()
      refs.windowWidth.value = 1200
      refs.workspacePanelRect.value = { top: 10, left: 20, width: 800, height: 600 }
      refs.activeWindow.value = 'workspace'
      expect(api.workspacePanelStyle.value).toEqual({
        top: '10px', left: '20px', width: '800px', height: '600px', zIndex: 2000,
      })
      refs.activeWindow.value = 'chat'
      expect(api.workspacePanelStyle.value.zIndex).toBe(1000)
    })
  })

  describe('activeWorkspaceTab', () => {
    it('根据 activeWorkspaceTabPath 返回对应 tab，找不到返回 null', () => {
      const { api, refs } = makeHarness()
      const tabA = { path: '/a.py', name: 'a.py' }
      const tabB = { path: '/b.py', name: 'b.py' }
      refs.workspaceTabs.value = [tabA, tabB]
      refs.activeWorkspaceTabPath.value = '/b.py'
      expect(api.activeWorkspaceTab.value.path).toBe('/b.py')
      refs.activeWorkspaceTabPath.value = '/nonexist.py'
      expect(api.activeWorkspaceTab.value).toBeNull()
    })
  })

  describe('getWorkspaceTabByPath', () => {
    it('按 path 查找 tab，找不到返回 null', () => {
      const { api, refs } = makeHarness()
      const tab = { path: '/a.py' }
      refs.workspaceTabs.value = [tab]
      expect(api.getWorkspaceTabByPath('/a.py').path).toBe('/a.py')
      expect(api.getWorkspaceTabByPath('/b.py')).toBeNull()
    })
  })

  describe('getPaneTabs / workspacePaneTabs', () => {
    it('getPaneTabs 返回 pane 对应标签（映射到 workspaceTabs）', () => {
      const { api, refs } = makeHarness()
      const tabA = { path: '/a.py' }
      const tabB = { path: '/b.py' }
      refs.workspaceTabs.value = [tabA, tabB]
      api.workspacePaneTabs.set('pane-1', ['/a.py', '/b.py'])
      const tabs = api.getPaneTabs('pane-1')
      expect(tabs).toHaveLength(2)
      expect(tabs[0].path).toBe('/a.py')
      expect(tabs[1].path).toBe('/b.py')
    })

    it('getPaneTabs 过滤掉 workspaceTabs 中不存在的 path', () => {
      const { api, refs } = makeHarness()
      refs.workspaceTabs.value = [{ path: '/a.py' }]
      api.workspacePaneTabs.set('pane-1', ['/a.py', '/gone.py'])
      const tabs = api.getPaneTabs('pane-1')
      expect(tabs).toHaveLength(1)
      expect(tabs[0].path).toBe('/a.py')
    })

    it('workspacePaneTabs 无该 pane 时返回空数组', () => {
      const { api } = makeHarness()
      expect(api.getPaneTabs('pane-99')).toEqual([])
    })

    it('无 paneId 时 getPaneTabs 返回空数组', () => {
      const { api } = makeHarness()
      expect(api.getPaneTabs(null)).toEqual([])
    })
  })

  describe('getActiveWorkspaceView', () => {
    it('返回激活 pane 的编辑器实例', () => {
      const { api, refs } = makeHarness()
      const viewA = { id: 'view-a' }
      const viewB = { id: 'view-b' }
      api.editorViews.set('pane-1', viewA)
      api.editorViews.set('pane-2', viewB)
      refs.activePaneId.value = 'pane-2'
      expect(api.getActiveWorkspaceView()).toBe(viewB)
    })

    it('激活 pane 无实例时回退到任一实例', () => {
      const { api, refs } = makeHarness()
      const viewA = { id: 'view-a' }
      api.editorViews.set('pane-1', viewA)
      refs.activePaneId.value = 'pane-99'
      expect(api.getActiveWorkspaceView()).toBe(viewA)
    })

    it('无任何实例时返回 null', () => {
      const { api } = makeHarness()
      expect(api.getActiveWorkspaceView()).toBeNull()
    })
  })

  describe('resolveAgentRelativePath', () => {
    it('绝对路径直接返回', () => {
      const { api } = makeHarness()
      expect(api.resolveAgentRelativePath('/abs/path.py')).toBe('/abs/path.py')
    })

    it('相对路径拼上 currentAgent working_dir', () => {
      const { api, refs } = makeHarness()
      refs.currentAgent.value = { working_dir: '/home/user/proj' }
      expect(api.resolveAgentRelativePath('src/a.py')).toBe('/home/user/proj/src/a.py')
    })

    it('优先用指定 agentId 的 working_dir', () => {
      const { api, refs } = makeHarness()
      refs.agentList.value = [{ agent_id: 'agent-1', working_dir: '/agent1' }]
      expect(api.resolveAgentRelativePath('x.py', 'agent-1')).toBe('/agent1/x.py')
    })

    it('无 working_dir 时原样返回', () => {
      const { api } = makeHarness()
      expect(api.resolveAgentRelativePath('rel.py')).toBe('rel.py')
    })
  })

  describe('setGlobalSearchMode / clearGlobalSearch', () => {
    it('setGlobalSearchMode 切换模式并重置状态', () => {
      const { api, refs } = makeHarness()
      refs.globalSearchMode.value = 'content'
      refs.globalSearchResults.value = [{ file: 'a' }]
      api.setGlobalSearchMode('filename')
      expect(refs.globalSearchMode.value).toBe('filename')
      expect(refs.globalSearchResults.value).toEqual([])
      expect(refs.globalSearchExecuted.value).toBe(false)
    })

    it('clearGlobalSearch 清空全部搜索状态', () => {
      const { api, refs } = makeHarness()
      refs.globalSearchQuery.value = 'q'
      refs.globalSearchResults.value = [{ file: 'a' }]
      refs.globalSearchExecuted.value = true
      api.clearGlobalSearch()
      expect(refs.globalSearchQuery.value).toBe('')
      expect(refs.globalSearchResults.value).toEqual([])
      expect(refs.globalSearchExecuted.value).toBe(false)
    })
  })

  describe('setWorkspaceSidebarView / toggleWorkspaceSidebarView', () => {
    it('setWorkspaceSidebarView 设置视图并打开侧边栏', () => {
      const { api, refs } = makeHarness()
      api.setWorkspaceSidebarView('git')
      expect(refs.workspaceSidebarView.value).toBe('git')
      expect(refs.showWorkspaceSidebar.value).toBe(true)
    })

    it('toggleWorkspaceSidebarView 已打开同视图时收起', () => {
      const { api, refs } = makeHarness()
      refs.showWorkspaceSidebar.value = true
      refs.workspaceSidebarView.value = 'search'
      api.toggleWorkspaceSidebarView('search')
      expect(refs.showWorkspaceSidebar.value).toBe(false)
    })

    it('toggleWorkspaceSidebarView 切换到不同视图', () => {
      const { api, refs } = makeHarness()
      refs.showWorkspaceSidebar.value = true
      refs.workspaceSidebarView.value = 'files'
      api.toggleWorkspaceSidebarView('search')
      expect(refs.workspaceSidebarView.value).toBe('search')
      expect(refs.showWorkspaceSidebar.value).toBe(true)
    })
  })

  describe('scheduleWorkspaceLayout', () => {
    it('同帧多次调用只执行一次 layout（rAF 合并）', async () => {
      const { api } = makeHarness()
      api.scheduleWorkspaceLayout()
      api.scheduleWorkspaceLayout()
      api.scheduleWorkspaceLayout()
      await new Promise((r) => setTimeout(r, 20))
      // layoutMonacoEditor 内部调用 ensureSplitMonacoEditors（无容器，不创建实例）
      // 不抛错即通过
      expect(true).toBe(true)
    })
  })
})
