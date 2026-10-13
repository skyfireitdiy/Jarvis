// useActivityBarLayout 单元测试（Issue #222）
// 覆盖：图标合并、排序、隐藏、收纳（更多菜单）、持久化、dispatch、reset
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useActivityBarLayout } from './useActivityBarLayout.js'

// 内存版 localStorage mock
const store = {}
const localStorageMock = {
  getItem: vi.fn((k) => (k in store ? store[k] : null)),
  setItem: vi.fn((k, v) => { store[k] = String(v) }),
  removeItem: vi.fn((k) => { delete store[k] }),
  clear: vi.fn(() => { for (const k in store) delete store[k] }),
}
vi.stubGlobal('localStorage', localStorageMock)

function makeHarness({ sidebarViews = [], toolPanels = [], isAdmin = true, layout = null } = {}) {
  if (layout) {
    store['jarvis_activity_bar_layout'] = JSON.stringify(layout)
  } else {
    delete store['jarvis_activity_bar_layout']
  }
  const pluginSidebarViews = ref(sidebarViews)
  const pluginToolPanels = ref(toolPanels)
  const admin = ref(isAdmin)
  const api = useActivityBarLayout({
    pluginSidebarViews,
    pluginToolPanels,
    isAdmin: admin,
  })
  return { api, pluginSidebarViews, pluginToolPanels, admin }
}

function makeExt({ id, title, iconSvg }) {
  return { id, title, iconSvg }
}

beforeEach(() => {
  localStorageMock.clear()
  localStorageMock.getItem.mockClear()
  localStorageMock.setItem.mockClear()
})

