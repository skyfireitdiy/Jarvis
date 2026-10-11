// 工作区编辑器 / 文件操作 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 10 PR-3，原 3180-5424 行），
// 保持行为完全一致：
// - 编辑器面板：workspacePanelStyle / workspacePanelRect / workspacePanelInteraction /
//   startWorkspacePanelMove / startWorkspacePanelResize / toggleWorkspaceMaximize
// - Monaco 编辑器：editorViews / workspaceViewPanes / diffEditorViews / workspacePaneTabs /
//   scheduleWorkspaceLayout / layoutMonacoEditor / remountMonacoEditor / activateWorkspaceTab /
//   openWorkspaceFile / saveWorkspaceTab / closeWorkspaceTab / tabContextMenu
// - 全局搜索：runGlobalSearch / fetchGlobalSearchResults / fetchFileSearchResults
// - 虚拟目录会话：openWorkspaceDir / removeWorkspaceDir / restoreVirtualWorkspaceDirs
// - LSP：activateLspForModel / ensureModelForUri / releaseLspBinding
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - 直传（定义在本 composable 调用点之前）：fetchWithAuth / getGatewayAddress / getHttpProtocol /
//   buildNodeHttpUrl / getWebSocketProtocol / buildWebSocketProtocols / getLanguageFromFilename /
//   getLanguageExtension / showToast / showConfirm / pushOverlayState / getNodeDisplayName /
//   getCurrentAgentOrNull / isStoppedAgent / refreshManageCapabilities / refreshManageTimers /
//   windowWidth / activeWindow / showWorkspacePanel / showTerminalPanel / showChatPanel /
//   workspaceSidebarWidth / workspaceSidebarResizeState / currentAgent / socket /
//   workspaceHostsChat / workspaceHostsTerminal / editorShortcutLocked /
//   effectiveGlobalSearchAgentId / normalizeWorkspaceSidebarWidth / saveWorkspaceSidebarWidth /
//   ACTIVE_Z_INDEX / BASE_Z_INDEX / manageInstalledScripts / manageGatewayScripts / getDefinition /
//   loadLspServers / getServerByLanguage / getServerByPath / ensureClient / disposeClient
// - 直传（useWorkspacePane 返回，定义在本调用点之前）：activePaneId / workspaceSessions /
//   activeWorkspaceSessionId / workspaceTabs / activeWorkspaceTabPath / activeWorkspaceSession /
//   virtualWorkspaceSessions / editorModels / workspaceFileHeartbeatTimer / isWorkspaceEditable /
//   EDITOR_FILE_HEARTBEAT_INTERVAL / globalSearch* / fileSearchResults / showWorkspaceSidebar /
//   workspaceSidebarView / workspaceMainView / workspacePaneCount / workspacePanelInteraction /
//   workspacePanelRect / workspacePanelRectBeforeMaximize / isWorkspaceMaximized /
//   saveWorkspacePanelRect / splitWorkspaceContainerRefs / editorContainerRef /
//   EDITOR_PANEL_MIN_WIDTH / EDITOR_PANEL_MIN_HEIGHT / PANEL_DRAG_ACTIVATION_DISTANCE /
//   collapseWorkspacePanes / findWorkspacePaneByView / ensureEditorPaneForFileOpen /
//   ensurePaneForView / setMainViewOnLeaf / setActivePaneView / setActivePaneViewForPane
// - getter 注入（定义在调用点之后，内部通过 xxx() 二次求值）：closePanel / agentList / panels /
//   workspaceSessionPanelId；useFileTree 返回的 fileTreeState / initFileTree /
//   getVisibleFileTreeNodes / expandedAgents / fileTreeExpanded / fileTreeLoading /
//   fileTreeSelectedAgentId / fileTreeSelectedPath / selectedAgentId / revealTabInFileTree；
//   useGitView 返回的 gitLogLoading / refreshGitView / layoutGitDiffEditor / renderDiffForPane /
//   scheduleDiffLayout；useTopology 返回的 topologyDaemonSessions / topologyExtensionSessions
import { computed, nextTick, reactive, ref, triggerRef } from 'vue'
import * as monaco from 'monaco-editor/esm/vs/editor/editor.main.js'

export function useWorkspaceEditor({
  // 直传（定义在调用点之前）
  fetchWithAuth,
  getGatewayAddress,
  getHttpProtocol,
  buildNodeHttpUrl,
  getWebSocketProtocol,
  buildWebSocketProtocols,
  getLanguageFromFilename,
  getLanguageExtension,
  showToast: showToastGetter,
  showConfirm: showConfirmGetter,
  pushOverlayState: pushOverlayStateGetter,
  getNodeDisplayName: getNodeDisplayNameGetter,
  getCurrentAgentOrNull: getCurrentAgentOrNullGetter,
  isStoppedAgent: isStoppedAgentGetter,
  closePanel: closePanelGetter,
  refreshManageCapabilities,
  refreshManageTimers,
  windowWidth,
  activeWindow,
  showWorkspacePanel,
  showTerminalPanel,
  showChatPanel,
  workspaceSidebarWidth,
  workspaceSidebarResizeState,
  agentList: agentListGetter,
  currentAgent: currentAgentGetter,
  socket,
  panels: panelsGetter,
  workspaceHostsChat: workspaceHostsChatGetter,
  workspaceHostsTerminal: workspaceHostsTerminalGetter,
  workspaceSessionPanelId: workspaceSessionPanelIdGetter,
  editorShortcutLocked: editorShortcutLockedGetter,
  effectiveGlobalSearchAgentId: effectiveGlobalSearchAgentIdGetter,
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
  // 直传（useWorkspacePane 返回，定义在调用点之前）
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
  // getter 注入（定义在调用点之后）
  fileTreeState: fileTreeStateGetter,
  initFileTree: initFileTreeGetter,
  getVisibleFileTreeNodes: getVisibleFileTreeNodesGetter,
  expandedAgents: expandedAgentsGetter,
  fileTreeExpanded: fileTreeExpandedGetter,
  fileTreeLoading: fileTreeLoadingGetter,
  fileTreeSelectedAgentId: fileTreeSelectedAgentIdGetter,
  fileTreeSelectedPath: fileTreeSelectedPathGetter,
  selectedAgentId: selectedAgentIdGetter,
  revealTabInFileTree: revealTabInFileTreeGetter,
  gitLogLoading: gitLogLoadingGetter,
  refreshGitView: refreshGitViewGetter,
  layoutGitDiffEditor: layoutGitDiffEditorGetter,
  renderDiffForPane: renderDiffForPaneGetter,
  scheduleDiffLayout: scheduleDiffLayoutGetter,
  topologyDaemonSessions: topologyDaemonSessionsGetter,
  topologyExtensionSessions: topologyExtensionSessionsGetter,
  getWorkspaceTargetNodeId: getWorkspaceTargetNodeIdGetter,
}) {
  // —— getter 化依赖的安全包装（内部以 xxx() 二次求值）——
  const fileTreeState = () => fileTreeStateGetter()
  const initFileTree = (...args) => { const fn = initFileTreeGetter(); if (fn) return fn(...args) }
  const getVisibleFileTreeNodes = (...args) => { const fn = getVisibleFileTreeNodesGetter(); if (fn) return fn(...args) }
  const expandedAgents = () => expandedAgentsGetter()
  const fileTreeExpanded = () => fileTreeExpandedGetter()
  const fileTreeLoading = () => fileTreeLoadingGetter()
  const fileTreeSelectedAgentId = () => fileTreeSelectedAgentIdGetter()
  const fileTreeSelectedPath = () => fileTreeSelectedPathGetter()
  const selectedAgentId = () => selectedAgentIdGetter()
  const revealTabInFileTree = (...args) => { const fn = revealTabInFileTreeGetter(); if (fn) return fn(...args) }
  const gitLogLoading = () => gitLogLoadingGetter()
  const refreshGitView = (...args) => { const fn = refreshGitViewGetter(); if (fn) return fn(...args) }
  const layoutGitDiffEditor = (...args) => { const fn = layoutGitDiffEditorGetter(); if (fn) return fn(...args) }
  const renderDiffForPane = (...args) => { const fn = renderDiffForPaneGetter(); if (fn) return fn(...args) }
  const scheduleDiffLayout = (...args) => { const fn = scheduleDiffLayoutGetter(); if (fn) return fn(...args) }
  const topologyDaemonSessions = () => topologyDaemonSessionsGetter()
  const topologyExtensionSessions = () => topologyExtensionSessionsGetter()
  const getWorkspaceTargetNodeId = (...args) => { const fn = getWorkspaceTargetNodeIdGetter(); if (fn) return fn(...args) }
  // 定义在调用点之后的函数（App.vue 以 getter 形式传入，内部二次求值）
  const showToast = (...args) => { const fn = showToastGetter(); if (fn) return fn(...args) }
  const showConfirm = (...args) => { const fn = showConfirmGetter(); if (fn) return fn(...args) }
  const pushOverlayState = (...args) => { const fn = pushOverlayStateGetter(); if (fn) return fn(...args) }
  const getNodeDisplayName = (...args) => { const fn = getNodeDisplayNameGetter(); if (fn) return fn(...args) }
  const getCurrentAgentOrNull = (...args) => { const fn = getCurrentAgentOrNullGetter(); if (fn) return fn(...args) }
  const isStoppedAgent = (...args) => { const fn = isStoppedAgentGetter(); if (fn) return fn(...args) }
  // 定义在调用点之后的 ref/computed（App.vue 以 getter 形式传入，内部二次求值）
  const currentAgent = () => currentAgentGetter()
  const workspaceHostsChat = () => workspaceHostsChatGetter()
  const workspaceHostsTerminal = () => workspaceHostsTerminalGetter()
  const editorShortcutLocked = () => editorShortcutLockedGetter()
  const effectiveGlobalSearchAgentId = () => effectiveGlobalSearchAgentIdGetter()

const workspacePanelStyle = computed(() => {
  if (windowWidth.value <= 768) {
    return {
      top: '0',
      left: '0',
      width: '100vw',
      height: 'var(--app-height, 100vh)',
      zIndex: 2000,
    }
  }

  return {
    top: `${workspacePanelRect.value.top}px`,
    left: `${workspacePanelRect.value.left}px`,
    width: `${workspacePanelRect.value.width}px`,
    height: `${workspacePanelRect.value.height}px`,
    zIndex: activeWindow.value === 'workspace' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
  }
})

const activeWorkspaceTab = computed(() => {
  return workspaceTabs.value.find(tab => tab.path === activeWorkspaceTabPath.value) || null
})

function clamp(value, min, max) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

function startWorkspaceSidebarResize(event) {
  if (windowWidth.value <= 768 || !showWorkspaceSidebar.value) return

  workspaceSidebarResizeState.value = {
    active: true,
    startX: event.clientX,
    startWidth: workspaceSidebarWidth.value,
  }

  document.addEventListener('mousemove', onWorkspaceSidebarResize)
  document.addEventListener('mouseup', stopWorkspaceSidebarResize)
  event.preventDefault()
  event.stopPropagation()
}

function onWorkspaceSidebarResize(event) {
  if (!workspaceSidebarResizeState.value.active) return

  const deltaX = event.clientX - workspaceSidebarResizeState.value.startX
  const nextWidth = workspaceSidebarResizeState.value.startWidth + deltaX
  workspaceSidebarWidth.value = normalizeWorkspaceSidebarWidth(nextWidth)
}

function stopWorkspaceSidebarResize() {
  if (!workspaceSidebarResizeState.value.active) {
    document.removeEventListener('mousemove', onWorkspaceSidebarResize)
    document.removeEventListener('mouseup', stopWorkspaceSidebarResize)
    return
  }

  workspaceSidebarResizeState.value = {
    active: false,
    startX: 0,
    startWidth: workspaceSidebarWidth.value,
  }

  document.removeEventListener('mousemove', onWorkspaceSidebarResize)
  document.removeEventListener('mouseup', stopWorkspaceSidebarResize)
  saveWorkspaceSidebarWidth()
}

// 设置焦点窗口
function focusWindow(windowType) {
  activeWindow.value = windowType
}

// 编辑器窗口最大化/还原
function toggleWorkspaceMaximize() {
  if (isWorkspaceMaximized.value) {
    // 还原
    if (workspacePanelRectBeforeMaximize.value) {
      workspacePanelRect.value = { ...workspacePanelRectBeforeMaximize.value }
    }
    isWorkspaceMaximized.value = false
  } else {
    // 最大化
    workspacePanelRectBeforeMaximize.value = { ...workspacePanelRect.value }
    workspacePanelRect.value = {
      top: 0,
      left: 0,
      width: window.innerWidth,
      height: window.innerHeight,
    }
    isWorkspaceMaximized.value = true
  }
  nextTick(() => {
    layoutMonacoEditor()
  })
}


function getWorkspacePanelBounds() {
  const HEADER_HEIGHT = 32 // 标题栏高度
  const MIN_VISIBLE_WIDTH = 100 // 至少保留100px面板宽度可见
  return {
    minTop: 0, // 标题栏不能拖到窗口顶部之外
    minLeft: 0, // 标题栏不能拖到窗口左侧之外
    maxLeft: window.innerWidth - MIN_VISIBLE_WIDTH, // 保留至少100px面板宽度可见
    maxTop: window.innerHeight - HEADER_HEIGHT, // 保留标题栏高度可见
    maxWidth: window.innerWidth,
    maxHeight: window.innerHeight,
  }
}

function ensureWorkspacePanelInViewport() {
  const HEADER_HEIGHT = 32 // 标题栏高度
  const MIN_VISIBLE_WIDTH = 100 // 至少保留100px面板宽度可见
  const maxWidth = Math.max(window.innerWidth, EDITOR_PANEL_MIN_WIDTH)
  const maxHeight = Math.max(window.innerHeight, EDITOR_PANEL_MIN_HEIGHT)

  workspacePanelRect.value.width = clamp(workspacePanelRect.value.width, EDITOR_PANEL_MIN_WIDTH, maxWidth)
  workspacePanelRect.value.height = clamp(workspacePanelRect.value.height, EDITOR_PANEL_MIN_HEIGHT, maxHeight)

  // 标题栏不能移出窗口
  workspacePanelRect.value.left = clamp(
    workspacePanelRect.value.left,
    0, // 标题栏不能拖到窗口左侧之外
    window.innerWidth - MIN_VISIBLE_WIDTH // 保留至少100px面板宽度可见
  )
  workspacePanelRect.value.top = clamp(
    workspacePanelRect.value.top,
    0, // 标题栏不能拖到窗口顶部之外
    window.innerHeight - HEADER_HEIGHT // 保留标题栏高度可见
  )
}

function startWorkspacePanelMove(event) {
  if (windowWidth.value <= 768) return
  if (event.target.closest('.workspace-panel-actions')) return

  focusWindow('workspace')

  workspacePanelInteraction.value = {
    active: false,
    mode: 'move',
    direction: null,
    startX: event.clientX,
    startY: event.clientY,
    startTop: workspacePanelRect.value.top,
    startLeft: workspacePanelRect.value.left,
    startWidth: workspacePanelRect.value.width,
    startHeight: workspacePanelRect.value.height,
  }

  document.addEventListener('mousemove', onWorkspacePanelPointerMove)
  document.addEventListener('mouseup', stopWorkspacePanelInteraction)
}

function startWorkspacePanelResize(event, direction) {
  if (windowWidth.value <= 768) return

  workspacePanelInteraction.value = {
    active: true,
    mode: 'resize',
    direction,
    startX: event.clientX,
    startY: event.clientY,
    startTop: workspacePanelRect.value.top,
    startLeft: workspacePanelRect.value.left,
    startWidth: workspacePanelRect.value.width,
    startHeight: workspacePanelRect.value.height,
  }

  document.addEventListener('mousemove', onWorkspacePanelPointerMove)
  document.addEventListener('mouseup', stopWorkspacePanelInteraction)
  event.preventDefault()
  event.stopPropagation()
}

function onWorkspacePanelPointerMove(event) {
  const deltaX = event.clientX - workspacePanelInteraction.value.startX
  const deltaY = event.clientY - workspacePanelInteraction.value.startY

  if (workspacePanelInteraction.value.mode === 'move' && !workspacePanelInteraction.value.active) {
    const dragDistance = Math.hypot(deltaX, deltaY)
    if (dragDistance < PANEL_DRAG_ACTIVATION_DISTANCE) {
      return
    }

    workspacePanelInteraction.value = {
      ...workspacePanelInteraction.value,
      active: true,
    }
    event.preventDefault()
  }

  if (!workspacePanelInteraction.value.active) return

  if (workspacePanelInteraction.value.mode === 'move') {
    const bounds = getWorkspacePanelBounds()
    workspacePanelRect.value.left = clamp(workspacePanelInteraction.value.startLeft + deltaX, bounds.minLeft, bounds.maxLeft)
    workspacePanelRect.value.top = clamp(workspacePanelInteraction.value.startTop + deltaY, bounds.minTop, bounds.maxTop)
    return
  }

  const direction = workspacePanelInteraction.value.direction || ''
  const startLeft = workspacePanelInteraction.value.startLeft
  const startTop = workspacePanelInteraction.value.startTop
  const startWidth = workspacePanelInteraction.value.startWidth
  const startHeight = workspacePanelInteraction.value.startHeight

  let nextLeft = startLeft
  let nextTop = startTop
  let nextWidth = startWidth
  let nextHeight = startHeight

  if (direction.includes('e')) {
    nextWidth = clamp(startWidth + deltaX, EDITOR_PANEL_MIN_WIDTH, Math.max(window.innerWidth - startLeft, EDITOR_PANEL_MIN_WIDTH))
  }

  if (direction.includes('s')) {
    nextHeight = clamp(startHeight + deltaY, EDITOR_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - startTop, EDITOR_PANEL_MIN_HEIGHT))
  }

  if (direction.includes('w')) {
    const desiredLeft = clamp(startLeft + deltaX, 0, startLeft + startWidth - EDITOR_PANEL_MIN_WIDTH)
    nextLeft = desiredLeft
    nextWidth = startWidth - (desiredLeft - startLeft)
  }

  if (direction.includes('n')) {
    const desiredTop = clamp(startTop + deltaY, 0, startTop + startHeight - EDITOR_PANEL_MIN_HEIGHT)
    nextTop = desiredTop
    nextHeight = startHeight - (desiredTop - startTop)
  }

  if (nextLeft + nextWidth > window.innerWidth) {
    nextWidth = Math.max(EDITOR_PANEL_MIN_WIDTH, window.innerWidth - nextLeft)
  }

  if (nextTop + nextHeight > window.innerHeight) {
    nextHeight = Math.max(EDITOR_PANEL_MIN_HEIGHT, window.innerHeight - nextTop)
  }

  workspacePanelRect.value.left = clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0))
  workspacePanelRect.value.top = clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0))
  workspacePanelRect.value.width = clamp(nextWidth, EDITOR_PANEL_MIN_WIDTH, Math.max(window.innerWidth - workspacePanelRect.value.left, EDITOR_PANEL_MIN_WIDTH))
  workspacePanelRect.value.height = clamp(nextHeight, EDITOR_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - workspacePanelRect.value.top, EDITOR_PANEL_MIN_HEIGHT))
}

