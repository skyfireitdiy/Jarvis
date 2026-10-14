// 活动栏布局 组合式函数（Issue #222）。
//
// 把工作区左侧活动栏（WorkspacePanel.vue 的 .workspace-activity-bar）从
// 硬编码按钮改为「数据驱动渲染 + 用户偏好排序/隐藏 + 溢出收纳」：
// - 内置图标数组化（含 SVG 图标 + action 描述符），与插件图标统一抽象
// - 插件图标（pluginSidebarViews / pluginToolPanels）动态合并，默认收纳
// - 用户偏好（顺序 + 隐藏）持久化到 localStorage（jarvis_activity_bar_layout）
// - 按偏好排序/过滤后，主栏渲染 + 溢出项收纳到「更多」菜单
//
// 图标 action 描述符（供 WorkspacePanel 分发 emit）：
//   { kind: 'sidebar', view }  -> emit('setSidebarView', view)
//   { kind: 'main', view }     -> emit('setMainView', view)
//   { kind: 'open', target }   -> emit('open' + Target)
import { ref, computed, watch } from 'vue'

// localStorage 持久化 key
const STORAGE_KEY = 'jarvis_activity_bar_layout'

// 主栏默认最多直接显示的图标数；超出部分收纳到「更多」菜单。
// 实际值由 WorkspacePanel 依据侧边栏可用高度动态调整（Issue #225）。
const DEFAULT_MAX_VISIBLE = 10