describe('useActivityBarLayout', () => {
  it('合并内置图标与插件图标，插件默认收纳', () => {
    const { api } = makeHarness({
      sidebarViews: [makeExt({ id: 'p1', title: '插件1' })],
      toolPanels: [makeExt({ id: 'p2', title: '插件2' })],
    })
    // 15 内置 + 2 插件
    expect(api.allIcons.value.length).toBe(17)
    const pluginIcon = api.allIcons.value.find((i) => i.id === 'plugin-view-p1')
    expect(pluginIcon.isPlugin).toBe(true)
    expect(pluginIcon.defaultHidden).toBe(true)
    // 插件默认未隐藏（defaultHidden 仅表示默认收纳，不自动进 hidden）
    expect(api.hiddenIds.value.has('plugin-view-p1')).toBe(false)
  })

  it('非管理员不显示 adminOnly 图标', () => {
    const { api } = makeHarness({ isAdmin: false })
    const ids = api.allIcons.value.map((i) => i.id)
    expect(ids).not.toContain('admin')
    expect(ids).not.toContain('plugins')
    expect(ids).toContain('agents')
  })

  it('主栏最多显示 MAX_VISIBLE 个，超出收纳到 moreIcons', () => {
    const { api } = makeHarness({
      sidebarViews: [makeExt({ id: 'p1' }), makeExt({ id: 'p2' }), makeExt({ id: 'p3' }), makeExt({ id: 'p4' })],
    })
    // 15 内置 + 4 插件 = 19
    expect(api.mainIcons.value.length).toBe(api.MAX_VISIBLE)
    expect(api.moreIcons.value.length).toBe(19 - api.MAX_VISIBLE)
  })

  it('隐藏图标后从主栏移除', () => {
    const { api } = makeHarness()
    // 选一个位于主栏前 10 个内的内置图标（git 在索引 3）
    const target = 'git'
    expect(api.mainIcons.value.map((i) => i.id)).toContain(target)
    api.setHidden(target, true)
    expect(api.hiddenIds.value.has(target)).toBe(true)
    expect(api.mainIcons.value.map((i) => i.id)).not.toContain(target)
    // 再次显示恢复
    api.setHidden(target, false)
    expect(api.mainIcons.value.map((i) => i.id)).toContain(target)
  })

  it('move 在全部图标有序列表内移动并持久化', () => {
    const { api } = makeHarness()
    const ids = () => api.orderedIcons.value.map((i) => i.id)
    const before = ids()
    api.move(before[0], 1)
    const after = ids()
    expect(after[0]).toBe(before[1])
    expect(after[1]).toBe(before[0])
    // 持久化
    const saved = JSON.parse(store['jarvis_activity_bar_layout'])
    expect(saved.order).toEqual(after)
  })

  it('move 越界时不改变顺序', () => {
    const { api } = makeHarness()
    const before = api.orderedIcons.value.map((i) => i.id)
    api.move(before[0], -1)
    expect(api.orderedIcons.value.map((i) => i.id)).toEqual(before)
    api.move(before[before.length - 1], 1)
    expect(api.orderedIcons.value.map((i) => i.id)).toEqual(before)
  })

  it('reset 清空顺序与隐藏并持久化', () => {
    const { api } = makeHarness()
    api.setHidden('about', true)
    api.move('about', -1)
    api.reset()
    expect(api.hiddenIds.value.size).toBe(0)
    const saved = JSON.parse(store['jarvis_activity_bar_layout'])
    expect(saved.order).toEqual([])
    expect(saved.hidden).toEqual([])
  })

  it('从持久化布局恢复顺序与隐藏', () => {
    const ids = ['about', 'docs', 'topology']
    const { api } = makeHarness({ layout: { order: ids, hidden: ['timers'] } })
    const ordered = api.orderedIcons.value.map((i) => i.id)
    expect(ordered.slice(0, 3)).toEqual(ids)
    expect(api.hiddenIds.value.has('timers')).toBe(true)
    expect(api.mainIcons.value.map((i) => i.id)).not.toContain('timers')
  })

  it('dispatch 按 action 分发到对应 emit', () => {
    const { api } = makeHarness()
    const emit = vi.fn()
    const sidebar = api.allIcons.value.find((i) => i.action.kind === 'sidebar')
    const main = api.allIcons.value.find((i) => i.action.kind === 'main')
    const open = api.allIcons.value.find((i) => i.action.kind === 'open')
    api.dispatch(sidebar, emit)
    expect(emit).toHaveBeenCalledWith('setSidebarView', sidebar.action.view)
    api.dispatch(main, emit)
    expect(emit).toHaveBeenCalledWith('setMainView', main.action.view)
    api.dispatch(open, emit)
    expect(emit).toHaveBeenCalledWith('open' + open.action.target)
  })

  it('isActive 判断侧边栏/主视图激活态', () => {
    const { api } = makeHarness()
    const sidebar = api.allIcons.value.find((i) => i.action.kind === 'sidebar')
    const main = api.allIcons.value.find((i) => i.action.kind === 'main')
    expect(api.isActive(sidebar, { showSidebar: true, sidebarView: sidebar.action.view, mainView: 'file' })).toBe(true)
    expect(api.isActive(sidebar, { showSidebar: false, sidebarView: sidebar.action.view, mainView: 'file' })).toBe(false)
    expect(api.isActive(main, { showSidebar: true, sidebarView: 'agents', mainView: main.action.view })).toBe(true)
  })

  it('插件列表变化时清理已消失图标的持久化记录', () => {
    const { pluginSidebarViews } = makeHarness({
      sidebarViews: [makeExt({ id: 'p1' })],
      layout: { order: ['plugin-view-p1', 'about'], hidden: ['plugin-view-p1'] },
    })
    expect(api_hidden_has_plugin()).toBe(true)
    // 移除插件
    pluginSidebarViews.value = []
    // watch 触发清理
    return new Promise((resolve) => setTimeout(resolve, 0)).then(() => {
      const saved = JSON.parse(store['jarvis_activity_bar_layout'])
      expect(saved.order).not.toContain('plugin-view-p1')
      expect(saved.hidden).not.toContain('plugin-view-p1')
    })
  })
})

function api_hidden_has_plugin() {
  // 辅助：读取当前 harness 的 hidden（简化，直接查 localStorage）
  const saved = JSON.parse(store['jarvis_activity_bar_layout'] || '{"hidden":[]}')
  return saved.hidden.includes('plugin-view-p1')
}