function stopWorkspacePanelInteraction() {
  workspacePanelInteraction.value = {
    active: false,
    mode: null,
    direction: null,
    startX: 0,
    startY: 0,
    startTop: 0,
    startLeft: 0,
    startWidth: 0,
    startHeight: 0,
  }

  document.removeEventListener('mousemove', onWorkspacePanelPointerMove)
  document.removeEventListener('mouseup', stopWorkspacePanelInteraction)
  saveWorkspacePanelRect()
}

function getWorkspaceTabByPath(path) {
  return workspaceTabs.value.find(tab => tab.path === path) || null
}

function syncWorkspaceTabDirtyState(path, value) {
  const tab = getWorkspaceTabByPath(path)
  if (tab) {
    tab.isDirty = value
  }
}

function updateWorkspaceTabFileStat(tab, fileStat = {}) {
  if (!tab) return
  tab.mtimeNs = fileStat.mtime_ns ?? null
  tab.fileSize = fileStat.size ?? null
}

function markWorkspaceTabExternalModified(path, value) {
  const tab = getWorkspaceTabByPath(path)
  if (tab) {
    tab.externalModified = value
  }
}

// ===== 蓝色系 Monaco 主题（对应原 CodeMirror blueDark）=====
const EDITOR_FONT_FAMILY = "'Consolas', 'Microsoft YaHei', monospace"

monaco.editor.defineTheme('blueDark', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '5a7a9a' },
    { token: 'keyword', foreground: '7aa2f7' },
    { token: 'keyword.control', foreground: '7aa2f7' },
    { token: 'string', foreground: '9ece6a' },
    { token: 'string.escape', foreground: '56b6c2' },
    { token: 'number', foreground: 'e0af68' },
    { token: 'regexp', foreground: '56b6c2' },
    { token: 'operator', foreground: '56b6c2' },
    { token: 'delimiter', foreground: 'a8c8e8' },
    { token: 'type', foreground: 'e0af68' },
    { token: 'type.identifier', foreground: 'e0af68' },
    { token: 'namespace', foreground: 'e0af68' },
    { token: 'annotation', foreground: 'e0af68' },
    { token: 'modifier', foreground: 'e0af68' },
    { token: 'identifier', foreground: 'a8c8e8' },
    { token: 'variable', foreground: 'a8c8e8' },
    { token: 'variable.predefined', foreground: 'ff9e64' },
    { token: 'constant', foreground: 'ff9e64' },
    { token: 'tag', foreground: 'f7768e' },
    { token: 'attribute.name', foreground: 'f7768e' },
    { token: 'function', foreground: '82aaff' },
    { token: 'invalid', foreground: 'ffffff' },
    { token: 'strong', fontStyle: 'bold' },
    { token: 'emphasis', fontStyle: 'italic' },
    { token: 'strikethrough', fontStyle: 'strikethrough' },
  ],
  colors: {
    'editor.foreground': '#a8c8e8',
    'editor.background': '#0d1b2a',
    'editorCursor.foreground': '#528bff',
    'editor.lineHighlightBackground': '#1a2a3a55',
    'editor.selectionBackground': '#264f78',
    'editor.inactiveSelectionBackground': '#264f7855',
    'editor.selectionHighlightBackground': '#264f7855',
    'editor.findMatchBackground': '#72a1ff59',
    'editor.findMatchHighlightBackground': '#6199ff2f',
    'editorBracketMatch.background': '#264f78aa',
    'editorLineNumber.foreground': '#5a7a9a',
    'editorLineNumber.activeForeground': '#a8c8e8',
    'editorGutter.background': '#0d1b2a',
    'editorWidget.background': '#16263a',
    'editorWidget.border': '#1a2a3a',
    'editorSuggestWidget.background': '#16263a',
    'editorSuggestWidget.selectedBackground': '#1a2a3a',
    'editorHoverWidget.background': '#16263a',
    'editorHoverWidget.border': '#1a2a3a',
    'editorIndentGuide.background1': '#1a2a3a',
    'editorIndentGuide.activeBackground1': '#2a4a6a',
    'scrollbarSlider.background': '#1a2a3a88',
    'scrollbarSlider.hoverBackground': '#2a4a6aaa',
  },
})

// ===== 编辑器增强：VS Code 风格编辑能力 =====
// 说明：补全依赖 Monaco 内置的语言服务 worker（json/css/html/ts），
// 其余语言为词法级高亮；文件读写仍走网关远端接口。
const EDITOR_TAB_SIZE = 4

