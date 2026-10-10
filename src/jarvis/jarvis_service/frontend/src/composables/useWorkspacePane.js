// 工作区 pane 树 / 自由分割 / 侧边栏 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 10 PR-2，原 2948-4098 行），
// 保持行为完全一致：
// - workspace 面板状态：workspacePanelRect / workspacePanelInteraction / workspacePanelRef /
//   isWorkspaceMaximized / workspacePanelRectBeforeMaximize / splitWorkspaceContainerRefs /
//   editorContainerRef / workspaceSessions / activeWorkspaceSessionId / workspaceTabs /
//   activeWorkspaceTabPath / activeWorkspaceSession / virtualWorkspaceSessions / editorModels /
//   workspaceFileHeartbeatTimer / isWorkspaceEditable / EDITOR_FILE_HEARTBEAT_INTERVAL /
//   globalSearch* / fileSearchResults / showWorkspaceSidebar / workspaceSidebarView / workspaceMainView
// - pane 树核心：workspacePaneTree / activePaneId / maximizedPaneId / workspacePaneCount /
//   canSplitWorkspacePane / activePane / findWorkspacePaneById / ... / restoreWorkspacePaneLayout /
//   restoreWorkspacePaneContents
// - 插件前端扩展：内部调用 usePlugins（返回 pluginExtensions 等供模板/外部使用）
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - 直传（定义在本 composable 调用点之前）：fetchWithAuth / getGatewayAddress / getHttpProtocol /
//   hasAuthToken / windowWidth / clamp / focusWindow / getWorkspaceTabByPath / activeWorkspaceTab /
//   editorViews / workspaceViewPanes /
//   diffEditorViews / workspacePaneTabs / workspacePaneTabsVersion / remountMonacoEditor /
//   scheduleWorkspaceLayout / layoutMonacoEditor / activateWorkspaceTab / openWorkspaceFile /
//   layoutGitDiffEditor / disposeDiffEditorForPane / disposeAllDiffEditors / loadDiffForPane（getter 注入）
// - getter 注入（定义在调用点之后，内部通过 xxx() 二次求值）：panels / activePanelId /
//   closePanel / getPanelAgent / workspaceSessionPanelId / agentList / gitAgentId / switchAgent /
//   activeTerminalId / terminalSessions / restoreTerminalSessions / focusFirstIn
import { computed, nextTick, ref, triggerRef, watch } from 'vue'
import { usePlugins } from './usePlugins.js'
import { fetchPluginExtensions, loadExtensionComponent } from '../pluginExtensions.js'
export function useWorkspacePane({
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
}) {

const EDITOR_PANEL_MIN_WIDTH = 360
const EDITOR_PANEL_MIN_HEIGHT = 260
const EDITOR_PANEL_STORAGE_KEY = 'jarvis_workspace_panel_rect'
const workspaceResizeDirections = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
const PANEL_DRAG_ACTIVATION_DISTANCE = 4

// 窗口最大化状态
const isWorkspaceMaximized = ref(false)
const workspacePanelRectBeforeMaximize = ref(null)

function getDefaultWorkspacePanelRect() {
  return {
    top: 88,
    left: Math.max(window.innerWidth - 824, 16),
    width: 800,
    height: 600,
  }
}

function loadWorkspacePanelRect() {
  const defaultWorkspacePanelRect = getDefaultWorkspacePanelRect()
  const savedValue = localStorage.getItem(EDITOR_PANEL_STORAGE_KEY)
  if (!savedValue) {
    return defaultWorkspacePanelRect
  }

  try {
    const parsedValue = JSON.parse(savedValue)
    if (
      typeof parsedValue.top !== 'number' ||
      typeof parsedValue.left !== 'number' ||
      typeof parsedValue.width !== 'number' ||
      typeof parsedValue.height !== 'number'
    ) {
      return defaultWorkspacePanelRect
    }

    return parsedValue
  } catch {
    return defaultWorkspacePanelRect
  }
}

function saveWorkspacePanelRect() {
  localStorage.setItem(EDITOR_PANEL_STORAGE_KEY, JSON.stringify(workspacePanelRect.value))
}

const workspacePanelRect = ref(loadWorkspacePanelRect())
const workspacePanelInteraction = ref({
  active: false,
  mode: null,
  direction: null,
  startX: 0,
  startY: 0,
  startTop: 0,
  startLeft: 0,
  startWidth: 0,
  startHeight: 0,
})
const workspacePanelRef = ref(null)
// 自由分割：每个 file pane 各有一个 Monaco 容器（paneId -> hostEl）。
// 注意：容器的 ref 回调在 Vue 渲染提交阶段执行，可能晚于 splitWorkspacePane 里的 nextTick，
// 因此这里在容器挂载后主动调度一次实例补齐（scheduleWorkspaceLayout 用 rAF 合并），
// 不能只依赖调用方在 nextTick 里调 remountMonacoEditor。
const splitWorkspaceContainerRefs = ref(new Map())
function setSplitWorkspaceContainerRef(paneId, el) {
  if (!paneId) return
  if (el) {
    if (splitWorkspaceContainerRefs.value.get(paneId) === el) return
    splitWorkspaceContainerRefs.value.set(paneId, el)
  } else {
    if (!splitWorkspaceContainerRefs.value.has(paneId)) return
    splitWorkspaceContainerRefs.value.delete(paneId)
  }
  triggerRef(splitWorkspaceContainerRefs)
  // 容器挂载/卸载后主动补齐实例。此处不判断 pane 数量：ref 回调可能早于
  // workspacePaneTree 变更引起的 computed 重算，判断会漏掉「首次分割」这一次。
  scheduleWorkspaceLayout()
}
// 激活 pane 的 Monaco 容器；激活 pane 非 file 时回退到任一 file pane 容器，
// 保证「打开文件」等操作仍有可用容器。优先取文档中真实挂载的元素（ref 元素可能是
// 渲染中间态，已脱离文档）。
const splitWorkspaceContainerRef = computed(() => {
  const active = splitWorkspaceContainerRefs.value.get(activePaneId.value)
  if (active && active.isConnected) return active
  for (const paneId of splitWorkspaceContainerRefs.value.keys()) {
    const live = document.querySelector(`.workspace-monaco-container[data-pane-id="${paneId}"]`)
    if (live && live.isConnected) return live
  }
  if (active) return active
  for (const [, hostEl] of splitWorkspaceContainerRefs.value) return hostEl
  return null
})
// 工作区恒为 pane 树：Monaco 容器一律由各 file pane 的 setSplitWorkspaceContainerRef 注册。
const editorContainerRef = computed(() => splitWorkspaceContainerRef.value)
// 编辑器多实例管理（类似 terminalSessions）
const workspaceSessions = ref([])  // [{ agent_id, agent_name, tabs: [], activeTabPath: null, editorModels: new Map() }]
const activeWorkspaceSessionId = ref(null)  // 当前激活的编辑器会话 agent_id

// 保持向后兼容的计算属性
const workspaceTabs = computed(() => {
  const session = workspaceSessions.value.find(s => s.agent_id === activeWorkspaceSessionId.value)
  return session ? session.tabs : []
})
const activeWorkspaceTabPath = computed(() => {
  const session = workspaceSessions.value.find(s => s.agent_id === activeWorkspaceSessionId.value)
  return session ? session.activeTabPath : null
})
const activeWorkspaceSession = computed(() => {
  return workspaceSessions.value.find(s => s.agent_id === activeWorkspaceSessionId.value) || null
})
// 虚拟目录会话（未创建 Agent 时直接打开的目录），供目录树额外渲染
const virtualWorkspaceSessions = computed(() => {
  return workspaceSessions.value.filter(s => s.agent?.virtual === true)
})
const editorModels = new Map() // path -> { model: ITextModel, content: string, language: string }
const workspaceFileHeartbeatTimer = ref(null)
const isWorkspaceEditable = ref(false)  // 编辑器可编辑开关，默认只读
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
// 搜索模式：'content' 搜文件内容，'filename' 按文件名模糊搜索
const globalSearchMode = ref('content')
const fileSearchResults = ref([])
const showWorkspaceSidebar = ref(true)
// 默认展示 Agent 列表（而非文件目录树）
const workspaceSidebarView = ref('agents')
// 插件前端扩展（拆自 composable usePlugins，见下方 usePlugins 调用处）
const {
  pluginExtensions,
  pluginAdminTabs,
  pluginSidebarViews,
  pluginToolPanels,
  pluginSidebarTitle,
  pluginToolPanelTitle,
  WORKSPACE_SIDEBAR_TITLES,
  workspaceSidebarTitle,
  loadPluginExtensionsForUi,
  resolvePluginExtensionComponent,
  isPluginSidebarView,
  isPluginToolView,
  pluginSidebarCompCache,
  activePluginSidebarComp,
  activePluginToolPanelComp,
} = usePlugins({
  workspaceSidebarView,
  fetchPluginExtensions,
  loadExtensionComponent,
  fetchWithAuth,
  getHttpProtocol,
  hasAuthToken,
  getGatewayAddress,
})
// 编辑器主区域视图：'file' 显示代码编辑器/diff，'chat' 显示聊天室，'terminal' 显示终端。
// 已统一为 pane 树模型：唯一 leaf 就是主区域，故主区域视图 = 唯一 leaf 的 view（派生）。
// 已分割时主区域语义由各 pane 承载，这里返回 'file' 以兼容历史读点。
const workspaceMainView = computed(() => {
  const root = workspacePaneTree.value
  if (root && root.type === 'leaf') return root.view
  return 'file'
})

// ===== 编辑器主工作区「自由分割」（VS Code split 同款）=====
// 布局模型：树形节点
//   split: { type:'split', direction:'row'|'column', ratio:number, children:[node, node] }
//   leaf : { type:'leaf', id:string, view:'file'|'session'|'chat'|'terminal'|'diff', sessionPanelId:string|null, diff?:object }
// 阶段3 起 chat / terminal 也可作为 leaf 的 view（host 单例：同一时刻只允许一个 pane 承载）。
// diff 作为 leaf 的 view：每个 diff pane 一个独立 Monaco DiffEditor 实例（可多实例，无 host 单例约束），
// diff 数据（commitHash/filePath 等）挂在 leaf.diff 上，不参与持久化（刷新后降级为 file）。
const EDITOR_PANE_MIN_RATIO = 0.15
const EDITOR_PANE_MAX_RATIO = 0.85
let workspacePaneSeq = 0
function createWorkspacePaneLeaf(view = 'file', sessionPanelId = null, agentId = null) {
  workspacePaneSeq += 1
  return { type: 'leaf', id: `pane-${workspacePaneSeq}`, view, sessionPanelId, agentId }
}
// 根默认单 leaf：未分割时行为与改动前完全一致
const workspacePaneTree = ref(createWorkspacePaneLeaf('file'))
const activePaneId = ref(workspacePaneTree.value.id)
// 处于「临时最大化」的 leaf id：该 leaf 用 CSS 提升为全屏浮层（DOM 不移动，Monaco/xterm 实例零重建），
// 再次点击还原即移除 class 嵌回原布局。null 表示无最大化。
const maximizedPaneId = ref(null)
// 是否已发生分割（>1 个 leaf）。未分割时模板走原有渲染路径，保证零回归。
const workspacePaneCount = computed(() => {
  let count = 0
  const walk = (node) => {
    if (!node) return
    if (node.type === 'leaf') {
      count += 1
      return
    }
    ;(node.children || []).forEach(walk)
  }
  walk(workspacePaneTree.value)
  return count
})
// 是否显示「分屏」按钮：未分割时，文件视图与会话/聊天/终端视图都允许切分
// （切分时会把当前主视图固化到原 pane，新 pane 为文件，见 splitWorkspacePane；
//  chat/terminal 是 host 单例，新 pane 一律为 file，不会出现两个 pane 争抢同一 host）。
const canSplitWorkspacePane = computed(() => {
  // 移动端不支持分割（分割条拖拽与多 pane 布局在窄屏不可用），隐藏分屏按钮
  if (windowWidth.value <= 768) return false
  if (workspacePaneCount.value > 1) return false
  return ['file', 'session', 'chat', 'terminal'].includes(workspaceMainView.value)
})
const activePane = computed(() => findWorkspacePaneById(workspacePaneTree.value, activePaneId.value))
function findWorkspacePaneById(node, paneId) {
  if (!node) return null
  if (node.type === 'leaf') return node.id === paneId ? node : null
  for (const child of node.children || []) {
    const found = findWorkspacePaneById(child, paneId)
    if (found) return found
  }
  return null
}
// 找到某个 leaf 的父 split 节点
function findWorkspacePaneParent(node, paneId) {
  if (!node || node.type === 'leaf') return null
  for (const child of node.children || []) {
    if (child.type === 'leaf' && child.id === paneId) return node
    const found = findWorkspacePaneParent(child, paneId)
    if (found) return found
  }
  return null
}
function activateWorkspacePane(paneId, { moveFocus = false } = {}) {
  if (!findWorkspacePaneById(workspacePaneTree.value, paneId)) return
  if (activePaneId.value === paneId) return
  activePaneId.value = paneId
  // 激活会话 pane 时同步当前 Agent，使侧边栏 Agent 高亮跟随切换（与 activatePanel 一致）
  const pane = findWorkspacePaneById(workspacePaneTree.value, paneId)
  if (pane && pane.view === 'session' && pane.sessionPanelId) {
    const panel = panels().value.find(p => p.id === pane.sessionPanelId)
    const agent = panel?.agentId ? agentList().value.find(a => a.agent_id === panel.agentId) : null
    if (agent) switchAgent()(agent)
  }
  // 激活 pane 会切换 Monaco 容器（只有激活 pane 渲染真实容器），需重建视图
  nextTick(() => {
    remountMonacoEditor()
    // 方向键切换时，把键盘焦点也移到新 pane 的内容上（否则焦点停留在旧 pane）
    if (moveFocus) focusWorkspacePane(paneId)
  })
}
// 临时最大化/还原指定 leaf：最大化时该 leaf 由 CSS 提升为全屏浮层（DOM 不移动，
// Monaco/xterm 实例不重建），还原即移除 class 嵌回原布局。
function toggleMaximizeWorkspacePane(paneId) {
  if (!findWorkspacePaneById(workspacePaneTree.value, paneId)) return
  if (maximizedPaneId.value === paneId) {
    maximizedPaneId.value = null
  } else {
    // 最大化前先激活该 pane，并让 workspace 面板置顶，避免被其它更高层面板遮挡。
    activateWorkspacePane(paneId)
    focusWindow('workspace')
    maximizedPaneId.value = paneId
  }
  // 布局尺寸变化，通知 Monaco/diff 重新 layout
  nextTick(() => {
    remountMonacoEditor()
    layoutGitDiffEditor()()
  })
}
// 把键盘焦点移到指定 pane 的内容上（用于方向键切换激活区域后让焦点跟随）
// file/diff pane 聚焦其 Monaco 编辑器实例；其它（session/chat/terminal/empty）聚焦 pane 内首个可聚焦元素
function focusWorkspacePane(paneId) {
  const pane = findWorkspacePaneById(workspacePaneTree.value, paneId)
  if (!pane) return
  if (pane.view === 'file') {
    const view = editorViews.get(paneId)
    if (view && typeof view.focus === 'function') {
      view.focus()
      return
    }
  }
  if (pane.view === 'diff') {
    const entry = diffEditorViews.get(paneId)
    if (entry && entry.editor && typeof entry.editor.focus === 'function') {
      entry.editor.focus()
      return
    }
  }
  const leafEl = document.querySelector(`.workspace-pane-leaf[data-pane-id="${paneId}"]`)
  if (leafEl) focusFirstIn()(leafEl)
}
// 在 pane 树中找到从根到指定 leaf 的路径（含根与 leaf 的所有节点）
function findWorkspacePanePath(node, paneId, path = []) {
  if (!node) return null
  if (node.type === 'leaf') {
    return node.id === paneId ? [...path, node] : null
  }
  for (const child of node.children || []) {
    const result = findWorkspacePanePath(child, paneId, [...path, node])
    if (result) return result
  }
  return null
}
// 返回 node 子树中在 dir 方向上最边缘的 leaf（用于方向导航落到目标子树内的具体 pane）
function findWorkspacePaneEdgeLeaf(node, dir) {
  if (!node) return null
  if (node.type === 'leaf') return node
  const row = node.direction === 'row'
  const col = node.direction === 'column'
  let childIdx = 0
  if ((dir === 'left' && row) || (dir === 'up' && col)) childIdx = 0
  else if ((dir === 'right' && row) || (dir === 'down' && col)) childIdx = 1
  return findWorkspacePaneEdgeLeaf(node.children[childIdx], dir)
}
// 用 Ctrl+Alt+方向键在分割 pane 之间切换激活区域
// dir: 'left'|'right'|'up'|'down'；返回是否已切换（未分割或无可切换 pane 时返回 false）
function moveActivePaneInDirection(dir) {
  if (workspacePaneCount.value <= 1) return false
  const path = findWorkspacePanePath(workspacePaneTree.value, activePaneId.value)
  if (!path || path.length < 2) return false
  const leaf = path[path.length - 1]
  // 从 leaf 的父 split 起向上回溯，找第一个满足方向条件的 split
  for (let i = path.length - 2; i >= 0; i--) {
    const node = path[i]
    if (node.type !== 'split') continue
    const childIdx = node.children.findIndex(c => !!findWorkspacePaneById(c, leaf.id))
    if (childIdx < 0) continue
    const row = node.direction === 'row'
    const col = node.direction === 'column'
    const match =
      (dir === 'left' && row && childIdx === 1) ||
      (dir === 'right' && row && childIdx === 0) ||
      (dir === 'up' && col && childIdx === 1) ||
      (dir === 'down' && col && childIdx === 0)
    if (!match) continue
    const targetChild = node.children[1 - childIdx]
    const targetLeaf = findWorkspacePaneEdgeLeaf(targetChild, dir)
    if (targetLeaf) {
      activateWorkspacePane(targetLeaf.id, { moveFocus: true })
      return true
    }
  }
  return false
}
// 找出「面积最大」的 pane（作为程序化分割的目标）：遍历所有 leaf，用其 DOM 的
// getBoundingClientRect 计算面积（宽×高），返回面积最大的 leaf id。
// 拿不到任何 DOM（未分割 / 尚未挂载）时回退当前激活 pane，保持与旧行为一致。
function findLargestWorkspacePaneId() {
  let largestId = activePaneId.value
  let largestArea = -1
  const walk = (node) => {
    if (!node) return
    if (node.type === 'leaf') {
      const el = document.querySelector(`.workspace-pane-leaf[data-pane-id="${node.id}"]`)
      if (el) {
        const rect = el.getBoundingClientRect()
        if (rect) {
          const area = rect.width * rect.height
          if (area > largestArea) {
            largestArea = area
            largestId = node.id
          }
        }
      }
      return
    }
    ;(node.children || []).forEach(walk)
  }
  walk(workspacePaneTree.value)
  return largestId
}
// 计算「自动分割」的方向：取「面积最大」pane 的宽高，高大于宽则上下分（column），否则左右分（row）。
// 用于点击侧边文件 / 打开面板等程序化分割（用户显式指定方向的快捷键不受影响）。
// 拿不到 pane 的 DOM（未分割 / 尚未挂载）时回退 'row'，保持与旧行为一致。
function computeSplitDirection() {
  const paneId = findLargestWorkspacePaneId()
  if (paneId) {
    const el = document.querySelector(`.workspace-pane-leaf[data-pane-id="${paneId}"]`)
    if (el) {
      const rect = el.getBoundingClientRect()
      if (rect && rect.height > rect.width) return 'column'
    }
  }
  return 'row'
}

// 以 direction 方向切分指定 leaf：把该 leaf 替换为 split，原 leaf 保留在首位，
// 新 leaf 成为激活 pane。
// 注意：session / chat / terminal leaf 不能把承载内容复制给新 leaf（否则同一 Panel 或同一
// host 单例被两个 pane 承载，xterm / chat 状态会争抢），因此切分时新 leaf 一律为 file leaf。
function splitWorkspacePane(paneId, direction) {
  if (windowWidth.value <= 768) return
  const parent = findWorkspacePaneParent(workspacePaneTree.value, paneId)
  const target = findWorkspacePaneById(workspacePaneTree.value, paneId)
  if (!target) return
  // 已统一为 pane 树模型：未分割时唯一 leaf 就是主区域，其 view/内容由该 leaf 承载。
  // 切分时 target 即该 leaf，内容自然保留，无需迁移。
  // 新 pane 一律为「空」leaf：不带 file/session/chat/terminal 任何属性，
  // 用户需显式打开文件/会话才会赋予内容（避免新 pane 凭空显示文件或会话）。
  const newLeaf = createWorkspacePaneLeaf('empty')
  const splitNode = {
    type: 'split',
    direction: direction === 'column' ? 'column' : 'row',
    ratio: 0.5,
    children: [target, newLeaf],
  }
  if (!parent) {
    workspacePaneTree.value = splitNode
  } else {
    const index = parent.children.indexOf(target)
    parent.children.splice(index, 1, splitNode)
  }
  // 首次分割：把当前全局标签列表固化到「原 pane」，新 pane 从空开始。
  // 这样两个 pane 的标签栏各自独立，互不影响。
  if (!workspacePaneTabs.has(target.id)) {
    workspacePaneTabs.set(target.id, workspaceTabs.value.map(t => t.path))
    workspacePaneTabsVersion.value += 1
  }
  // 首次分割时把当前打开的文件绑到原 pane 的 workspaceViewPanes；
  // 否则两个 pane 的实例都会 setModel(null) → 都看不到文件。
  if (target.view === 'file' && !workspaceViewPanes.has(target.id)) {
    const currentPath = activeWorkspaceTabPath.value
    if (currentPath) workspaceViewPanes.set(target.id, currentPath)
  }
  activePaneId.value = newLeaf.id
  // 分割会改变布局，若此前处于最大化则先还原
  maximizedPaneId.value = null
  persistWorkspacePaneLayout()
  nextTick(() => {
    remountMonacoEditor()
    layoutGitDiffEditor()()
  })
}
// 关闭指定 leaf：兄弟节点顶替；仅剩一个 leaf 时不允许关闭。
function closeWorkspacePane(paneId) {
  if (workspacePaneCount.value <= 1) return
  const parent = findWorkspacePaneParent(workspacePaneTree.value, paneId)
  if (!parent) return
  const index = parent.children.findIndex(child => child.type === 'leaf' && child.id === paneId)
  if (index < 0) return
  parent.children.splice(index, 1)
  // 该 pane 的独立标签列表一并丢弃（其文件若仍被其他 pane 引用则保持）
  workspacePaneTabs.delete(paneId)
  workspacePaneTabsVersion.value += 1
  // 该 pane 若承载 diff，释放其独立 diff 实例
  disposeDiffEditorForPane()(paneId)
  // 父节点只剩一个 child 时，用该 child 顶替父节点（压缩冗余层级）
  if (parent.children.length === 1) {
    const only = parent.children[0]
    if (parent === workspacePaneTree.value) {
      workspacePaneTree.value = only
    } else {
      // 在树上定位 parent 并替换为 only
      const replaceNode = (node) => {
        if (!node || node.type === 'leaf') return false
        const idx = node.children.indexOf(parent)
        if (idx >= 0) {
          node.children.splice(idx, 1, only)
          return true
        }
        return (node.children || []).some(replaceNode)
      }
      replaceNode(workspacePaneTree.value)
    }
  }
  if (!findWorkspacePaneById(workspacePaneTree.value, activePaneId.value)) {
    activePaneId.value = findFirstWorkspacePaneId(workspacePaneTree.value)
  }
  // 被关闭的 pane 若正处于最大化，清除最大化状态
  if (maximizedPaneId.value && !findWorkspacePaneById(workspacePaneTree.value, maximizedPaneId.value)) {
    maximizedPaneId.value = null
  }
  // 已统一为 pane 树模型：关闭后回到未分割（只剩一个 leaf）时，该 leaf 就是主区域，
  // 其 view/内容自然保留，无需迁回 workspaceMainView。
  persistWorkspacePaneLayout()
  nextTick(() => {
    remountMonacoEditor()
    layoutGitDiffEditor()()
  })
}
function findFirstWorkspacePaneId(node) {
  if (!node) return null
  if (node.type === 'leaf') return node.id
  for (const child of node.children || []) {
    const found = findFirstWorkspacePaneId(child)
    if (found) return found
  }
  return null
}
// 收起所有分割，回到单个 file leaf（切到 chat/terminal 或需要重置时调用）
function collapseWorkspacePanes() {
  const leaf = createWorkspacePaneLeaf('file')
  workspacePaneTree.value = leaf
  activePaneId.value = leaf.id
  maximizedPaneId.value = null
  // 收起分割：回到全局标签栏，清空各 pane 的独立列表
  workspacePaneTabs.clear()
  workspacePaneTabsVersion.value += 1
  // 收起分割：释放所有 diff pane 的独立实例
  disposeAllDiffEditors()()
}

// ===== 阶段2：左侧点击路由到「激活 pane」=====
// 设计：每个 leaf 持有自己的 view（'file' | 'session'）与 sessionPanelId。
// 左侧点击（文件树 / Agent 列表 / 搜索结果）在已分割时改写「激活 pane」的 view，
// 未分割时走原有 workspaceMainView 路径（保证零回归）。
// 约束：同一个 sessionPanelId 不允许同时出现在两个 pane 中（终端 host 单例，会争抢），
// 因此路由到 session 时会先把其他 pane 上相同的 sessionPanelId 清空。

// 找出除 exceptPaneId 之外、正在承载指定 sessionPanelId 的 leaf（用于去重）
function findWorkspacePaneBySessionPanelId(sessionPanelId, exceptPaneId = null) {
  if (!sessionPanelId) return null
  let found = null
  const walk = (node) => {
    if (!node || found) return
    if (node.type === 'leaf') {
      if (node.id !== exceptPaneId && node.view === 'session' && node.sessionPanelId === sessionPanelId) {
        found = node
      }
      return
    }
    ;(node.children || []).forEach(walk)
  }
  walk(workspacePaneTree.value)
  return found
}

// 找出除 exceptPaneId 之外、正在承载指定 view（chat / terminal）的 leaf。
// host 单例：同一时刻只允许一个 pane 承载 chat / terminal，切换前需先卸载旧的。
function findWorkspacePaneByView(view, exceptPaneId = null) {
  let found = null
  const walk = (node) => {
    if (!node || found) return
    if (node.type === 'leaf') {
      if (node.id !== exceptPaneId && node.view === view) found = node
      return
    }
    ;(node.children || []).forEach(walk)
  }
  walk(workspacePaneTree.value)
  return found
}
// 找出正在承载指定 Agent 的「文件编辑器」pane（view==='file' 且记录了该 agent_id）。
// 用于 editor_open_file：Agent 打开文件时应复用其已有的编辑器面板，而非覆盖当前会话区域。
function findAgentFilePane(agentId) {
  if (!agentId) return null
  let found = null
  const walk = (node) => {
    if (!node || found) return
    if (node.type === 'leaf') {
      if (node.view === 'file' && node.agentId === agentId) found = node
      return
    }
    ;(node.children || []).forEach(walk)
  }
  walk(workspacePaneTree.value)
  return found
}

// 为 editor_open_file 定位目标编辑器 pane，返回其 paneId（并确保它被激活且为 file 视图）：
// 1) 该 Agent 已有文件编辑器面板 → 复用它（激活）；
// 2) 当前激活 pane 已是 file 视图 → 直接复用它（记录 agentId）；
// 3) 否则分割当前面板，在新 file 面板中打开（保留当前会话/聊天/终端不被覆盖）。
function ensureAgentEditorPane(agentId) {
  const existing = findAgentFilePane(agentId)
  if (existing) {
    activateWorkspacePane(existing.id)
    return existing.id
  }
  // 已统一为 pane 树：activePane 就是当前激活区域（未分割时即唯一 leaf），
  // 只有当前确实是「文件视图」才直接复用；否则（会话/聊天/终端）需分割出新面板，避免覆盖。
  const isFileView = activePane.value && activePane.value.view === 'file'
  if (isFileView) {
    const cur = activePane.value
    if (cur) {
      cur.agentId = agentId
      return cur.id
    }
  }
  splitWorkspacePane(findLargestWorkspacePaneId(), computeSplitDirection())
  const newPane = activePane.value
  if (newPane) {
    newPane.view = 'file'
    newPane.agentId = agentId
    return newPane.id
  }
  return null
}

// 判断某个 pane 是否可视为「空区域」（点击侧边文件时优先在空区域原地创建编辑器）：
// - view === 'empty'：显式空 pane；
// - view === 'file' 但未绑定任何文件：新分割出的空 file pane / 刚打开编辑器（标题显示「空区域」）。
function isPaneEmptyForFileOpen(pane) {
  if (!pane) return false
  if (pane.view === 'empty') return true
  if (pane.view === 'file') {
    return !workspaceViewPanes.has(pane.id) && !(pane.id === activePaneId.value && activeWorkspaceTabPath.value)
  }
  return false
}

// 找出「已打开的编辑器面板」：优先该 Agent 的 file pane，其次任意 file pane。
// 用于点击侧边文件时复用已有编辑器面板，而非覆盖当前会话/聊天/终端区域。
function findAnyFilePane(agentId) {
  if (agentId) {
    const agentPane = findAgentFilePane(agentId)
    if (agentPane) return agentPane
  }
  let found = null
  const walk = (node) => {
    if (!node || found) return
    if (node.type === 'leaf') {
      if (node.view === 'file') found = node
      return
    }
    ;(node.children || []).forEach(walk)
  }
  walk(workspacePaneTree.value)
  return found
}

// 为「点击侧边文件打开」定位目标编辑器 pane（返回 paneId）：
// 1) 当前活动区域为空 → 直接在当前区域创建编辑器（不分割）；
// 2) 否则找已打开的编辑器面板 → 复用它（不打扰当前活动区域）；
// 3) 否则分割当前区域，在新 pane 创建编辑器。
// 已统一为 pane 树：未分割时 activePane 就是唯一 leaf，逻辑与已分割一致。
function ensureEditorPaneForFileOpen(agentId) {
  const active = activePane.value
  // 1. 当前活动区域为空 → 在当前区域创建编辑器
  if (isPaneEmptyForFileOpen(active)) {
    active.view = 'file'
    if (agentId) active.agentId = agentId
    activateWorkspacePane(active.id)
    return active.id
  }
  // 2. 找已打开的编辑器面板 → 复用
  const filePane = findAnyFilePane(agentId)
  if (filePane) {
    activateWorkspacePane(filePane.id)
    return filePane.id
  }
  // 3. 分割当前区域创建编辑器
  splitWorkspacePane(findLargestWorkspacePaneId(), computeSplitDirection())
  const newPane = activePane.value
  if (newPane) {
    newPane.view = 'file'
    if (agentId) newPane.agentId = agentId
    return newPane.id
  }
  return null
}
// workspaceMainView 派生自 leaf.view，故直接改写唯一 leaf 的 view 即可。
function setMainViewOnLeaf(view, sessionPanelId = null) {
  const root = workspacePaneTree.value
  if (root && root.type === 'leaf') {
    root.view = view
    root.sessionPanelId = view === 'session' ? sessionPanelId : null
  }
}

// 为「打开面板视图」定位目标 pane（返回 paneId；未分割且原地打开时返回 null）：
// 1) 当前活动区域为空 → 直接在当前区域创建（不分割）；
// 2) 已存在承载该视图的 pane（chat/terminal 是 host 单例、session 按 panel 复用）→ 激活它；
// 3) 否则分割当前区域，在新 pane 承载目标视图。
function ensurePaneForView(view, sessionPanelId) {
  // 2. 已存在承载该视图的 pane → 复用（chat/terminal host 单例、session 按 panel 复用）
  if (view === 'chat' || view === 'terminal') {
    const existing = findWorkspacePaneByView(view)
    if (existing) {
      activateWorkspacePane(existing.id)
      return existing.id
    }
  } else if (view === 'session' && sessionPanelId) {
    const existing = findWorkspacePaneBySessionPanelId(sessionPanelId)
    if (existing) {
      activateWorkspacePane(existing.id)
      return existing.id
    }
  } else if (view === 'diff') {
    // diff 每个 pane 一个独立实例（无 host 单例约束）：已存在 diff pane 则复用，避免覆盖当前区域。
    const existing = findWorkspacePaneByView('diff')
    if (existing) {
      activateWorkspacePane(existing.id)
      return existing.id
    }
  }
  // 已统一为 pane 树：未分割时 activePane 就是唯一 leaf，逻辑与已分割一致。
  const active = activePane.value
  // 1. 当前活动区域为空 → 在当前区域创建
  if (isPaneEmptyForFileOpen(active)) {
    setActivePaneViewForPane(active, view, sessionPanelId)
    activateWorkspacePane(active.id)
    return active.id
  }
  // 3. 分割当前区域创建
  splitWorkspacePane(findLargestWorkspacePaneId(), computeSplitDirection())
  const newPane = activePane.value
  if (newPane) {
    setActivePaneViewForPane(newPane, view, sessionPanelId)
    return newPane.id
  }
  return null
}

// 把「激活 pane」的视图切换为 view（file / session / chat / terminal / diff）。
// 已统一为 pane 树：activePane 就是当前激活区域（未分割时即唯一 leaf）。
function setActivePaneView(view, sessionPanelId = null) {
  const pane = activePane.value
  if (!pane) return false
  return setActivePaneViewForPane(pane, view, sessionPanelId)
}

// 把「指定 pane」的视图切换为 view（file / session / chat / terminal / diff / empty）。
// 与 setActivePaneView 的区别：作用于传入的 pane，而非当前激活 pane（用于「收起」时定位承载 host 的 pane）。
function setActivePaneViewForPane(pane, view, sessionPanelId = null) {
  if (!pane) return false
  if (view === 'session') {
    if (!sessionPanelId) return false
    // 同一 panel 不允许同时被两个 pane 承载：清掉其他 pane 上的相同 panel
    const duplicated = findWorkspacePaneBySessionPanelId(sessionPanelId, pane.id)
    if (duplicated) {
      duplicated.view = 'empty'
      duplicated.sessionPanelId = null
    }
    // 需求：Panel 一律落在「激活 pane」里（不再重定向到其他空闲 file pane）。
    // 若激活 pane 已承载另一个 session panel，则关闭旧 panel，让新 panel 覆盖它。
    if (pane.view === 'session' && pane.sessionPanelId && pane.sessionPanelId !== sessionPanelId) {
      const oldPanelId = pane.sessionPanelId
      const oldPanel = panels().value.find(p => p.id === oldPanelId)
      if (oldPanel) closePanel()(oldPanelId)
    }
  } else if (view === 'chat' || view === 'terminal') {
    // host 单例：先卸载其他 pane 上同类型的承载，再交给激活 pane
    const duplicated = findWorkspacePaneByView(view, pane.id)
    if (duplicated) {
      duplicated.view = 'empty'
      duplicated.sessionPanelId = null
    }
  }
  // 从 diff 切走时释放该 pane 的 diff 实例（diff 数据一并清空）
  if (pane.view === 'diff' && view !== 'diff') {
    disposeDiffEditorForPane()(pane.id)
    pane.diff = null
  }
  pane.view = view
  pane.sessionPanelId = view === 'session' ? sessionPanelId : null
  persistWorkspacePaneLayout()
  // 切换激活 pane 的内容类型后，Monaco 容器可能被替换/移除，需要重建视图
  nextTick(() => {
    remountMonacoEditor()
    layoutGitDiffEditor()()
  })
  return true
}

// pane 标题：file 显示当前文件名（仅激活 pane，因为 Monaco 单实例只渲染激活 pane），
// session 显示 Agent 名（找不到时回退到通用文案）
function getWorkspacePaneTitle(pane) {
  if (!pane) return ''
  if (pane.view === 'empty') return '空区域'
  if (pane.view === 'chat') return '聊天室'
  if (pane.view === 'terminal') return '终端'
  if (pane.view === 'diff') {
    const path = pane.diff?.filePath
    return path ? `diff: ${path.split('/').pop() || path}` : 'diff'
  }
  if (pane.view === 'session') {
    const panel = panels().value.find(p => p.id === pane.sessionPanelId)
    const agent = panel ? getPanelAgent()(panel) : null
    return agent ? (agent.name || agent.agent_id) : '会话'
  }
  // 每个 file pane 都有独立编辑器实例，标题显示该 pane 自己绑定的文件
  const panePath = workspaceViewPanes.get(pane.id) || (pane.id === activePaneId.value ? activeWorkspaceTabPath.value : null)
  if (panePath) return panePath.split('/').pop() || panePath
  // 文件视图但未绑定任何文件（如刚打开编辑器、或分割出的空 pane）：
  // 内容区是空占位符，标题也应显示「空区域」，与 view='empty' 的语义保持一致。
  return '空区域'
}

// pane 状态文案（原顶部工具栏的状态提示，现随 pane 标题栏展示）：
// 只对 file pane 有意义——取该 pane 自己绑定的文件对应的标签状态。
function getWorkspacePaneStatus(pane) {
  if (!pane || pane.view !== 'file') return ''
  const path = workspaceViewPanes.get(pane.id) || (pane.id === activePaneId.value ? activeWorkspaceTabPath.value : null)
  if (!path) return ''
  const tab = getWorkspaceTabByPath(path)
  if (!tab) return ''
  if (tab.loading) return '加载中...'
  if (tab.error) return tab.error
  return tab.isDirty ? '未保存修改' : '已保存'
}

// 非激活 file pane 的只读预览文本：取当前激活文件的内容，截断到合理长度，
// 避免大文件把 DOM 撑爆（只读快照仅用于「让用户看到内容还在」，不追求完整）。
const EDITOR_PANE_PREVIEW_MAX_CHARS = 20000
function getWorkspacePreviewText() {
  const path = activeWorkspaceTabPath.value
  if (!path) return ''
  const modelData = editorModels.get(path)
  const content = modelData?.content ?? activeWorkspaceTab.value?.content ?? ''
  if (content.length <= EDITOR_PANE_PREVIEW_MAX_CHARS) return content
  return `${content.slice(0, EDITOR_PANE_PREVIEW_MAX_CHARS)}\n\n…（预览已截断，激活后可查看完整内容）`
}

// pane 承载的 Panel 对象（session leaf 用）
function getPanePanel(pane) {
  if (!pane || pane.view !== 'session' || !pane.sessionPanelId) return null
  return panels().value.find(p => p.id === pane.sessionPanelId) || null
}

// pane 是否应被视为「激活」（用于 SessionPanel 的 active 态）
function isPaneActive(pane) {
  return !!pane && pane.id === activePaneId.value
}
// 拖拽分隔条调整比例（限 0.15~0.85）
// 说明：split 节点是 workspacePaneTree 内的可变对象，拖拽时直接改它的 ratio，
// 由 Vue 的深层响应式驱动重渲染；拖拽期间不调用 layout()，结束后才重排一次，避免尺寸震荡。
let workspacePaneResizeContext = null
const workspacePaneResizing = ref(false)
function startWorkspacePaneResize(event, splitNode) {
  if (windowWidth.value <= 768) return
  const containerEl = event.currentTarget?.parentElement
  const rect = containerEl?.getBoundingClientRect?.() || { width: 0, height: 0 }
  const containerSize = splitNode.direction === 'row' ? rect.width : rect.height
  if (!containerSize) return
  workspacePaneResizeContext = {
    splitNode,
    direction: splitNode.direction,
    startPos: splitNode.direction === 'row' ? event.clientX : event.clientY,
    startRatio: splitNode.ratio,
    containerSize,
  }
  workspacePaneResizing.value = true
  document.addEventListener('mousemove', onWorkspacePaneResize)
  document.addEventListener('mouseup', stopWorkspacePaneResize)
  event.preventDefault()
  event.stopPropagation()
}
function onWorkspacePaneResize(event) {
  const ctx = workspacePaneResizeContext
  if (!ctx) return
  const current = ctx.direction === 'row' ? event.clientX : event.clientY
  const delta = current - ctx.startPos
  const nextRatio = ctx.startRatio + delta / ctx.containerSize
  ctx.splitNode.ratio = clamp(nextRatio, EDITOR_PANE_MIN_RATIO, EDITOR_PANE_MAX_RATIO)
}
function stopWorkspacePaneResize() {
  const wasActive = !!workspacePaneResizeContext
  workspacePaneResizeContext = null
  workspacePaneResizing.value = false
  document.removeEventListener('mousemove', onWorkspacePaneResize)
  document.removeEventListener('mouseup', stopWorkspacePaneResize)
  if (wasActive) {
    persistWorkspacePaneLayout()
    nextTick(() => {
      layoutMonacoEditor()
      layoutGitDiffEditor()()
    })
  }
}

// ===== 阶段4：布局持久化（localStorage）+ 合法性校验 =====
// 设计：把 workspacePaneTree 序列化到 localStorage；刷新后恢复。
// 任何解析/校验失败都回退到默认单 leaf，绝不因脏数据导致白屏。
const EDITOR_PANE_LAYOUT_KEY = 'jarvis_workspace_pane_layout'

// 递归校验并规范化一个节点；非法返回 null（调用方据此回退）
// 说明：leaf 上允许携带 content 字段（各视图的内容恢复信息，见 persistWorkspacePaneLayout），
// 该字段仅用于「刷新后恢复内容」，不参与渲染；恢复完成后由 restoreWorkspacePaneContents 移除。
function sanitizeWorkspacePaneNode(raw) {
  if (!raw || typeof raw !== 'object') return null
  if (raw.type === 'split') {
    if (raw.direction !== 'row' && raw.direction !== 'column') return null
    if (!Array.isArray(raw.children) || raw.children.length !== 2) return null
    const left = sanitizeWorkspacePaneNode(raw.children[0])
    const right = sanitizeWorkspacePaneNode(raw.children[1])
    if (!left || !right) return null
    let ratio = Number(raw.ratio)
    if (!Number.isFinite(ratio)) ratio = 0.5
    ratio = clamp(ratio, EDITOR_PANE_MIN_RATIO, EDITOR_PANE_MAX_RATIO)
    return { type: 'split', direction: raw.direction, ratio, children: [left, right] }
  }
  if (raw.type === 'leaf') {
    const validViews = ['file', 'session', 'chat', 'terminal', 'diff', 'empty']
    if (!validViews.includes(raw.view)) return null
    if (typeof raw.id !== 'string' || !raw.id) return null
    const content = raw.content && typeof raw.content === 'object' ? raw.content : null
    if (raw.view === 'diff') {
      // diff 内容恢复信息：commitHash + filePath（最小信息，diff 文本不持久化）+ agentId（工作目录来源）。
      // 合法则保留 diff 视图，恢复时重新拉取；非法（如 commit 已失效）降级为空 pane，
      // 而不是 file pane，避免误导用户以为是文件区域。
      if (content && typeof content.commitHash === 'string' && content.commitHash
        && typeof content.filePath === 'string' && content.filePath) {
        const agentId = typeof content.agentId === 'string' && content.agentId ? content.agentId : null
        return { type: 'leaf', id: raw.id, view: 'diff', sessionPanelId: null, agentId, content: { commitHash: content.commitHash, filePath: content.filePath, agentId } }
      }
      return { type: 'leaf', id: raw.id, view: 'empty', sessionPanelId: null, agentId: null, content: null }
    }
    if (raw.view === 'session') {
      // 只校验持久化的 agentId（用于刷新后重建 panel）；sessionPanelId 是刷新前的
      // panel id，刷新后 panels 重建必然失效，故不再据此校验（由 restoreWorkspacePaneContents
      // 按 agentId 重建 panel 后回填）。无 agentId 时回退为 file leaf（保持旧行为）。
      if (content && typeof content.agentId === 'string' && content.agentId) {
        return { type: 'leaf', id: raw.id, view: 'session', sessionPanelId: null, agentId: content.agentId, content: { agentId: content.agentId } }
      }
      return { type: 'leaf', id: raw.id, view: 'file', sessionPanelId: null, agentId: null, content: null }
    }
    if (raw.view === 'file') {
      // 文件编辑器 pane：持久化打开的文件列表（tabs）、当前绑定文件（activePath）与 agentId（文件系统来源）。
      let tabs = Array.isArray(content?.tabs) ? content.tabs.filter(t => typeof t === 'string' && t) : []
      const activePath = typeof content?.activePath === 'string' && content.activePath ? content.activePath : null
      const agentId = typeof content?.agentId === 'string' && content.agentId ? content.agentId : null
      return { type: 'leaf', id: raw.id, view: 'file', sessionPanelId: null, agentId, content: { tabs, activePath, agentId } }
    }
    if (raw.view === 'terminal') {
      // 终端 pane：持久化终端会话 id（刷新后由 restoreTerminalSessions 恢复的会话列表中匹配）。
      const terminalId = typeof content?.terminalId === 'string' && content.terminalId ? content.terminalId : null
      return { type: 'leaf', id: raw.id, view: 'terminal', sessionPanelId: null, agentId: null, content: terminalId ? { terminalId } : null }
    }
    // chat / empty：无内容恢复信息
    return { type: 'leaf', id: raw.id, view: raw.view, sessionPanelId: null, agentId: null, content: null }
  }
  return null
}

// 校验整棵树：必须是合法节点，且 leaf 数 >= 1；chat/terminal 至多各一个（host 单例约束）
function sanitizeWorkspacePaneTree(raw) {
  const node = sanitizeWorkspacePaneNode(raw)
  if (!node) return null
  const leafIds = new Set()
  const viewCount = { chat: 0, terminal: 0 }
  let valid = true
  const walk = (n) => {
    if (!valid || !n) return
    if (n.type === 'leaf') {
      if (leafIds.has(n.id)) { valid = false; return }
      leafIds.add(n.id)
      if (n.view === 'chat' || n.view === 'terminal') {
        viewCount[n.view] += 1
        if (viewCount[n.view] > 1) { valid = false; return }
      }
      return
    }
    ;(n.children || []).forEach(walk)
  }
  walk(node)
  if (!valid || leafIds.size < 1) return null
  return node
}

// 同步 workspacePaneSeq，避免恢复后新建 leaf 的 id 与已有 id 冲突
function syncWorkspacePaneSeq(tree) {
  let maxSeq = 0
  const walk = (n) => {
    if (!n) return
    if (n.type === 'leaf') {
      const m = /^pane-(\d+)$/.exec(n.id)
      if (m) maxSeq = Math.max(maxSeq, parseInt(m[1], 10))
      return
    }
    ;(n.children || []).forEach(walk)
  }
  walk(tree)
  workspacePaneSeq = Math.max(workspacePaneSeq, maxSeq)
}

// 写入 localStorage（失败静默，不影响功能）
function persistWorkspacePaneLayout() {
  try {
    const tree = workspacePaneTree.value
    // 未分割时不写（等价于清空），避免把默认态持久化成「已分割」的错觉
    if (!tree || workspacePaneCount.value <= 1) {
      localStorage.removeItem(EDITOR_PANE_LAYOUT_KEY)
      return
    }
    // version 2：除布局外，每个 leaf 额外携带 content（各视图的内容恢复信息）
    const payload = { version: 2, activePaneId: activePaneId.value, tree: serializeWorkspacePaneTree(tree) }
    localStorage.setItem(EDITOR_PANE_LAYOUT_KEY, JSON.stringify(payload))
  } catch (e) {
    // 忽略：localStorage 不可用（隐私模式 / 配额满）时静默降级
  }
}

// 序列化 pane 树：为每个 leaf 附加 content 字段（内容恢复信息），供刷新后恢复
function serializeWorkspacePaneTree(tree) {
  const clone = (node) => {
    if (!node) return node
    if (node.type === 'split') {
      return { type: 'split', direction: node.direction, ratio: node.ratio, children: node.children.map(clone) }
    }
    // leaf：按视图提取内容恢复信息（不序列化运行时状态如 diff 文本、Monaco 实例）
    let content = null
    if (node.view === 'session') {
      content = { agentId: node.agentId || null }
    } else if (node.view === 'file') {
      content = {
        tabs: workspacePaneTabs.get(node.id) || [],
        activePath: workspaceViewPanes.get(node.id) || null,
        agentId: node.agentId || null,
      }
    } else if (node.view === 'diff') {
      content = node.diff ? { commitHash: node.diff.commitHash || null, filePath: node.diff.filePath || null, agentId: node.agentId || null } : null
    } else if (node.view === 'terminal') {
      content = { terminalId: activeTerminalId().value || null }
    }
    return { type: 'leaf', id: node.id, view: node.view, sessionPanelId: node.sessionPanelId, agentId: node.agentId, content }
  }
  return clone(tree)
}

// 从 localStorage 恢复（setup 阶段调用）；失败回退默认单 leaf
function restoreWorkspacePaneLayout() {
  let raw = null
  try {
    raw = localStorage.getItem(EDITOR_PANE_LAYOUT_KEY)
  } catch (e) {
    return
  }
  if (!raw) return
  let parsed = null
  try {
    parsed = JSON.parse(raw)
  } catch (e) {
    try { localStorage.removeItem(EDITOR_PANE_LAYOUT_KEY) } catch (e2) {}
    return
  }
  const tree = sanitizeWorkspacePaneTree(parsed && parsed.tree)
  if (!tree) {
    try { localStorage.removeItem(EDITOR_PANE_LAYOUT_KEY) } catch (e) {}
    return
  }
  workspacePaneTree.value = tree
  syncWorkspacePaneSeq(tree)
  const wantActive = parsed && parsed.activePaneId
  activePaneId.value = findWorkspacePaneById(tree, wantActive)
    ? wantActive
    : findFirstWorkspacePaneId(tree)
}

// ===== 阶段 B：恢复每个 pane 的内容（session 会话 / 文件 / diff / terminal） =====
// 在 agentList 首次就绪后调用（socket 已连、agentList 已加载、restoreTerminalSessions 已执行）。
// 幂等：只执行一次；无法恢复的 leaf 降级为空 pane（与 Issue #82 补充说明一致）。
let workspacePaneContentsRestored = false
async function restoreWorkspacePaneContents() {
  if (workspacePaneContentsRestored) return
  // Agent 列表尚未就绪时不得恢复：此时 agentList 为空，session pane 会因
  // 找不到 Agent 被误降级为空 pane，且恢复信息（leaf.content）会被一次性
  // 清空、workspacePaneContentsRestored 置位后不再重试。故此处提前返回，
  // 等下次 fetchAgentList 拿到 Agent 后再触发（不消耗一次性标志）。
  if (agentList().value.length === 0) return
  const tree = workspacePaneTree.value
  if (!tree) return
  workspacePaneContentsRestored = true
  const leaves = []
  const walk = (n) => {
    if (!n) return
    if (n.type === 'leaf') leaves.push(n)
    else (n.children || []).forEach(walk)
  }
  walk(tree)
  for (const leaf of leaves) {
    const content = leaf.content
    if (!content) continue
    try {
      if (leaf.view === 'session' && content.agentId) {
        const agent = agentList().value.find(a => a.agent_id === content.agentId)
        if (!agent) {
          // Agent 已不存在：降级为空 pane
          leaf.view = 'empty'
          leaf.sessionPanelId = null
          leaf.agentId = null
        } else {
          // 复用已有 Panel（同一 Agent 只允许一个 Panel），否则新建
          let panel = panels().value.find(p => p.agentId === agent.agent_id)
          if (!panel) {
            panel = { id: `panel-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, agentId: agent.agent_id }
            panels().value.push(panel)
          }
          leaf.sessionPanelId = panel.id
          leaf.agentId = agent.agent_id
          activePanelId().value = panel.id
          workspaceSessionPanelId().value = panel.id
          await switchAgent()(agent)
        }
      } else if (leaf.view === 'file') {
        const tabs = content.tabs || []
        // 逐个打开到本 pane（先激活目标 pane，openWorkspaceFile 会登记到激活 pane 的标签列表）
        for (const path of tabs) {
          activateWorkspacePane(leaf.id)
          await openWorkspaceFile(path, content.agentId)
        }
        // 恢复当前绑定文件（activePath 在 tabs 中时激活它）
        if (content.activePath && tabs.includes(content.activePath)) {
          activateWorkspacePane(leaf.id)
          activateWorkspaceTab(content.activePath)
        }
      } else if (leaf.view === 'diff' && content.commitHash && content.filePath) {
        // 临时把 Git 目标切到该 Agent（确保 getGitWorkingDir 命中其工作目录），恢复后还原
        const savedGitAgentId = gitAgentId().value
        if (content.agentId) gitAgentId().value = content.agentId
        try {
          await loadDiffForPane()(leaf.id, content.commitHash, content.filePath)
        } finally {
          gitAgentId().value = savedGitAgentId
        }
        const pane = findWorkspacePaneById(workspacePaneTree.value, leaf.id)
        if (pane && pane.view === 'diff' && pane.diff && pane.diff.error) {
          // diff 拉取失败（如 commit 已失效）：降级为空 pane
          pane.view = 'empty'
          pane.diff = null
          pane.agentId = null
        }
      } else if (leaf.view === 'terminal' && content.terminalId) {
        // 终端会话由 restoreTerminalSessions 恢复；此处仅匹配并激活
        let session = terminalSessions().value.find(t => t.terminal_id === content.terminalId)
        if (!session) {
          // 兜底：再尝试拉取一次存活终端（可能 restoreTerminalSessions 尚未完成）
          await restoreTerminalSessions()()
          session = terminalSessions().value.find(t => t.terminal_id === content.terminalId)
        }
        if (session) {
          activeTerminalId().value = content.terminalId
        } else {
          // 终端会话已不存在：降级为空 pane
          leaf.view = 'empty'
          leaf.agentId = null
        }
      }
    } catch (e) {
      console.warn('[workspace-pane] restore content failed for pane', leaf.id, e)
      // 恢复失败：降级为空 pane，避免残留半初始化状态
      leaf.view = 'empty'
      leaf.sessionPanelId = null
      leaf.agentId = null
      leaf.diff = null
    } finally {
      // 内容恢复信息用完即清，避免残留到运行时 leaf 上
      leaf.content = null
    }
  }
  // 确保当前 Agent 与激活 pane 一致（若激活 pane 是 session）
  const activeLeaf = findWorkspacePaneById(workspacePaneTree.value, activePaneId.value)
  if (activeLeaf && activeLeaf.view === 'session' && activeLeaf.sessionPanelId) {
    const panel = panels().value.find(p => p.id === activeLeaf.sessionPanelId)
    const agent = panel?.agentId ? agentList().value.find(a => a.agent_id === panel.agentId) : null
    if (agent) await switchAgent()(agent)
  }
  // 写回规范化后的布局（content 已清空）
  persistWorkspacePaneLayout()
}

// 每次 DOM 提交后（激活 pane / 分割树变化 / 标签变化）都重新补齐一次实例：
// Vue 在 patch 时可能清掉容器里「它不认识的」Monaco DOM，导致实例 DOM 脱离文档；
// 这里在 post flush 阶段检测并重建，保证每个 file pane 始终有可见的编辑器。
watch(
  [activePaneId, workspacePaneTree, () => workspaceTabs.value.length, activeWorkspaceTabPath],
  () => {
    scheduleWorkspaceLayout()
  },
  { flush: 'post', immediate: true },
)

  return {
    EDITOR_PANEL_MIN_WIDTH,
    EDITOR_PANEL_MIN_HEIGHT,
    workspaceResizeDirections,
    PANEL_DRAG_ACTIVATION_DISTANCE,
    isWorkspaceMaximized,
    workspacePanelRectBeforeMaximize,
    saveWorkspacePanelRect,
    workspacePanelRect,
    workspacePanelInteraction,
    workspacePanelRef,
    splitWorkspaceContainerRefs,
    setSplitWorkspaceContainerRef,
    editorContainerRef,
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
    workspacePaneTree,
    activePaneId,
    maximizedPaneId,
    workspacePaneCount,
    activePane,
    findWorkspacePaneById,
    activateWorkspacePane,
    toggleMaximizeWorkspacePane,
    moveActivePaneInDirection,
    splitWorkspacePane,
    closeWorkspacePane,
    collapseWorkspacePanes,
    findWorkspacePaneBySessionPanelId,
    findWorkspacePaneByView,
    ensureAgentEditorPane,
    ensureEditorPaneForFileOpen,
    setMainViewOnLeaf,
    ensurePaneForView,
    setActivePaneView,
    setActivePaneViewForPane,
    getWorkspacePaneTitle,
    getWorkspacePaneStatus,
    getPanePanel,
    isPaneActive,
    startWorkspacePaneResize,
    persistWorkspacePaneLayout,
    restoreWorkspacePaneLayout,
    restoreWorkspacePaneContents,
    pluginExtensions,
    pluginAdminTabs,
    pluginSidebarViews,
    pluginToolPanels,
    pluginSidebarTitle,
    pluginToolPanelTitle,
    WORKSPACE_SIDEBAR_TITLES,
    workspaceSidebarTitle,
    loadPluginExtensionsForUi,
    resolvePluginExtensionComponent,
    isPluginSidebarView,
    isPluginToolView,
    pluginSidebarCompCache,
    activePluginSidebarComp,
    activePluginToolPanelComp,
  }
}