// 内置活动栏图标（含 SVG 图标与 action 描述符）。
// isPlugin=false；defaultHidden 仅对插件图标有意义（内置默认显示）。
const BUILTIN_ICONS = [
  {
    id: 'agents',
    title: 'Agent 列表 (Space v a)',
    action: { kind: 'sidebar', view: 'agents' },
    icon: '<img class="workspace-activity-icon" src="/icons/jarvis-pet.svg" alt="Agent" />',
  },
  {
    id: 'files',
    title: '目录树',
    action: { kind: 'sidebar', view: 'files' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 4.5A1.5 1.5 0 0 1 3 3h2.4l1.6 1.6H13A1.5 1.5 0 0 1 14.5 6v5.5A1.5 1.5 0 0 1 13 13H3a1.5 1.5 0 0 1-1.5-1.5v-7Z"/></svg>',
  },
  {
    id: 'search',
    title: '全局搜索',
    action: { kind: 'sidebar', view: 'search' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/></svg>',
  },
  {
    id: 'git',
    title: 'Git (Space v g)',
    action: { kind: 'sidebar', view: 'git' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="5" cy="4" r="1.5"/><circle cx="5" cy="12" r="1.5"/><circle cx="11" cy="8" r="1.5"/><path d="M5 5.5v5"/><path d="M6.5 12H9.5a1.5 1.5 0 0 0 1.5-1.5V9"/></svg>',
  },
  {
    id: 'chat',
    title: '聊天室',
    action: { kind: 'main', view: 'chat' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v6a1.5 1.5 0 0 1-1.5 1.5H6.5L3.5 14v-3H3.5A1.5 1.5 0 0 1 2 9.5v-6Z"/></svg>',
  },
  {
    id: 'terminal',
    title: '终端',
    action: { kind: 'main', view: 'terminal' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5v-9Z"/><path d="M5 6l2 2-2 2"/><path d="M8.5 10H11"/></svg>',
  },
  {
    id: 'settings',
    title: '设置 (Space v s)',
    action: { kind: 'open', target: 'Settings' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="1.5"/><circle cx="8" cy="8" r="4.2"/><g stroke-width="2.4"><path d="M8 3.8v-2M10.97 5.03l1.41-1.41M12.2 8h2M10.97 10.97l1.41 1.41M8 12.2v2M5.03 10.97l-1.41 1.41M3.8 8h-2M5.03 5.03l-1.41-1.41"/></g></svg>',
  },
  {
    id: 'admin',
    title: '管理 (Space m a)',
    action: { kind: 'open', target: 'Admin' },
    adminOnly: true,
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 1.5 13 3.5v4c0 3-2 5.5-5 7-3-1.5-5-4-5-7v-4L8 1.5Z"/><path d="M5.5 8l1.7 1.7L10.5 6"/></svg>',
  },
  {
    id: 'plugins',
    title: '插件管理',
    action: { kind: 'sidebar', view: 'plugins' },
    adminOnly: true,
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.5 2.5h3a1 1 0 0 1 1 1v3h-1.2a1.3 1.3 0 0 0 0 2.6H13.5v3a1 1 0 0 1-1 1h-3v-1.2a1.3 1.3 0 0 0-2.6 0V13h-3a1 1 0 0 1-1-1V9.5h1.2a1.3 1.3 0 0 0 0-2.6H2.5v-3a1 1 0 0 1 1-1h3v1.2a1.3 1.3 0 0 0 2.6 0V2.5Z"/></svg>',
  },
  {
    id: 'manage',
    title: '增强能力清单',
    action: { kind: 'sidebar', view: 'manage' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="9" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="2.5" y="9" width="4.5" height="4.5" rx="1"/><rect x="9" y="9" width="4.5" height="4.5" rx="1"/></svg>',
  },
  {
    id: 'timers',
    title: '定时任务',
    action: { kind: 'sidebar', view: 'timers' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M8 4.5V8l2.5 1.5"/></svg>',
  },
  {
    id: 'orchestration',
    title: '编排查看',
    action: { kind: 'sidebar', view: 'orchestration' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="1.5" y="2" width="4" height="3.5" rx="1"/><rect x="1.5" y="10.5" width="4" height="3.5" rx="1"/><rect x="10.5" y="6.25" width="4" height="3.5" rx="1"/><path d="M5.5 3.75h2.5v4.25h2.5"/><path d="M5.5 12.25h2.5V8h2.5"/></svg>',
  },
  {
    id: 'topology',
    title: '网络拓扑',
    action: { kind: 'open', target: 'Topology' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="4" cy="4" r="1.5"/><circle cx="12" cy="4" r="1.5"/><circle cx="8" cy="12" r="1.5"/><path d="M5.5 4H10.5"/><path d="M5 5.5 6.8 10.5"/><path d="M11 5.5 9.2 10.5"/></svg>',
  },
  {
    id: 'docs',
    title: '使用文档 (Space m h)',
    action: { kind: 'open', target: 'Docs' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M6.3 6.4a1.7 1.7 0 1 1 2.8 1.3c-.8.6-1.1 1-1.1 1.8"/><circle cx="8" cy="11.6" r="0.4" fill="currentColor" stroke="none"/></svg>',
  },
  {
    id: 'about',
    title: '关于',
    action: { kind: 'open', target: 'About' },
    icon: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M8 7.2V11"/><circle cx="8" cy="5.2" r="0.4" fill="currentColor" stroke="none"/></svg>',
  },
]

// 插件默认图标（无 iconSvg 时）
const PLUGIN_FALLBACK_ICON =
  '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6.5 2.5a1.5 1.5 0 0 1 3 0V3h2.5a1 1 0 0 1 1 1v2.5h.5a1.5 1.5 0 0 1 0 3H13V12a1 1 0 0 1-1 1H9.5v.5a1.5 1.5 0 0 1-3 0V13H4a1 1 0 0 1-1-1V9.5h-.5a1.5 1.5 0 0 1 0-3H3V4a1 1 0 0 1 1-1h2.5v-.5Z"/></svg>'

function readLayout() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { order: [], hidden: [] }
    const data = JSON.parse(raw)
    return {
      order: Array.isArray(data.order) ? data.order.filter((x) => typeof x === 'string') : [],
      hidden: Array.isArray(data.hidden) ? data.hidden.filter((x) => typeof x === 'string') : [],
    }
  } catch (e) {
    return { order: [], hidden: [] }
  }
}

function writeLayout(layout) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(layout))
  } catch (e) {
    // localStorage 不可用（隐私模式等）时静默失败，仅本次会话生效
  }
}

export function useActivityBarLayout({ pluginSidebarViews, pluginToolPanels, isAdmin }) {
  const layout = ref(readLayout())

  // 合并内置 + 插件图标（插件图标默认收纳 defaultHidden=true）
  const allIcons = computed(() => {
    const icons = []
    for (const b of BUILTIN_ICONS) {
      if (b.adminOnly && !isAdmin.value) continue
      icons.push({ ...b, isPlugin: false, defaultHidden: false })
    }
    for (const ext of pluginSidebarViews.value || []) {
      icons.push({
        id: 'plugin-view-' + ext.id,
        title: ext.title || ext.id,
        action: { kind: 'sidebar', view: 'plugin:' + ext.id },
        icon: ext.iconSvg || PLUGIN_FALLBACK_ICON,
        isPlugin: true,
        defaultHidden: true,
      })
    }
    for (const ext of pluginToolPanels.value || []) {
      icons.push({
        id: 'plugin-tool-' + ext.id,
        title: ext.title || ext.id,
        action: { kind: 'sidebar', view: 'plugin-tool:' + ext.id },
        icon: ext.iconSvg || PLUGIN_FALLBACK_ICON,
        isPlugin: true,
        defaultHidden: true,
      })
    }
    return icons
  })

  // 用户显式隐藏的 id 集合（持久化）
  const hiddenIds = computed(() => new Set(layout.value.hidden))

  // 排序：用户 order 优先，未在 order 中的按默认顺序追加
  const orderedIcons = computed(() => {
    const orderMap = new Map()
    layout.value.order.forEach((id, idx) => orderMap.set(id, idx))
    const sorted = [...allIcons.value].sort((a, b) => {
      const hasA = orderMap.has(a.id)
      const hasB = orderMap.has(b.id)
      if (hasA && hasB) return orderMap.get(a.id) - orderMap.get(b.id)
      if (hasA) return -1
      if (hasB) return 1
      return 0
    })
    return sorted
  })

  // 可见图标（未被用户隐藏）
  const visibleIcons = computed(() =>
    orderedIcons.value.filter((ic) => !hiddenIds.value.has(ic.id))
  )

  // 主栏最多直接显示的图标数（动态，由 WorkspacePanel 按侧边栏可用高度设置）
  const maxVisible = ref(DEFAULT_MAX_VISIBLE)

  // 主栏图标（前 maxVisible 个）与收纳图标（其余）
  const mainIcons = computed(() => visibleIcons.value.slice(0, maxVisible.value))
  const moreIcons = computed(() => visibleIcons.value.slice(maxVisible.value))

  // 判断某图标是否处于激活态
  function isActive(icon, { showSidebar, sidebarView, mainView }) {
    if (icon.action.kind === 'sidebar') {
      return showSidebar && sidebarView === icon.action.view
    }
    if (icon.action.kind === 'main') {
      return mainView === icon.action.view
    }
    return false
  }

  // 分发 action 到 emit
  function dispatch(icon, emit) {
    const a = icon.action
    if (a.kind === 'sidebar') emit('setSidebarView', a.view)
    else if (a.kind === 'main') emit('setMainView', a.view)
    else if (a.kind === 'open') emit('open' + a.target)
  }

  // 用户操作
  function setHidden(id, hidden) {
    const h = new Set(layout.value.hidden)
    if (hidden) h.add(id)
    else h.delete(id)
    layout.value = { ...layout.value, hidden: [...h] }
    persist()
  }

  function move(id, dir) {
    // 在全部图标的有序列表里移动（含隐藏项，供自定义面板排序）
    const ids = orderedIcons.value.map((ic) => ic.id)
    const idx = ids.indexOf(id)
    if (idx < 0) return
    const target = idx + dir
    if (target < 0 || target >= ids.length) return
    const [moved] = ids.splice(idx, 1)
    ids.splice(target, 0, moved)
    layout.value = { ...layout.value, order: ids }
    persist()
  }

  function reset() {
    layout.value = { order: [], hidden: [] }
    persist()
  }

  function persist() {
    writeLayout(layout.value)
  }

  // 插件列表变化时，清理已不存在图标的持久化记录
  watch(allIcons, (icons) => {
    const ids = new Set(icons.map((ic) => ic.id))
    const order = layout.value.order.filter((id) => ids.has(id))
    const hidden = layout.value.hidden.filter((id) => ids.has(id))
    if (order.length !== layout.value.order.length || hidden.length !== layout.value.hidden.length) {
      layout.value = { order, hidden }
      persist()
    }
  })

  return {
    allIcons,
    orderedIcons,
    visibleIcons,
    mainIcons,
    moreIcons,
    hiddenIds,
    maxVisible,
    isActive,
    dispatch,
    setHidden,
    move,
    reset,
  }
}