// ===== 自由分割：每个 file pane 一个独立 Monaco 实例 =====
// 设计要点（避免「多实例互相触发 layout 导致主线程卡死」）：
// 1) 实例创建/销毁只发生在 pane 容器集合真正变化时（ensureMonacoEditor 内做集合差分）；
// 2) 容器尺寸变化由 Monaco 自身的 automaticLayout(ResizeObserver) 处理，本文件不额外挂
//    ResizeObserver，也不在 resize 回调里对每个实例调 layout()，避免「layout → 尺寸变化 →
//    再 layout」的震荡；
// 3) 显式 layout() 一律经 scheduleWorkspaceLayout() 用 rAF 合并，同一帧内多次调用只执行一次。
const editorViews = new Map()  // paneId -> monaco editor instance
const workspaceViewPanes = new Map()  // paneId -> 该 pane 当前绑定的文件 path
// 自由分割：每个 diff pane 一个独立 Monaco DiffEditor 实例（paneId -> { editor, originalModel, modifiedModel, oldText, newText }）。
const diffEditorViews = new Map()
const diffContainerRefs = ref(new Map())  // paneId -> 容器元素
function setDiffContainerRef(paneId, el) {
  if (!paneId) return
  if (el) {
    if (diffContainerRefs.value.get(paneId) === el) return
    diffContainerRefs.value.set(paneId, el)
  } else {
    if (!diffContainerRefs.value.has(paneId)) return
    diffContainerRefs.value.delete(paneId)
  }
  triggerRef(diffContainerRefs)
  nextTick(() => {
    renderDiffForPane(paneId)
    scheduleDiffLayout()
  })
}
// 按 data-diff-pane-id 从文档解析「当前真实挂载」的容器（ref 元素可能是渲染中间态）
function resolveDiffContainer(paneId) {
  const live = document.querySelector(`.workspace-diff-monaco[data-diff-pane-id="${paneId}"]`)
  if (live && live.isConnected) return live
  const refEl = diffContainerRefs.value.get(paneId)
  return refEl && refEl.isConnected ? refEl : null
}
// 已分割时每个 pane 独立的标签列表（paneId -> path[]）。未分割时该 Map 为空，
// 标签栏仍由全局 workspaceTabs 驱动，保证未分割路径零回归。
// 目的：分割后两个 pane 的标签栏互不影响（关闭一个 pane 的标签不会连带关闭另一个）。
const workspacePaneTabs = new Map()  // paneId -> path[]
const workspacePaneTabsVersion = ref(0)  // 触发依赖 workspacePaneTabs 的模板/计算属性重算

function getPaneTabs(paneId) {
  if (!paneId) return []
  const paths = workspacePaneTabs.get(paneId)
  if (!paths || paths.length === 0) return []
  const all = workspaceTabs.value
  return paths.map(p => all.find(t => t.path === p)).filter(Boolean)
}

// 该 path 是否仍被某个 pane 的标签列表引用（用于判断关闭标签时能否真正释放模型）
function isPathReferencedByAnyPane(path) {
  for (const paths of workspacePaneTabs.values()) {
    if (paths.includes(path)) return true
  }
  return false
}

// 已分割时把 path 加入指定 pane 的标签列表（去重）
function addPaneTab(paneId, path) {
  if (!paneId || !path) return
  const paths = workspacePaneTabs.get(paneId) || []
  if (!paths.includes(path)) {
    paths.push(path)
    workspacePaneTabs.set(paneId, paths)
    workspacePaneTabsVersion.value += 1
  }
}

// 从指定 pane 的标签列表移除 path
function removePaneTab(paneId, path) {
  const paths = workspacePaneTabs.get(paneId)
  if (!paths) return
  const index = paths.indexOf(path)
  if (index === -1) return
  paths.splice(index, 1)
  workspacePaneTabsVersion.value += 1
}

// 当前激活 pane 的 Monaco 实例（激活 pane 非 file 时回退到任一实例）
function getActiveWorkspaceView() {
  const active = editorViews.get(activePaneId.value)
  if (active) return active
  for (const [, view] of editorViews) return view
  return null
}

function buildEditorOptions() {
  return {
    model: null,
    theme: 'blueDark',
    fontFamily: EDITOR_FONT_FAMILY,
    fontSize: 13,
    lineHeight: 20,
    tabSize: EDITOR_TAB_SIZE,
    insertSpaces: true,
    automaticLayout: true,
    minimap: { enabled: true },
    scrollBeyondLastLine: true,
    renderWhitespace: 'selection',
    smoothScrolling: true,
    cursorBlinking: 'smooth',
    mouseWheelZoom: true,
    bracketPairColorization: { enabled: true },
    guides: { bracketPairs: true, indentation: true },
    folding: true,
    showFoldingControls: 'mouseover',
    wordWrap: 'off',
    contextmenu: true,
    quickSuggestions: { other: true, comments: false, strings: true },
    suggestOnTriggerCharacters: true,
    tabCompletion: 'on',
    readOnly: !isWorkspaceEditable.value,
    readOnlyMessage: { value: '编辑器当前为只读，点击工具栏解锁后可编辑' },
  }
}

// 内容变更 → 回写该文件对应的 tab（模型上记录了 path，多 pane 打开同一文件时天然同步）
// ===== 光标历史（后退/前进，Ctrl+Alt+←/→）=====
// VS Code 的 navigateBack / navigateForward：记录光标「跳转」到的位置，可前后导航。
// Monaco standalone 无此内置功能，这里自行维护历史栈。
// 元素：{ path, line, column }；cursorHistoryIndex 为当前指针。
// 连续的光标移动（同文件、短时间）合并为一条记录，避免方向键逐字移动产生大量冗余；
// 后退/前进跳转期间置 cursorNavGuard，防止跳转本身被回写进历史。
const cursorHistory = []
let cursorHistoryIndex = -1
let lastCursorTime = 0
let cursorNavGuard = false
const CURSOR_MERGE_MS = 300 // 同文件连续光标移动在此窗口内合并为一条记录

// 记录一次光标位置。连续移动（同文件、短时间）合并更新当前记录，不新增。
function recordCursorLocation(path, line, column) {
  if (!path || !line) return
  if (cursorNavGuard) return // 后退/前进跳转中，不把跳转结果写回历史
  const now = Date.now()
  const current = cursorHistory[cursorHistoryIndex]
  // 与当前指针处完全相同 → 忽略
  if (current && current.path === path && current.line === line && current.column === column) return
  // 同文件且短时间内的连续移动 → 更新当前记录（光标随移动刷新）
  if (current && current.path === path && now - lastCursorTime < CURSOR_MERGE_MS) {
    cursorHistory[cursorHistoryIndex] = { path, line, column }
  } else {
    // 新增：截断指针之后的记录，追加新位置并前移指针
    cursorHistory.splice(cursorHistoryIndex + 1, cursorHistory.length - cursorHistoryIndex - 1)
    cursorHistory.push({ path, line, column })
    cursorHistoryIndex = cursorHistory.length - 1
  }
  lastCursorTime = now
}

// 后退到上一个光标位置（指针回退）
async function goToPreviousCursorLocation() {
  if (cursorHistoryIndex <= 0) return
  cursorHistoryIndex -= 1
  const loc = cursorHistory[cursorHistoryIndex]
  if (loc) {
    cursorNavGuard = true
    try {
      await revealInWorkspace(loc.path, loc.line, loc.column)
    } finally {
      cursorNavGuard = false
    }
  }
}

// 前进到下一个光标位置（指针前进）
async function goToNextCursorLocation() {
  if (cursorHistoryIndex >= cursorHistory.length - 1) return
  cursorHistoryIndex += 1
  const loc = cursorHistory[cursorHistoryIndex]
  if (loc) {
    cursorNavGuard = true
    try {
      await revealInWorkspace(loc.path, loc.line, loc.column)
    } finally {
      cursorNavGuard = false
    }
  }
}

function bindWorkspaceViewEvents(view) {
  // 重新聚焦编辑器时恢复原生快捷键控制（撤销 ESC「脱离」状态）：
  // 用户重新进入编辑器编辑，Ctrl+A 应恢复为编辑器全选。
  view.onDidFocusEditorText(() => {
    editorShortcutLocked().value = false
  })
  view.onDidChangeModelContent((e) => {
    const model = view.getModel()
    if (!model) return
    const path = model.__jarvisPath
    if (!path) return
    const tab = getWorkspaceTabByPath(path)
    if (!tab) return
    tab.content = model.getValue()
    tab.isDirty = tab.content !== tab.originalContent
  })
  // 记录光标位置（供 Ctrl+Alt+←/→ 后退/前进导航）：
  // 连续移动（同文件、短时间）合并为一条，跳转（跨文件/间隔）新增记录。
  view.onDidChangeCursorPosition((e) => {
    const model = view.getModel()
    if (!model) return
    const path = model.__jarvisPath
    if (!path) return
    const pos = e.position
    if (pos) recordCursorLocation(path, pos.lineNumber, pos.column)
  })
  // 跳转到定义：用纯 F12（Monaco 在编辑器聚焦时会拦截该键，浏览器不弹开发者工具）。
  // 不用 Monaco 内置 revealDefinition——它只能跳到已加载的 model，无法自动打开
  // 未打开的目标文件；这里拿到 LSP definition 结果后，若目标文件未打开则自行
  // openWorkspaceFile 打开再定位。
  view.addAction({
    id: 'jarvis.goToDefinition',
    label: 'Go to Definition',
    keybindings: [monaco.KeyCode.F12],
    contextMenuGroupId: 'navigation',
    contextMenuOrder: 1.5,
    run: (ed) => {
      jumpToDefinition(ed)
    },
  })
  // 后退/前进光标位置（Ctrl+Alt+←/→）。
  // 用 addAction 绑定：编辑器聚焦时优先于全局 Ctrl+Alt+方向键处理（切 pane/大厅）。
  view.addAction({
    id: 'jarvis.goToPreviousCursorLocation',
    label: 'Go to Previous Cursor Location',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.LeftArrow],
    run: () => {
      goToPreviousCursorLocation()
    },
  })
  view.addAction({
    id: 'jarvis.goToNextCursorLocation',
    label: 'Go to Next Cursor Location',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.RightArrow],
    run: () => {
      goToNextCursorLocation()
    },
  })
  // Ctrl+P 打开 Monaco 内置命令面板（editor.action.quickCommand，默认 F1）。
  // 全局 handler 在编辑器聚焦时让位给 Monaco，由这里的 addAction 接管 Ctrl+P。
  view.addAction({
    id: 'jarvis.openCommandPalette',
    label: 'Command Palette',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyP],
    run: (ed) => {
      ed.trigger('keyboard', 'editor.action.quickCommand', null)
    },
  })
}

// LSP file:// uri → 本地文件绝对路径（如 file:///home/a.py → /home/a.py）
function lspUriToPath(uri) {
  if (!uri) return ''
  const raw = String(uri)
  if (!raw.startsWith('file://')) return raw
  return decodeURIComponent(raw.slice('file://'.length))
}

// 从 LSP definition 结果中取第一个目标 {path, line, column}（支持 Location / LocationLink[]）
function pickFirstDefinitionTarget(result) {
  if (!result) return null
  const items = Array.isArray(result) ? result : [result]
  for (const it of items) {
    if (!it) continue
    const uri = it.targetUri || it.uri
    const range = it.targetRange || it.range
    if (!uri || !range) continue
    return {
      path: lspUriToPath(uri),
      line: (range.start?.line ?? 0) + 1,
      column: (range.start?.character ?? 0) + 1,
    }
  }
  return null
}

// Ctrl+F12 自定义跳转定义：拿到目标文件后，未打开则打开，再定位到目标行/列
async function jumpToDefinition(ed) {
  const model = ed && ed.getModel && ed.getModel()
  const position = ed && ed.getPosition && ed.getPosition()
  if (!model || !position) return
  const result = await getDefinition(model, position)
  const target = pickFirstDefinitionTarget(result)
  if (!target || !target.path) return
  await revealInWorkspace(target.path, target.line, target.column)
}

// 在工作区中打开（或激活）目标文件并定位到指定行列。
// 供 F12 跳转定义与 peek 双击跳转（registerEditorOpener）复用。
async function revealInWorkspace(path, line, column) {
  if (!path) return
  // 判断是否已作为标签打开（而非 editorModels 是否有 model——ensureModelForUri
  // 会预加载跨文件 model 但未建标签，若据此判断会误走 activateWorkspaceTab，
  // 导致不新建标签、只把当前缓冲区替换为目标文件内容）。
  // 有 tab 则激活，否则 openWorkspaceFile 新建标签并激活。
  if (!getWorkspaceTabByPath(path)) {
    await openWorkspaceFile(path)
  } else {
    activateWorkspaceTab(path)
  }
  await nextTick()
  const view = getActiveWorkspaceView()
  if (!view) return
  view.revealLineInCenter(line)
  view.setPosition({ lineNumber: line, column })
  view.focus()
}

// 注册 Monaco 资源 opener：当 Monaco 需要打开当前 model 之外的资源时（如 peek
// definition 窗口双击内容跳转、go-to-definition），回调这里。默认行为对未加载的
// model 什么都不做，故必须自行打开目标文件并定位，否则 peek 双击无法跳转。
// 返回 true 表示已处理，Monaco 不再走默认逻辑。
monaco.editor.registerEditorOpener({
  openCodeEditor: async (source, resource, selectionOrPosition) => {
    const path = lspUriToPath(resource?.toString?.() || '')
    if (!path) return false
    const line = selectionOrPosition?.startLineNumber ?? selectionOrPosition?.lineNumber ?? 1
    const column = selectionOrPosition?.startColumn ?? selectionOrPosition?.column ?? 1
    await revealInWorkspace(path, line, column)
    return true
  },
})
function applyEditorViewModel(paneId, view) {
  const path = workspaceViewPanes.get(paneId)
  if (!path) {
    if (view.getModel()) view.setModel(null)
    view.updateOptions({ readOnly: !isWorkspaceEditable.value })
    return
  }
  const modelData = editorModels.get(path)
  if (!modelData) {
    workspaceViewPanes.delete(paneId)
    if (view.getModel()) view.setModel(null)
    return
  }
  let model = modelData.model
  if (!model || model.isDisposed()) {
    model = monaco.editor.createModel(modelData.content, modelData.language, monaco.Uri.file(path))
    model.__jarvisPath = path
    modelData.model = model
  }
  if (view.getModel() !== model) view.setModel(model)
  view.updateOptions({ readOnly: !isWorkspaceEditable.value })
}

// 未分割时，Monaco 容器由 WorkspacePanel 内部渲染（editorContainerRef），沿用单实例路径。
// 为每个 file pane 的容器建立/复用实例；容器集合变化时才创建或销毁。
// 关键：ref 回调拿到的元素可能是「渲染中间态」元素（Vue 随后会替换掉它），把实例建在
// 这种脱离文档的元素上会导致编辑器 DOM 永久悬空（容器里看不到编辑器）。因此这里不直接
// 使用 ref 元素，而是按 data-pane-id 从文档中解析「当前真实挂载」的容器。
function resolveSplitWorkspaceContainer(paneId) {
  const live = document.querySelector(`.workspace-monaco-container[data-pane-id="${paneId}"]`)
  if (live && live.isConnected) return live
  const refEl = splitWorkspaceContainerRefs.value.get(paneId)
  return refEl && refEl.isConnected ? refEl : null
}

function ensureSplitMonacoEditors() {
  for (const paneId of [...splitWorkspaceContainerRefs.value.keys()]) {
    const container = resolveSplitWorkspaceContainer(paneId)
    // 容器尚未真正入文档时不要创建实例，等下一次调度（ref 回调 / rAF）补齐。
    if (!container) continue
    let view = editorViews.get(paneId)
    // 失效判定只看「宿主容器元素是否被替换」：Monaco 的编辑器 DOM 是异步挂载的，
    // getDomNode() 在无 model 时返回 null，创建后立刻 querySelector 也拿不到根节点，
    // 因此任何基于「实例 DOM 是否在容器里」的判断都会误判并导致反复 dispose/create。
    // 容器元素本身被 Vue 替换（pane 重建）时，才需要销毁旧实例、在新容器上重建。
    if (view && view.__jarvisContainer !== container) {
      view.dispose()
      editorViews.delete(paneId)
      view = null
    }
    if (!view) {
      view = monaco.editor.create(container, buildEditorOptions())
      view.__jarvisContainer = container
      bindWorkspaceViewEvents(view)
      editorViews.set(paneId, view)
    }
    applyEditorViewModel(paneId, view)
  }
  // 清理已消失 pane 的实例
  for (const [paneId, view] of [...editorViews]) {
    if (!splitWorkspaceContainerRefs.value.has(paneId)) {
      view.dispose()
      editorViews.delete(paneId)
      workspaceViewPanes.delete(paneId)
    }
  }
}

function ensureMonacoEditor() {
  ensureSplitMonacoEditors()
}




// 已分割时每个 pane 的标签列表由「打开文件 / 点击标签」时显式登记（addPaneTab），
// 新 pane 一律从空开始；不在这里用全局标签兜底补种，否则新 pane 会凭空出现
// 其他 pane 的标签（同一文件同时出现在两个 pane 顶部）。

// 显式 layout 合并到下一帧，避免同一帧内对多个实例反复 layout 造成尺寸震荡。
// 另外做有限次重试：ref 回调触发时容器可能尚未真正入文档（Vue 可能在插入前调用 ref），
// 此时建不了实例；等下一帧/下一个 tick 容器入文档后再补一次，避免「首次分割无实例」。
let workspaceLayoutScheduled = false
let workspaceLayoutRetries = 0
const EDITOR_LAYOUT_MAX_RETRIES = 8
function scheduleWorkspaceLayout() {
  if (workspaceLayoutScheduled) return
  workspaceLayoutScheduled = true
  requestAnimationFrame(() => {
    workspaceLayoutScheduled = false
    layoutMonacoEditor()
    if (workspaceLayoutRetries < EDITOR_LAYOUT_MAX_RETRIES) {
      const pending = [...splitWorkspaceContainerRefs.value.keys()].some((paneId) => {
        const container = resolveSplitWorkspaceContainer(paneId)
        if (!container) return false
        const view = editorViews.get(paneId)
        return !view || view.__jarvisContainer !== container
      })
      if (pending) {
        workspaceLayoutRetries += 1
        scheduleWorkspaceLayout()
        return
      }
    }
    workspaceLayoutRetries = 0
  })
}

function layoutMonacoEditor() {
  ensureSplitMonacoEditors()
  for (const [, view] of editorViews) {
    if (view.getContainerDomNode?.()?.isConnected) view.layout()
  }
}

// 自由分割：Monaco 视图绑定在具体 DOM 容器上，分割/激活/关闭 pane 时容器会被替换，
// 旧容器随 DOM 卸载后视图即失效。此处在容器变化后重建视图并恢复当前标签。
// 说明：模型（editorModels）与内容不受影响，仅重建视图层。
function remountMonacoEditor() {
  // 按容器集合差分补齐/复用实例（容器未变则复用，不会重建）
  ensureSplitMonacoEditors()
}

// 保存当前编辑器（激活 pane / 单实例）正在显示的文件的 view state（光标位置、滚动位置、选区、折叠）。
// Monaco 的 setModel 会重置光标与滚动，切换标签前必须先保存，否则切回来位置丢失。
function saveCurrentEditorViewState() {
  const currentPath = activeWorkspaceTabPath.value
  if (!currentPath) return
  const modelData = editorModels.get(currentPath)
  if (!modelData) return
  const view = editorViews.get(activePaneId.value)
  // 无 model 时 saveViewState 返回空状态，会覆盖已保存的 viewState（如 remountMonacoEditor 重建视图后）
  if (!view || !view.getModel()) return
  modelData.viewState = view.saveViewState()
}

// 恢复指定 pane 上目标文件的 view state（需在 setModel 之后调用）。
function restoreEditorViewState(view, path) {
  if (!view) return
  const modelData = editorModels.get(path)
  if (!modelData?.viewState) return
  view.restoreViewState(modelData.viewState)
}

function activateWorkspaceTab(path) {
  // 切换前先保存当前文件的 view state（光标+滚动），否则 setModel 重置后位置丢失
  saveCurrentEditorViewState()
  const session = activeWorkspaceSession.value
  if (session) session.activeTabPath = path
  const modelData = editorModels.get(path)
  if (!modelData) return
  let model = modelData.model
  if (!model || model.isDisposed()) {
    model = monaco.editor.createModel(modelData.content, modelData.language, monaco.Uri.file(path))
    model.__jarvisPath = path
    modelData.model = model
  }
  // 只把「激活 pane」绑定到该文件；其他 pane 保持各自内容（新 pane 为空）
  ensureSplitMonacoEditors()
  const activeView = editorViews.get(activePaneId.value)
  if (activeView) {
    // 该文件登记到激活 pane 的标签列表（点击标签/打开文件都走这里）
    addPaneTab(activePaneId.value, path)
    workspaceViewPanes.set(activePaneId.value, path)
    if (activeView.getModel() !== model) activeView.setModel(model)
    restoreEditorViewState(activeView, path)
    activeView.updateOptions({ readOnly: !isWorkspaceEditable.value })
    nextTick(() => {
      scheduleWorkspaceLayout()
      activeView.focus()
    })
  }
  // 模型就绪后尝试接入 LSP（失败静默降级，不影响编辑器）
  activateLspForModel(path, modelData)
}

// ---------------------------------------------------------------------------
// LSP 接入（薄层：所有逻辑在 src/lsp/ 模块内，此处只做时机编排）
// ---------------------------------------------------------------------------

// 语言清单只需拉一次，失败也不阻塞编辑器
let lspRegistryReady = false
async function ensureLspRegistry() {
  if (lspRegistryReady) return
  try {
    await loadLspServers({
      fetchWithAuth,
      getGatewayAddress,
      getHttpProtocol,
    })
    lspRegistryReady = true
  } catch {
    // registry 内部已降级处理，这里兜底
  }
}

// 记录 path -> { serverId, root }，供关闭标签时精确释放
const lspBindings = new Map()

/**
 * 为当前模型接入 LSP。
 *
 * 已知限制：仅支持 master 本地（文件读写走 /api/node/{id}/... 时，
 * 非 master 节点的文件系统与本地 LSP 进程不一致，故跳过）。
 */
async function activateLspForModel(path, modelData) {
  if (!path || !modelData || !modelData.model) return
  // 只读预览、非 master 节点：不接入
  if (getWorkspaceTargetNodeId() !== 'master') return

  await ensureLspRegistry()

  const language = modelData.model.getLanguageId?.() || modelData.language
  const spec = getServerByLanguage(language) || getServerByPath(path)
  if (!spec) return

  const workspaceRoot = resolveLspWorkspaceRoot(path)
  const client = await ensureClient({
    spec,
    workspaceRoot,
    model: modelData.model,
    deps: { fetchWithAuth, getGatewayAddress, getWebSocketProtocol, buildWebSocketProtocols, ensureModelForUri },
  })
  if (client) {
    lspBindings.set(path, { serverId: spec.id, root: workspaceRoot })
  }
}

/**
 * 确保 file:// uri 对应的 Monaco model 已存在（跨文件 peek definition 需要）。
 *
 * Monaco 内置 peek 通过 monaco.editor.getModel(uri) 取目标 model 渲染内容；
 * 目标文件从未打开过时 model 不存在 → peek 只显示文件名/行列号、内容空白。
 * 这里在 definition provider 返回前异步加载目标文件并创建 model（不激活标签、
 * 不创建 workspace tab），让 peek 能拿到内容。已加载则直接复用。
 *
 * @param {string} uri LSP file:// uri
 * @returns {Promise<void>}
 */
async function ensureModelForUri(uri) {
  if (!uri) return
  const raw = String(uri)
  const path = raw.startsWith('file://') ? decodeURIComponent(raw.slice('file://'.length)) : raw
  if (!path) return
  const existing = editorModels.get(path)
  if (existing && existing.model && !existing.model.isDisposed()) return
  // 只读预览、非 master 节点：无法读取远端文件内容，跳过（保持原有降级）
  if (getWorkspaceTargetNodeId() !== 'master') return
  const content = await fetchFileContent(path)
  const spec = getServerByPath(path)
  const language = spec?.monacoLanguage || 'plaintext'
  let model = existing?.model
  if (!model || model.isDisposed()) {
    model = monaco.editor.createModel(content, language, monaco.Uri.file(path))
    model.__jarvisPath = path
  } else {
    model.setValue(content)
  }
  editorModels.set(path, { model, content, language })
}

/** 由文件路径推导 workspace 根目录（取所在目录，后端会校验其存在性）。 */
function resolveLspWorkspaceRoot(path) {
  const normalized = String(path || '')
  const idx = normalized.lastIndexOf('/')
  return idx > 0 ? normalized.slice(0, idx) : ''
}

/**
 * 释放某个文件绑定的 LSP 连接。
 * 仅当同一 (serverId, root) 已无其他文件在用时才真正关闭连接，
 * 避免频繁开关标签导致反复重启语言服务器。
 */
function releaseLspBinding(path) {
  const binding = lspBindings.get(path)
  if (!binding) return
  lspBindings.delete(path)

  for (const other of lspBindings.values()) {
    if (other.serverId === binding.serverId && other.root === binding.root) {
      return // 仍有其他文件在用同一连接
    }
  }
  disposeClient(binding.serverId, binding.root)
}

function resolveAgentRelativePath(relativePath, agentId = null) {
  if (!relativePath) return ''
  const raw = String(relativePath)
  // 绝对路径直接返回，不做 working_dir 拼接（否则会把绝对路径当相对路径拼出重复前缀）
  if (raw.startsWith('/')) return raw
  // 优先用指定 Agent 的工作目录解析（命令面板/搜索场景应使用其对应的 Agent，
  // 而非 currentAgent——两者可能不一致，导致拼出相对路径触发 Monaco「path must be absolute」）。
  let workingDir = ''
  if (agentId) {
    const agent = agentListGetter().value.find(a => a.agent_id === agentId)
    workingDir = agent?.working_dir || ''
  }
  if (!workingDir) workingDir = currentAgent().value?.working_dir || ''
  if (!workingDir) return raw
  return `${workingDir.replace(/\/$/, '')}/${raw.replace(/^\//, '')}`
}

async function fetchGlobalSearchResults(agentId, payload) {
  const { host, port } = getGatewayAddress()
  // 使用传入的agentId对应的node_id
  const agent = agentListGetter().value.find(a => a.agent_id === agentId)
  if (!agent) {
    throw new Error(`找不到Agent: ${agentId}`)
  }
  if (!agent.node_id) {
    throw new Error(`Agent没有node_id: ${agentId}`)
  }
  const targetNodeId = String(agent.node_id).trim()
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `global-search/${agentId}`), {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      node_id: targetNodeId,
    })
  })
  const result = await response.json()
  if (!response.ok || !result.success || !result.data) {
    throw new Error(result.error?.message || '全局搜索失败')
  }
  return result.data
}

async function fetchFileSearchResults(agentId, payload) {
  const { host, port } = getGatewayAddress()
  const agent = agentListGetter().value.find(a => a.agent_id === agentId)
  if (!agent) {
    throw new Error(`找不到Agent: ${agentId}`)
  }
  if (!agent.node_id) {
    throw new Error(`Agent没有node_id: ${agentId}`)
  }
  const targetNodeId = String(agent.node_id).trim()
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `file-search/${agentId}`), {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      node_id: targetNodeId,
    })
  })
  const result = await response.json()
  if (!response.ok || !result.success || !result.data) {
    throw new Error(result.error?.message || '文件名搜索失败')
  }
  return result.data
}

const hasWorkspaceSidebarFileTree = computed(() => {
  const agentId = activeWorkspaceSessionId.value
  if (!agentId) return false
  return getVisibleFileTreeNodes(agentId).length > 0
})

async function ensureWorkspaceSidebarFileTree(agent = activeWorkspaceSession.value?.agent) {
  if (!agent?.agent_id || !agent.working_dir) return
  const treeNodes = fileTreeState.value.get(agent.agent_id) || []
  if (treeNodes.length === 0) {
    await initFileTree(agent.agent_id, agent.working_dir)
  }
}

function setWorkspaceSidebarView(view) {
  workspaceSidebarView.value = view
  showWorkspaceSidebar.value = true
  if (view === 'files') {
    nextTick(() => {
      ensureWorkspaceSidebarFileTree()
      layoutMonacoEditor()
    })
    return
  }
  if (view === 'git') {
    // 切到 Git 视图时自动刷新提交历史与分支（每次切换都拉取最新，避免停留在旧数据）
    nextTick(() => {
      layoutMonacoEditor()
      layoutGitDiffEditor()
      if (!gitLogLoading.value) {
        refreshGitView()
      }
    })
    return
  }
  if (view === 'manage') {
    // 切到能力清单视图：数据缓存，避免频繁请求；仅首次打开（四个数据源均为空）时加载，
    // 之后靠侧边栏内「刷新」按钮手动刷新。
    // 注意：不能用 topologyDaemonSessions/topologyExtensionSessions 是否为空来判断——
    // 这两个 ref 与网络拓扑图共享，可能已被拓扑图轮询填充，导致 installedScripts/
    // gatewayScripts 永远不加载（网关脚本库区块不显示）。
    if (
      !topologyDaemonSessions.value.length &&
      !topologyExtensionSessions.value.length &&
      !manageInstalledScripts.value.length &&
      !manageGatewayScripts.value.length
    ) {
      refreshManageCapabilities()
    }
    nextTick(() => {
      layoutMonacoEditor()
    })
    return
  }
  if (view === 'timers') {
    // 切到定时任务视图：任务会变化，拉取最新列表（只读展示）
    refreshManageTimers()
    nextTick(() => {
      layoutMonacoEditor()
    })
    return
  }
  if (view === 'plugins') {
    // 切到插件视图：插件列表可能变化，拉取最新（组件内部通过 watch 自行加载）
    nextTick(() => {
      layoutMonacoEditor()
    })
    return
  }
  nextTick(() => {
    layoutMonacoEditor()
  })
}

// 活动栏按钮点击：已打开该侧边栏视图时再次点击则收起，否则切换到该视图。
function toggleWorkspaceSidebarView(view) {
  if (showWorkspaceSidebar.value && workspaceSidebarView.value === view) {
    closeWorkspaceSidebar()
    return
  }
  setWorkspaceSidebarView(view)
}

// 活动栏按钮点击（聊天室/终端）：已打开该主视图时再次点击则回到文件视图。
// 已统一为 pane 树：host 由某个 pane 承载（未分割时唯一 leaf 即承载 pane）。
function toggleWorkspaceMainView(view) {
  const hostedByPane = !!findWorkspacePaneByView(view)
  if (workspaceMainView.value === view || hostedByPane) {
    setWorkspaceMainView('file')
    return
  }
  setWorkspaceMainView(view)
}

// 切换编辑器主区域视图（file / chat / terminal）
function setWorkspaceMainView(view) {
  // 已统一为 pane 树：pane 树本身承载 file/session 内容，主区域视图恒为 file，
  // 因此这里不改 workspaceMainView、也不收起分割（会话显示在各自的 pane 中）。
  // 「收起」语义（切回 file）必须在此提前处理，否则会被下面的 workspaceMainView === view 早退吞掉。
  if (view === 'file') {
    // 收起：把承载 chat / terminal 的 pane 清成中性空白（host 单例，至多一个）
    const hostPane = findWorkspacePaneByView('chat') || findWorkspacePaneByView('terminal')
    if (hostPane) setActivePaneViewForPane(hostPane, 'empty')
    // 未分割（唯一 leaf）时若主区域不是文件视图，原地切回文件并重排 Monaco
    if (workspacePaneCount.value === 1 && workspaceMainView.value !== 'file') {
      setMainViewOnLeaf('file')
      nextTick(() => {
        layoutMonacoEditor()
        layoutGitDiffEditor()
      })
    }
    return
  }
  if (view === 'session') {
    // session 由 pane 承载：交给 ensurePaneForView 定位承载 pane（未分割时唯一 leaf 原地承载）
    ensurePaneForView('session', workspaceSessionPanelIdGetter().value)
    return
  }
  // chat / terminal：空则原地、已有则复用、否则分割（不覆盖当前区域）
  ensurePaneForView(view)
  return
}

// 在工作区中显示 chat / terminal（host 单例）：确保工作区面板已打开，再交给主区域或激活 pane 承载。
// 面板分离能力移除后，chat/terminal 只能在工作区内部渲染，因此任何「打开终端/聊天室」的入口
// 都必须走这里，而不是去改已废弃的 showTerminalPanel / showChatPanel 标志。
function showWorkspaceHostView(view) {
  if (!showWorkspacePanel.value) {
    showWorkspacePanel.value = true
    if (windowWidth.value <= 768) pushOverlayState()
  }
  setWorkspaceMainView(view)
}

// 让主区域回到「文件视图」（打开文件时调用）。
// 主区域的 file/chat/terminal/session 四种内容是互斥的，打开文件类内容必须先切回文件视图，
// 否则会被 chat/terminal/session 内容挡住。
function showWorkspaceFileView() {
  if (workspaceMainView.value !== 'file') {
    setMainViewOnLeaf('file')
  }
  // 切回后容器尺寸可能变化，重排 Monaco（含 diff），确保内容正确渲染
  nextTick(() => {
    layoutMonacoEditor()
    layoutGitDiffEditor()
  })
}

function toggleWorkspaceSearchSidebar() {
  if (showWorkspaceSidebar.value && workspaceSidebarView.value === 'search') {
    closeWorkspaceSidebar()
    return
  }
  setWorkspaceSidebarView('search')
}

function closeWorkspaceSidebar() {
  showWorkspaceSidebar.value = false
  // 侧栏收起不影响主区域 diff，仅重排主编辑器
  nextTick(() => {
    layoutMonacoEditor()
  })
}

function clearGlobalSearch() {
  globalSearchQuery.value = ''
  globalSearchFileGlob.value = ''
  globalSearchCaseSensitive.value = false
  globalSearchWholeWord.value = false
  globalSearchError.value = ''
  globalSearchResults.value = []
  fileSearchResults.value = []
  globalSearchTotalFiles.value = 0
  globalSearchTotalMatches.value = 0
  globalSearchExecuted.value = false
}

async function runGlobalSearch() {
  const searchAgentId = effectiveGlobalSearchAgentId().value
  if (!searchAgentId) {
    showToast('请先选择 Agent', 'error')
    return
  }

  const query = globalSearchQuery.value.trim()
  if (!query) {
    globalSearchError.value = '请输入搜索关键词'
    globalSearchExecuted.value = false
    globalSearchResults.value = []
    fileSearchResults.value = []
    setWorkspaceSidebarView('search')
    return
  }

  setWorkspaceSidebarView('search')
  globalSearchLoading.value = true
  globalSearchError.value = ''
  globalSearchExecuted.value = false

  try {
    if (globalSearchMode.value === 'filename') {
      const data = await fetchFileSearchResults(searchAgentId, {
        query,
        case_sensitive: globalSearchCaseSensitive.value,
        max_results: 200,
        file_glob: globalSearchFileGlob.value.trim(),
      })
      fileSearchResults.value = Array.isArray(data.results) ? data.results : []
      globalSearchTotalFiles.value = Number(data.total_files || 0)
      globalSearchTotalMatches.value = 0
      globalSearchExecuted.value = true
      return
    }
    const data = await fetchGlobalSearchResults(searchAgentId, {
      query,
      case_sensitive: globalSearchCaseSensitive.value,
      whole_word: globalSearchWholeWord.value,
      max_results: 100,
      file_glob: globalSearchFileGlob.value.trim(),
    })
    globalSearchResults.value = Array.isArray(data.results) ? data.results : []
    globalSearchTotalFiles.value = Number(data.total_files || 0)
    globalSearchTotalMatches.value = Number(data.total_matches || 0)
    globalSearchExecuted.value = true
  } catch (error) {
    globalSearchError.value = error.message || '全局搜索失败'
    globalSearchResults.value = []
    fileSearchResults.value = []
    globalSearchTotalFiles.value = 0
    globalSearchTotalMatches.value = 0
    globalSearchExecuted.value = true
    showToast(globalSearchError.value, 'error')
  } finally {
    globalSearchLoading.value = false
  }
}

function setGlobalSearchMode(mode) {
  if (globalSearchMode.value === mode) return
  globalSearchMode.value = mode
  globalSearchError.value = ''
  globalSearchExecuted.value = false
  globalSearchResults.value = []
  fileSearchResults.value = []
  globalSearchTotalFiles.value = 0
  globalSearchTotalMatches.value = 0
}

function openFileSearchResult(filePath) {
  openWorkspaceFile(resolveAgentRelativePath(filePath, effectiveGlobalSearchAgentId().value), effectiveGlobalSearchAgentId().value)
}

async function openGlobalSearchResult(filePath, lineNumber, matchStart = 0, matchEnd = matchStart) {
  const absolutePath = resolveAgentRelativePath(filePath, effectiveGlobalSearchAgentId().value)
  // 使用全局搜索侧边栏选中的 Agent
  await openWorkspaceFile(absolutePath, effectiveGlobalSearchAgentId().value)
  await nextTick()
  const modelData = editorModels.get(absolutePath)
  const view = getActiveWorkspaceView()
  if (!view || !modelData) {
    return
  }

  // Monaco: 通过 setPosition / setSelection + revealLineInCenter 定位
  const line = Number(lineNumber || 1)
  const col = Number(matchStart || 0) + 1
  const endCol = Math.max(col, Number(matchEnd || matchStart || 0) + 1)

  view.revealLineInCenter(line)
  view.setSelection(new monaco.Selection(line, col, line, endCol))
  view.setPosition({ lineNumber: line, column: col })
  view.focus()
}

async function fetchFileContent(path, agentId = null) {
  const { host, port } = getGatewayAddress()
  // 如果提供了agentId，使用对应的node_id；否则使用当前激活编辑器会话的node_id
  let targetNodeId
  if (agentId) {
    const agent = agentListGetter().value.find(a => a.agent_id === agentId) || getVirtualWorkspaceAgent(agentId)
    if (!agent) {
      throw new Error(`找不到Agent: ${agentId}`)
    }
    if (!agent.node_id) {
      throw new Error(`Agent没有node_id: ${agentId}`)
    }
    targetNodeId = String(agent.node_id).trim()
  } else {
    targetNodeId = getWorkspaceTargetNodeId()
  }
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-content'), {
    method: 'POST',
    body: JSON.stringify({ path, node_id: targetNodeId })
  })

  const result = await response.json()
  if (!response.ok || !result.success || !result.data) {
    throw new Error(result.error?.message || '读取文件失败')
  }
  return result.data.content || ''
}

async function fetchFileStat(path, agentId = null) {
  const { host, port } = getGatewayAddress()
  // 如果提供了agentId，使用对应的node_id；否则使用当前激活编辑器会话的node_id
  let targetNodeId
  if (agentId) {
    const agent = agentListGetter().value.find(a => a.agent_id === agentId) || getVirtualWorkspaceAgent(agentId)
    if (!agent) {
      throw new Error(`找不到Agent: ${agentId}`)
    }
    if (!agent.node_id) {
      throw new Error(`Agent没有node_id: ${agentId}`)
    }
    targetNodeId = String(agent.node_id).trim()
  } else {
    targetNodeId = getWorkspaceTargetNodeId()
  }
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-stat'), {
    method: 'POST',
    body: JSON.stringify({ path, node_id: targetNodeId })
  })

  const result = await response.json()
  if (!response.ok || !result.success || !result.data) {
    throw new Error(result.error?.message || '读取文件状态失败')
  }
  return result.data
}

async function refreshWorkspaceTabFromRemote(path, showAutoRefreshToast = false) {
  const tab = getWorkspaceTabByPath(path)
  if (!tab) return

  const [content, fileStat] = await Promise.all([
    fetchFileContent(path),
    fetchFileStat(path),
  ])

  tab.content = content
  tab.originalContent = content
  tab.isDirty = false
  tab.error = ''
  tab.externalModified = false
  updateWorkspaceTabFileStat(tab, fileStat)

  const modelData = editorModels.get(path)
  if (modelData && modelData.content !== content) {
    modelData.content = content
    // 模型是共享的：直接更新 model 内容，所有打开该文件的 pane 都会同步
    const model = modelData.model
    if (model && !model.isDisposed()) {
      model.setValue(content)
    }
  }

  if (showAutoRefreshToast) {
    showToast('检测到文件已更新，已自动刷新', 'info')
  }
}

async function checkActiveWorkspaceFileHeartbeat() {
  if (!showWorkspacePanel.value) return

  const tab = activeWorkspaceTab.value
  if (!tab || tab.loading || !tab.path) return

  try {
    const remoteFileStat = await fetchFileStat(tab.path)
    const remoteMtimeNs = remoteFileStat.mtime_ns ?? null
    const remoteFileSize = remoteFileStat.size ?? null
    const localMtimeNs = tab.mtimeNs ?? null
    const localFileSize = tab.fileSize ?? null
    const hasRemoteChange =
      remoteMtimeNs !== localMtimeNs || remoteFileSize !== localFileSize

    if (!hasRemoteChange) {
      if (!tab.isDirty && tab.externalModified) {
        tab.externalModified = false
      }
      return
    }

    if (tab.isDirty) {
      if (!tab.externalModified) {
        tab.externalModified = true
        tab.error = '文件已被外部修改，请先处理冲突后再保存'
        showToast('检测到文件外部变更，当前标签有未保存修改', 'error')
      }
      return
    }

    await refreshWorkspaceTabFromRemote(tab.path, true)
  } catch (error) {
    console.error('[EDITOR] File heartbeat check failed:', error)
  }
}

function stopWorkspaceFileHeartbeat() {
  if (workspaceFileHeartbeatTimer.value) {
    clearInterval(workspaceFileHeartbeatTimer.value)
    workspaceFileHeartbeatTimer.value = null
  }
}

function startWorkspaceFileHeartbeat() {
  stopWorkspaceFileHeartbeat()

  if (!showWorkspacePanel.value || !activeWorkspaceTab.value) {
    return
  }

  workspaceFileHeartbeatTimer.value = setInterval(() => {
    checkActiveWorkspaceFileHeartbeat()
  }, EDITOR_FILE_HEARTBEAT_INTERVAL)
}

async function openWorkspaceFile(path, agentId = null) {
  if (!path) return

  showWorkspacePanel.value = true
  // 智能定位打开位置（点击侧边文件）：
  //  1) 当前活动区域为空 → 在当前区域创建编辑器；
  //  2) 否则复用已打开的编辑器面板（不覆盖当前会话/聊天/终端）；
  //  3) 否则分割当前区域创建新编辑器。
  // 返回 paneId 表示已定位到某分割 pane；返回 null 表示走未分割的原地路径。
  const targetPaneId = ensureEditorPaneForFileOpen(agentId)
  // 打开文件属于「文件视图」：未分割且原地打开时，若主区域停在 chat/terminal/session，
  // 需先切回文件视图，否则文件（及 diff）会被这些内容挡住。
  // （已分割时由 ensureEditorPaneForFileOpen 负责定位到 file pane，无需再切。）
  if (!targetPaneId) {
    showWorkspaceFileView()
  }

  const existingTab = getWorkspaceTabByPath(path)
  if (existingTab) {
    // 已统一为 pane 树：把该文件登记到「激活 pane」的标签列表（同一文件可同时出现在多个 pane）
    addPaneTab(activePaneId.value, path)
    activateWorkspaceTab(path)
    return
  }

  const tab = reactive({
    path,
    name: path.split('/').pop() || path,
    content: '',
    originalContent: '',
    language: getLanguageFromFilename(path),
    isDirty: false,
    loading: true,
    error: '',
    externalModified: false,
    mtimeNs: null,
    fileSize: null,
  })
  const session = activeWorkspaceSession.value
  if (!session) {
    // 编辑器面板可能通过 Ctrl+E / 命令面板打开（只设 showWorkspacePanel，未创建会话）。
    // 此时按传入的 agentId 或当前 Agent 补建会话，避免点击文件静默无反应。
    // 注意：虚拟目录会话（未创建 Agent 时打开的目录）不在 agentList 中，且刷新后
    // activeWorkspaceSession 为空（restoreVirtualWorkspaceDirs 只恢复会话不激活），
    // 因此必须优先按 agentId 命中已存在的虚拟会话并激活，否则点击文件会静默无反应。
    const virtualSession = agentId
      ? workspaceSessions.value.find(s => s.agent_id === agentId && s.agent?.virtual === true)
      : null
    if (virtualSession) {
      activeWorkspaceSessionId.value = agentId
    } else {
      const targetAgent = (agentId && agentListGetter().value.find(a => a.agent_id === agentId))
        || getCurrentAgentOrNull()
      if (!targetAgent) return
      createWorkspaceForAgent(targetAgent)
      if (!activeWorkspaceSession.value) return
    }
  }
  const activeSession = activeWorkspaceSession.value
  activeSession.tabs.push(tab)
  activeSession.activeTabPath = path
  // 已统一为 pane 树：新文件登记到「激活 pane」的标签列表
  addPaneTab(activePaneId.value, path)

  try {
    const [content, fileStat] = await Promise.all([
      fetchFileContent(path, agentId),
      fetchFileStat(path, agentId),
    ])
    tab.content = content
    tab.originalContent = content
    tab.externalModified = false
    updateWorkspaceTabFileStat(tab, fileStat)
    tab.loading = false

    let modelData = editorModels.get(path)
    if (!modelData) {
      modelData = { model: null, content, language: getLanguageExtension(tab.language) }
      editorModels.set(path, modelData)
    }
    modelData.content = content

    await nextTick()
    // 确保编辑器容器存在（当从无标签状态打开时需要等待DOM更新）
    let retryCount = 0
    while (!editorContainerRef.value && retryCount < 10) {
      await new Promise(resolve => setTimeout(resolve, 50))
      retryCount++
    }
    ensureMonacoEditor()
    activateWorkspaceTab(path)
  } catch (error) {
    tab.loading = false
    tab.error = error.message || '读取文件失败'
  }
}

async function saveWorkspaceTab(path) {
  const tab = getWorkspaceTabByPath(path)
  if (!tab) return

  const modelData = editorModels.get(path)
  const content = modelData ? modelData.content : tab.content

  const { host, port } = getGatewayAddress()
  const targetNodeId = getWorkspaceTargetNodeId()
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-write'), {
    method: 'POST',
    body: JSON.stringify({ path, content, node_id: targetNodeId })
  })
  const result = await response.json()

  if (!response.ok || !result.success) {
    const message = result.error?.message || '保存文件失败'
    tab.error = message
    showToast(message, 'error')
    return
  }

  tab.originalContent = content
  tab.content = content
  tab.isDirty = false
  tab.error = ''
  tab.externalModified = false

  try {
    const fileStat = await fetchFileStat(path)
    updateWorkspaceTabFileStat(tab, fileStat)
  } catch (error) {
    console.error('[EDITOR] Failed to refresh file stat after save:', error)
  }

  showToast(`${getNodeDisplayName(targetNodeId)}节点的${path}已保存`, 'success')
}

async function saveActiveWorkspaceTab() {
  if (!activeWorkspaceTab.value) return
  await saveWorkspaceTab(activeWorkspaceTab.value.path)
}

// 保存指定 pane 当前绑定的文件（每个 pane 内的保存按钮调用）
async function savePaneWorkspaceFile(paneId) {
  const path = workspaceViewPanes.get(paneId)
  if (!path) return
  await saveWorkspaceTab(path)
}

function toggleWorkspaceEditable() {
  isWorkspaceEditable.value = !isWorkspaceEditable.value
  for (const [, view] of editorViews) {
    view.updateOptions({ readOnly: !isWorkspaceEditable.value })
  }
}

function hasDirtyWorkspaceTabs() {
  return workspaceTabs.value.some(tab => tab.isDirty)
}

function confirmCloseWorkspacePanel() {
  return new Promise((resolve) => {
    showConfirm(
      '存在未保存标签，确定关闭编辑器吗？',
      () => resolve(true),
      () => resolve(false),
      false
    )
  })
}

// 编辑器主区域正承载终端/聊天时，对应独立面板的显示状态是被内嵌取代的遗留值；
// 关闭编辑器前需复位，否则独立面板会「凭空」浮现（如编辑器内新建终端后关闭编辑器）。
// 同时复位主区域视图，避免下次打开编辑器直接进入终端/聊天视图。
function resetWorkspaceHostedPanelState() {
  if (workspaceHostsTerminal().value) showTerminalPanel.value = false
  if (workspaceHostsChat().value) showChatPanel.value = false
  setMainViewOnLeaf('file')
  // 关闭编辑器时一并收起自由分割，避免下次打开残留多 pane 布局
  if (workspacePaneCount.value > 1) collapseWorkspacePanes()
  // 内嵌会话 Panel 只在编辑器内部渲染：编辑器关闭后它们失去宿主，
  // 若继续留在 panels 中会既不可见、又让 hasNoPanel 恒为 false（宠物大厅不显示）。
  // 因此关闭编辑器时一并关闭所有会话 Panel。
  for (const panel of [...panelsGetter().value]) {
    closePanelGetter()(panel.id)
  }
  workspaceSessionPanelIdGetter().value = null
}

// 「关闭编辑器」只是隐藏：保留主区域视图、自由分割布局、会话 Panel 与 diff 数据，
// 使再次打开时恢复关闭前的状态。这里只做「避免独立终端/聊天面板凭空浮现」的必要清理
// （编辑器内嵌承载时，独立面板的显示状态是被取代的遗留值，关闭编辑器后需复位）。
// 注意：必须在 showWorkspacePanel 置 false 之前调用，否则 workspaceHosts* 已为 false，
// 独立面板不会被收起。
function hideWorkspaceHostedPanelState() {
  if (workspaceHostsTerminal().value) showTerminalPanel.value = false
  if (workspaceHostsChat().value) showChatPanel.value = false
}

async function closeWorkspacePanel() {
  if (hasDirtyWorkspaceTabs()) {
    const confirmed = await confirmCloseWorkspacePanel()
    if (!confirmed) return
  }

  hideWorkspaceHostedPanelState()
  showWorkspacePanel.value = false
}

// 为 Agent 创建/打开编辑器会话
function createWorkspaceForAgent(agent) {
  if (!socket.value) {
    console.warn('[workspace-session] No socket connection')
    return
  }

  const agentId = agent.agent_id
  const agentName = agent.name || agent.agent_type

  // 检查是否已存在该 Agent 的编辑器会话
  let session = workspaceSessions.value.find(s => s.agent_id === agentId)
  if (!session) {
    // 创建新的编辑器会话
    session = {
      agent_id: agentId,
      agent_name: agentName,
      agent: agent,
      tabs: [],
      activeTabPath: null,
      editorModels: new Map(),
      isEditable: false,
      showSidebar: true,
      sidebarView: 'files'
    }
    workspaceSessions.value.push(session)
  }

  // 切换到该会话
  activeWorkspaceSessionId.value = agentId
  showWorkspacePanel.value = true

}

// 虚拟目录会话的 agent_id 前缀：未创建 Agent 时直接打开某节点的目录
const VIRTUAL_WORKSPACE_PREFIX = '__node__:'

// 已打开目录记录的持久化 key：刷新后自动恢复，无需重新添加。
// 仅存 node_id + working_dir（agent_id 由二者推导），避免持久化整个会话对象。
const VIRTUAL_DIRS_STORAGE_KEY = 'jarvis_virtual_workspace_dirs'

// 从虚拟会话的 agent_id 还原出伪 agent 信息（含 node_id/working_dir），供文件树与文件读写复用
function getVirtualWorkspaceAgent(agentId) {
  const key = String(agentId || '')
  if (!key.startsWith(VIRTUAL_WORKSPACE_PREFIX)) return null
  const session = workspaceSessions.value.find(s => s.agent_id === key)
  return session?.agent || null
}

// 目录树/文件操作统一取 agent：优先真实 Agent，其次虚拟目录会话
function resolveFileTreeAgent(agentId) {
  return agentListGetter().value.find(a => a.agent_id === agentId) || getVirtualWorkspaceAgent(agentId)
}

// 由文件的绝对路径反查其所属的目录树 Agent（真实 Agent 或虚拟目录会话）：
// 按 working_dir 前缀匹配，取最长前缀者（避免嵌套目录下命中父目录 Agent）；
// 前缀长度相同时优先活跃 Agent，避免命中同目录下已停止的旧 Agent。
// 返回 { agentId, agent } 或 null。
function resolveAgentForPath(path) {
  const raw = String(path || '')
  if (!raw) return null
  const candidates = []
  // 真实 Agent：附带其是否已停止（虚拟目录会话无「停止」概念，视为活跃）
  for (const agent of agentListGetter().value) {
    if (agent?.agent_id && agent.working_dir) {
      candidates.push({ agent, stopped: isStoppedAgent(agent) })
    }
  }
  for (const session of virtualWorkspaceSessions.value) {
    if (session?.agent?.agent_id && session.agent.working_dir) {
      candidates.push({ agent: session.agent, stopped: false })
    }
  }
  let best = null
  let bestLen = -1
  let bestStopped = true
  for (const { agent, stopped } of candidates) {
    const dir = String(agent.working_dir).replace(/\/+$/, '')
    if (!dir) continue
    if (raw === dir || raw.startsWith(`${dir}/`)) {
      // 更长前缀优先；同长度时活跃 Agent 优先于已停止 Agent
      if (dir.length > bestLen || (dir.length === bestLen && bestStopped && !stopped)) {
        best = agent
        bestLen = dir.length
        bestStopped = stopped
      }
    }
  }
  return best ? { agentId: best.agent_id, agent: best } : null
}

// 读取持久化的「已打开目录」记录
function loadVirtualWorkspaceDirs() {
  try {
    const raw = localStorage.getItem(VIRTUAL_DIRS_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(item => item && item.node_id && item.working_dir)
      .map(item => ({ node_id: String(item.node_id), working_dir: String(item.working_dir) }))
  } catch (e) {
    return []
  }
}

// 把当前虚拟目录会话写回 localStorage（以实际会话为准，移除后自然消失）
function saveVirtualWorkspaceDirs() {
  try {
    const dirs = virtualWorkspaceSessions.value
      .map(s => ({
        node_id: String(s.agent?.node_id || '').trim(),
        working_dir: String(s.agent?.working_dir || '').trim(),
      }))
      .filter(item => item.node_id && item.working_dir)
    localStorage.setItem(VIRTUAL_DIRS_STORAGE_KEY, JSON.stringify(dirs))
  } catch (e) {
    // localStorage 不可用（隐私模式 / 配额满）时静默降级
  }
}

// 创建或复用某节点的虚拟目录会话，返回 { agentId, agent }
// 注意：agent_id 由「节点 + 目录」共同决定（同一节点可同时打开多个目录），
// 因此这里不能只按节点生成 id，否则同节点再次打开别的目录会复用并覆盖上一个会话。
function ensureVirtualWorkspaceSession(nodeId, dirPath) {
  const targetNodeId = String(nodeId || 'master').trim() || 'master'
  const targetDir = String(dirPath || '').trim()
  if (!targetDir) return null

  const agentId = `${VIRTUAL_WORKSPACE_PREFIX}${targetNodeId}:${targetDir}`
  // 节点名 + 目录名，便于在目录树中区分同一节点下的多个目录
  const dirLabel = targetDir.replace(/\/+$/, '').split('/').pop() || targetDir
  const virtualAgent = {
    agent_id: agentId,
    name: `${getNodeDisplayName(targetNodeId)} · ${dirLabel}`,
    node_id: targetNodeId,
    working_dir: targetDir,
    agent_type: 'virtual_dir',
    virtual: true
  }

  let session = workspaceSessions.value.find(s => s.agent_id === agentId)
  if (!session) {
    session = {
      agent_id: agentId,
      agent_name: virtualAgent.name,
      agent: virtualAgent,
      tabs: [],
      activeTabPath: null,
      editorModels: new Map(),
      isEditable: false,
      showSidebar: true,
      sidebarView: 'files'
    }
    workspaceSessions.value.push(session)
  } else {
    // 复用已有虚拟会话时刷新节点与目录
    session.agent = virtualAgent
    session.agent_name = virtualAgent.name
  }
  return { agentId, agent: virtualAgent }
}

// 打开「某节点的某目录」为编辑器工作区（不需要先创建 Agent）
async function openWorkspaceDir(nodeId, dirPath) {
  const created = ensureVirtualWorkspaceSession(nodeId, dirPath)
  if (!created) return
  const { agentId, agent: virtualAgent } = created

  activeWorkspaceSessionId.value = agentId
  showWorkspacePanel.value = true
  setActivePaneView('file')
  showWorkspaceFileView()
  workspaceSidebarView.value = 'files'

  // 初始化该目录的文件树
  await initFileTree(agentId, virtualAgent.working_dir)
  // 记录持久化，刷新后自动恢复
  saveVirtualWorkspaceDirs()
  showToast(`已打开目录：${virtualAgent.working_dir}`, 'success')
}

// 移除一个已打开的目录（关闭其虚拟会话并清理文件树状态），并同步持久化记录
function removeWorkspaceDir(agentId) {
  const index = workspaceSessions.value.findIndex(s => s.agent_id === agentId)
  if (index === -1) return
  const session = workspaceSessions.value[index]
  if (session.agent?.virtual !== true) return

  // 清理该会话的文件树 / 展开态 / 加载态
  fileTreeState.value.delete(agentId)
  fileTreeExpanded.value.delete(agentId)
  fileTreeLoading.value.delete(agentId)
  expandedAgents.value.delete(agentId)
  if (fileTreeSelectedAgentId.value === agentId) {
    fileTreeSelectedAgentId.value = null
    fileTreeSelectedPath.value = null
  }
  if (selectedAgentId.value === agentId) selectedAgentId.value = null

  // 释放编辑器模型
  session.editorModels?.clear()

  workspaceSessions.value.splice(index, 1)
  // 若移除的是当前激活会话，切到剩余的第一个会话；没有则清空激活态。
  // 注意：这里只移除一个目录条目，工作区面板本身要继续保留（面板是承载目录树的容器），
  // 不能像关闭编辑器会话那样把整个面板收起，否则用户会误以为「移除目录 = 关闭工作区」。
  if (activeWorkspaceSessionId.value === agentId) {
    activeWorkspaceSessionId.value = workspaceSessions.value.length > 0
      ? workspaceSessions.value[0].agent_id
      : null
    if (!activeWorkspaceSessionId.value) {
      // 无剩余会话时仅复位主区域视图/分割/内嵌会话面板，面板保持打开并显示占位提示
      resetWorkspaceHostedPanelState()
    }
  }
  triggerRef(expandedAgents)
  saveVirtualWorkspaceDirs()
  showToast('已移除目录', 'success')
}

// 刷新后恢复上次打开的目录记录（在连接成功、鉴权可用后调用）
async function restoreVirtualWorkspaceDirs() {
  const dirs = loadVirtualWorkspaceDirs()
  if (!dirs.length) return
  for (const dir of dirs) {
    const created = ensureVirtualWorkspaceSession(dir.node_id, dir.working_dir)
    if (!created) continue
    // 仅恢复会话与文件树，不抢占当前激活会话、不弹提示
    await initFileTree(created.agentId, created.agent.working_dir)
  }
}


// 关闭编辑器会话
async function closeWorkspaceSession(agentId) {
  const sessionIndex = workspaceSessions.value.findIndex(s => s.agent_id === agentId)
  if (sessionIndex === -1) return

  const session = workspaceSessions.value[sessionIndex]

  // 检查是否有未保存的标签
  const hasDirty = session.tabs.some(tab => tab.isDirty)
  if (hasDirty) {
    const confirmed = await new Promise((resolve) => {
      showConfirm(
        `${session.agent_name} 的编辑器存在未保存修改，确定关闭吗？`,
        () => resolve(true),
        () => resolve(false),
        false
      )
    })
    if (!confirmed) return
  }

  // 清理编辑器模型
  session.editorModels.clear()

  // 从数组中移除
  workspaceSessions.value.splice(sessionIndex, 1)

  // 如果关闭的是当前激活的会话，切换到另一个
  if (activeWorkspaceSessionId.value === agentId) {
    activeWorkspaceSessionId.value = workspaceSessions.value.length > 0 ? workspaceSessions.value[0].agent_id : null
    if (!activeWorkspaceSessionId.value) {
      // 与 closeWorkspacePanel 一致：编辑器承载终端/聊天时，关闭编辑器需一并收起其独立面板状态
      resetWorkspaceHostedPanelState()
      showWorkspacePanel.value = false
    }
  }

}

// 切换编辑器会话
function switchWorkspaceSession(agentId) {
  const session = workspaceSessions.value.find(s => s.agent_id === agentId)
  if (!session) return

  activeWorkspaceSessionId.value = agentId
  showWorkspacePanel.value = true
}

function confirmCloseDirtyWorkspaceTab(path) {
  return new Promise((resolve) => {
    showConfirm(
      '该标签存在未保存修改，确定关闭吗？',
      () => resolve(true),
      () => resolve(false),
      false
    )
  })
}

// skipDirtyConfirm：批量关闭（标签栏右键菜单）时调用方已统一确认过一次，
// 避免每个脏标签再逐个弹窗。
async function closeWorkspaceTab(path, paneId = null, skipDirtyConfirm = false) {
  const tab = getWorkspaceTabByPath(path)
  if (!tab) return

  if (tab.isDirty && !skipDirtyConfirm) {
    const confirmed = await confirmCloseDirtyWorkspaceTab(path)
    if (!confirmed) return
  }

  // 已统一为 pane 树：指定了 pane 时只从该 pane 的标签列表移除。
  // 若该文件仍被其他 pane 引用，则不销毁模型、也不从全局 tabs 移除，
  // 其他 pane 的编辑器保持原样（这正是「关闭一个 pane 的标签不影响另一个」的关键）。
  let closedFromPane = false
  if (paneId) {
    closedFromPane = true
    removePaneTab(paneId, path)
    const panePaths = workspacePaneTabs.get(paneId) || []
    if (workspaceViewPanes.get(paneId) === path) {
      const nextPath = panePaths[panePaths.length - 1] || null
      if (nextPath) {
        activateWorkspaceTab(nextPath)
      } else {
        workspaceViewPanes.delete(paneId)
        const view = editorViews.get(paneId)
        if (view) view.setModel(null)
      }
    }
    if (isPathReferencedByAnyPane(path)) return
    // 没有其他 pane 引用该文件：继续走下方全局清理（释放模型 / LSP / 全局 tab）
  }

  const session = activeWorkspaceSession.value
  if (!session) return
  const index = session.tabs.findIndex(item => item.path === path)
  if (index === -1) return

  const wasActive = session.activeTabPath === path
  session.tabs.splice(index, 1)

  const modelData = editorModels.get(path)
  if (modelData) {
    if (modelData.model && !modelData.model.isDisposed()) {
      modelData.model.dispose()
    }
    editorModels.delete(path)
  }

  // 释放该文件绑定的 LSP client（若该 server 无其他文件在用，则关闭连接）
  releaseLspBinding(path)

  if (wasActive) {
    const nextTab = session.tabs[index] || session.tabs[index - 1] || null
    // 从某个 pane 关闭标签时，该 pane 的「下一个标签 / 清空」已在上面处理完毕；
    // 这里若再激活全局下一个标签，会把别的 pane 的文件错误地绑到该 pane 上。
    if (closedFromPane) {
      // 该 pane 的视图已在上方处理；这里只把全局「激活文件」修正为仍存在的标签，
      // 避免它继续指向已删除的 path。
      session.activeTabPath = nextTab ? nextTab.path : null
    } else if (nextTab) {
      activateWorkspaceTab(nextTab.path)
    } else {
      session.activeTabPath = null
      // 不销毁编辑器实例，保留编辑器和容器 DOM，
      // 否则 v-if/v-else 切换会导致 editorContainerRef 消失，
      // 后续打开文件时无法重新创建编辑器。
      // 仅清空模型即可（所有 pane 的实例一并清空）。
      for (const [pid, view] of editorViews) {
        view.setModel(null)
        workspaceViewPanes.delete(pid)
      }
    }
  }
}

// ===== 编辑器标签栏右键菜单：关闭右侧所有 / 关闭所有 / 仅保留当前 =====
// paneId 为 null 表示未分割态（标签栏由全局 workspaceTabs 驱动，渲染在 WorkspacePanel.vue）；
// 否则为该 pane 的独立标签列表（getPaneTabs）。
const tabContextMenu = ref({ visible: false, x: 0, y: 0, paneId: null, path: '' })

function closeTabContextMenu() {
  if (tabContextMenu.value.visible) {
    tabContextMenu.value = { ...tabContextMenu.value, visible: false }
  }
}

function openTabContextMenu(paneId, path, event) {
  if (!path) return
  tabContextMenu.value = {
    visible: true,
    x: event?.clientX || 0,
    y: event?.clientY || 0,
    paneId: paneId || null,
    path,
  }
  // 点击空白处关闭（与目录树右键菜单同款：pointerdown 一次即解绑）
  document.addEventListener('pointerdown', closeTabContextMenu, { once: true })
}

// 当前右键菜单对应的标签 path 列表（按显示顺序）
function getTabContextPaths() {
  const menu = tabContextMenu.value
  if (menu.paneId) return getPaneTabs(menu.paneId).map(t => t.path)
  return workspaceTabs.value.map(t => t.path)
}

const tabContextActions = computed(() => {
  const paths = getTabContextPaths()
  const index = paths.indexOf(tabContextMenu.value.path)
  const hasRight = index >= 0 && index < paths.length - 1
  const hasOthers = paths.length > 1
  const canReveal = !!resolveAgentForPath(tabContextMenu.value.path)
  return [
    { id: 'reveal-in-tree', icon: '⌖', label: '在文件树中显示', enabled: canReveal },
    { id: 'close-right', icon: '⇥', label: '关闭右侧所有', enabled: hasRight },
    { id: 'close-all', icon: '✕', label: '关闭所有', enabled: hasOthers },
    { id: 'keep-current', icon: '◎', label: '仅保留当前', enabled: hasOthers },
  ]
})

async function runTabContextAction(act) {
  if (!act || act.enabled === false) return
  const menu = { ...tabContextMenu.value }
  const paneId = menu.paneId
  const paths = getTabContextPaths()
  const index = paths.indexOf(menu.path)
  if (index === -1) {
    closeTabContextMenu()
    return
  }

  let targets = []
  if (act.id === 'reveal-in-tree') {
    closeTabContextMenu()
    await revealTabInFileTree(menu.path)
    return
  }
  if (act.id === 'close-right') {
    targets = paths.slice(index + 1)
  } else if (act.id === 'close-all') {
    targets = paths.slice()
  } else if (act.id === 'keep-current') {
    targets = paths.filter(p => p !== menu.path)
  }
  closeTabContextMenu()
  if (!targets.length) return

  // 批量关闭：若其中含未保存标签，统一确认一次（避免逐个弹窗）
  const dirtyCount = targets.filter(p => getWorkspaceTabByPath(p)?.isDirty).length
  if (dirtyCount > 0) {
    const confirmed = await new Promise((resolve) => {
      showConfirm(
        `有 ${dirtyCount} 个标签存在未保存修改，确定关闭吗？`,
        () => resolve(true),
        () => resolve(false),
        false
      )
    })
    if (!confirmed) return
  }

  // 逐个关闭（closeWorkspaceTab 内部已处理模型/LSP/pane 绑定清理）；
  // 脏标签已在上方统一确认过，这里跳过逐个确认。
  for (const path of targets) {
    await closeWorkspaceTab(path, paneId, true)
  }
}

// 在左侧文件树中定位并高亮某个已打开文件（类似 VSCode 的 Reveal in Explorer）：
// 1) 反查文件所属 Agent/虚拟目录会话；2) 打开侧边栏并切到「文件」视图；
// 3) 展开 Agent 节点；4) 按路径逐级展开目录（必要时按需加载子节点）；
// 5) 选中并滚动到该文件节点。

// 通用 UI 图标（自绘 stroke 线性 SVG，currentColor 继承主题色）
const UI_ICONS = {
  folder: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 4.5v7a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H8.2L6.7 4.5H2.5a1 1 0 0 0-1 1z"/></svg>',
  monitor: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="2.5" width="12" height="8.5" rx="1.5"/><path d="M6 13.5h4M8 11v2.5"/></svg>',
  search: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3.5 3.5"/></svg>',
  save: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 2.5h9l1.5 1.5v9.5a1 1 0 0 1-1 1h-10a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1z"/><path d="M5 2.5v4h5v-4M5 13.5v-5h6v5"/></svg>',
  lock: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/></svg>',
  unlock: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 4.9-.8"/></svg>',
  receipt: '<svg viewBox="0 0 16 16" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.5h8v13l-1.5-1-1.5 1-1.5-1-1.5 1-1.5-1z"/><path d="M6 5.5h4M6 8h4M6 10.5h2.5"/></svg>',
  folderStack: '<svg viewBox="0 0 16 16" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 4.5v7a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H8.2L6.7 4.5H3.5a1 1 0 0 0-1 1z"/><path d="M5 13v.5a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V7.5"/></svg>',
  eye: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/></svg>',
  eyeOff: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><path d="M4 4 12 12M8 6.5a1.5 1.5 0 0 1 1.5 1.5"/></svg>',
}
// 细粒度扩展名 → 图标文件映射（图标源：material-icon-theme，位于 public/file-icons/）

// 取当前选中的文本，用于打开全局搜索时预填搜索框。
// 优先取 Monaco 编辑器选区（编辑器聚焦时），否则回退到页面 DOM 选区
// （如会话输出 / 聊天内容里选中的文字）。返回折叠空白后的单行文本，无选中返回空串。
function getSelectedTextForSearch() {
  let raw = ''
  const view = getActiveWorkspaceView()
  if (view && typeof view.getSelection === 'function') {
    const selection = view.getSelection()
    const model = view.getModel()
    if (selection && model && !selection.isEmpty()) {
      raw = model.getValueInRange(selection)
    }
  }
  if (!raw) {
    const domSelection = window.getSelection && window.getSelection()
    if (domSelection) raw = domSelection.toString()
  }
  // 搜索框是单行输入：把选区里的换行/连续空白折叠为单个空格，避免多行内容撑坏查询
  return raw.replace(/\s+/g, ' ').trim()
}

// 切到编辑器侧边栏的全局搜索并聚焦输入框（mode 为 'content' 内容搜索 / 'filename' 文件名搜索）。
// 若当前有选中文字，则预填到搜索框（选中内容优先于原有查询）。
function openWorkspaceGlobalSearch(mode = 'content') {
  if (!showWorkspacePanel.value) return
  setWorkspaceSidebarView('search')
  setGlobalSearchMode(mode)
  const selectedText = getSelectedTextForSearch()
  if (selectedText) globalSearchQuery.value = selectedText
  nextTick(() => {
    const input = document.querySelector('.workspace-global-search-input')
    if (input) input.focus()
  })
}
  return {
    EDITOR_FONT_FAMILY,
    UI_ICONS,
    activateWorkspaceTab,
    activeWorkspaceTab,
    bindWorkspaceViewEvents,
    clamp,
    clearGlobalSearch,
    closeWorkspacePanel,
    closeWorkspaceSidebar,
    closeWorkspaceTab,
    createWorkspaceForAgent,
    diffContainerRefs,
    diffEditorViews,
    editorViews,
    ensureMonacoEditor,
    ensureWorkspacePanelInViewport,
    ensureWorkspaceSidebarFileTree,
    fetchFileContent,
    fetchFileSearchResults,
    focusWindow,
    getActiveWorkspaceView,
    getPaneTabs,
    getVirtualWorkspaceAgent,
    getWorkspaceTabByPath,
    hideWorkspaceHostedPanelState,
    layoutMonacoEditor,
    lspBindings,
    openFileSearchResult,
    openGlobalSearchResult,
    openTabContextMenu,
    openWorkspaceDir,
    openWorkspaceFile,
    openWorkspaceGlobalSearch,
    remountMonacoEditor,
    removeWorkspaceDir,
    resolveAgentForPath,
    resolveAgentRelativePath,
    resolveDiffContainer,
    resolveFileTreeAgent,
    restoreVirtualWorkspaceDirs,
    runGlobalSearch,
    runTabContextAction,
    saveActiveWorkspaceTab,
    savePaneWorkspaceFile,
    scheduleWorkspaceLayout,
    setDiffContainerRef,
    setGlobalSearchMode,
    setWorkspaceMainView,
    setWorkspaceSidebarView,
    showWorkspaceHostView,
    startWorkspaceFileHeartbeat,
    startWorkspacePanelMove,
    startWorkspacePanelResize,
    startWorkspaceSidebarResize,
    stopWorkspaceFileHeartbeat,
    stopWorkspacePanelInteraction,
    tabContextActions,
    tabContextMenu,
    toggleWorkspaceEditable,
    toggleWorkspaceMainView,
    toggleWorkspaceMaximize,
    toggleWorkspaceSidebarView,
    workspacePaneTabs,
    workspacePaneTabsVersion,
    workspacePanelStyle,
    workspaceViewPanes,
  }
}
