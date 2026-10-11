// useSessionPanel 单元测试
// useSessionPanel 不依赖 monaco，无需 mock monaco 模块。
// 注意：7 个依赖全部直传（ref 型 activeWindow/windowWidth，函数型 clamp/focusWindow，常量型 ACTIVE_Z_INDEX/BASE_Z_INDEX/PANEL_DRAG_ACTIVATION_DISTANCE）。
//       ref.value 赋值对象后元素被 Vue reactive 代理，引用比较需用 toStrictEqual。
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useSessionPanel } from './useSessionPanel.js'

function realClamp(value, min, max) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

// 构造测试 harness，注入全部依赖
function makeHarness(overrides = {}) {
  const activeWindow = ref(null)
  const windowWidth = ref(1024)
  const ACTIVE_Z_INDEX = 1100
  const BASE_Z_INDEX = 1000
  const PANEL_DRAG_ACTIVATION_DISTANCE = 4
  const clamp = vi.fn(realClamp)
  const focusWindow = vi.fn()

  const api = useSessionPanel({
    activeWindow,
    ACTIVE_Z_INDEX,
    BASE_Z_INDEX,
    clamp,
    windowWidth,
    PANEL_DRAG_ACTIVATION_DISTANCE,
    focusWindow,
    ...overrides,
  })

  return {
    api,
    activeWindow,
    windowWidth,
    ACTIVE_Z_INDEX,
    BASE_Z_INDEX,
    PANEL_DRAG_ACTIVATION_DISTANCE,
    clamp,
    focusWindow,
  }
}

beforeEach(() => {
  localStorage.clear()
  // 重置 window 尺寸
  Object.defineProperty(window, 'innerWidth', { value: 1280, configurable: true, writable: true })
  Object.defineProperty(window, 'innerHeight', { value: 800, configurable: true, writable: true })
  vi.restoreAllMocks()
})

describe('useSessionPanel 常量与状态', () => {
  it('暴露常量与初始状态', () => {
    const { api } = makeHarness()
    expect(api.SESSION_PANEL_MIN_WIDTH).toBe(400)
    expect(api.SESSION_PANEL_MIN_HEIGHT).toBe(300)
    expect(api.SESSION_PANEL_STORAGE_KEY_PREFIX).toBe('jarvis_session_panel_rect_')
    expect(api.sessionResizeDirections).toEqual(['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'])
    expect(api.sessionPanelRects.value).toEqual({})
    expect(api.sessionPanelInteraction.value).toEqual({
      active: false,
      mode: null,
      direction: null,
      panelId: null,
      startX: 0,
      startY: 0,
      startTop: 0,
      startLeft: 0,
      startWidth: 0,
      startHeight: 0,
    })
  })
})

describe('useSessionPanel 矩形持久化', () => {
  it('getDefaultSessionPanelRect 返回默认矩形（左侧按窗口宽度）', () => {
    const { api } = makeHarness()
    const rect = api.getDefaultSessionPanelRect('p1')
    expect(rect).toEqual({ top: 80, left: Math.max(1280 - 824, 16), width: 600, height: 500 })
  })

  it('getDefaultSessionPanelRect 在窄窗口下 left 最小为 16', () => {
    const { api } = makeHarness()
    window.innerWidth = 500
    const rect = api.getDefaultSessionPanelRect('p1')
    expect(rect.left).toBe(16)
  })

  it('loadSessionPanelRect 无存档时返回默认矩形', () => {
    const { api } = makeHarness()
    const rect = api.loadSessionPanelRect('p1')
    expect(rect).toEqual({ top: 80, left: Math.max(1280 - 824, 16), width: 600, height: 500 })
  })

  it('loadSessionPanelRect 读取有效存档', () => {
    const { api } = makeHarness()
    localStorage.setItem('jarvis_session_panel_rect_p1', JSON.stringify({ top: 10, left: 20, width: 300, height: 200 }))
    const rect = api.loadSessionPanelRect('p1')
    expect(rect).toEqual({ top: 10, left: 20, width: 300, height: 200 })
  })

  it('loadSessionPanelRect 字段非法时回退默认', () => {
    const { api } = makeHarness()
    localStorage.setItem('jarvis_session_panel_rect_p1', JSON.stringify({ top: 'x', left: 20, width: 300, height: 200 }))
    const rect = api.loadSessionPanelRect('p1')
    expect(rect).toEqual({ top: 80, left: Math.max(1280 - 824, 16), width: 600, height: 500 })
  })

  it('loadSessionPanelRect JSON 解析失败时回退默认', () => {
    const { api } = makeHarness()
    localStorage.setItem('jarvis_session_panel_rect_p1', '{invalid json')
    const rect = api.loadSessionPanelRect('p1')
    expect(rect).toEqual({ top: 80, left: Math.max(1280 - 824, 16), width: 600, height: 500 })
  })

  it('saveSessionPanelRect 将当前 rect 写入 localStorage', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 10, left: 20, width: 300, height: 200 } }
    api.saveSessionPanelRect('p1')
    expect(JSON.parse(localStorage.getItem('jarvis_session_panel_rect_p1'))).toEqual({ top: 10, left: 20, width: 300, height: 200 })
  })

  it('saveSessionPanelRect 无 rect 时不写入', () => {
    const { api } = makeHarness()
    api.saveSessionPanelRect('p1')
    expect(localStorage.getItem('jarvis_session_panel_rect_p1')).toBeNull()
  })
})

describe('useSessionPanel 样式与边界', () => {
  it('getSessionPanelStyle 无 rect 时返回空对象', () => {
    const { api } = makeHarness()
    expect(api.getSessionPanelStyle('p1')).toEqual({})
  })

  it('getSessionPanelStyle 返回样式，activeWindow 为 session 时用 ACTIVE_Z_INDEX', () => {
    const { api, activeWindow } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 10, left: 20, width: 300, height: 200 } }
    activeWindow.value = 'session'
    expect(api.getSessionPanelStyle('p1')).toEqual({
      top: '10px',
      left: '20px',
      width: '300px',
      height: '200px',
      zIndex: 1100,
    })
  })

  it('getSessionPanelStyle 非 session 窗口用 BASE_Z_INDEX', () => {
    const { api, activeWindow } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 10, left: 20, width: 300, height: 200 } }
    activeWindow.value = 'chat'
    expect(api.getSessionPanelStyle('p1').zIndex).toBe(1000)
  })

  it('getSessionPanelBounds 返回窗口边界', () => {
    const { api } = makeHarness()
    expect(api.getSessionPanelBounds()).toEqual({
      minTop: 0,
      minLeft: 0,
      maxLeft: 1280 - 100,
      maxTop: 800 - 32,
    })
  })

  it('ensureSessionPanelInViewport 修正越界尺寸与位置', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: -50, left: -100, width: 50, height: 50 } }
    api.ensureSessionPanelInViewport('p1')
    const rect = api.sessionPanelRects.value.p1
    expect(rect.width).toBe(400)
    expect(rect.height).toBe(300)
    expect(rect.left).toBe(0)
    expect(rect.top).toBe(0)
  })

  it('ensureSessionPanelInViewport 无 rect 时直接返回', () => {
    const { api } = makeHarness()
    expect(() => api.ensureSessionPanelInViewport('p1')).not.toThrow()
  })
})

describe('useSessionPanel 拖拽移动', () => {
  it('startSessionPanelMove 在窄窗口（<=768）下不执行', () => {
    const { api, windowWidth, focusWindow } = makeHarness()
    windowWidth.value = 768
    const event = { target: { closest: vi.fn(() => null) }, clientX: 100, clientY: 100 }
    api.startSessionPanelMove(event, 'p1')
    expect(focusWindow).not.toHaveBeenCalled()
    expect(api.sessionPanelInteraction.value.active).toBe(false)
    expect(api.sessionPanelInteraction.value.mode).toBeNull()
  })

  it('startSessionPanelMove 命中 header actions 时不执行', () => {
    const { api, focusWindow } = makeHarness()
    const event = { target: { closest: vi.fn(() => document.createElement('div')) }, clientX: 100, clientY: 100 }
    api.startSessionPanelMove(event, 'p1')
    expect(focusWindow).not.toHaveBeenCalled()
  })

  it('startSessionPanelMove 无 rect 时 focusWindow 仍被调用但不设置 interaction', () => {
    const { api, focusWindow } = makeHarness()
    const event = { target: { closest: vi.fn(() => null) }, clientX: 100, clientY: 100 }
    api.startSessionPanelMove(event, 'p1')
    // 原代码中 focusWindow('session') 在 rect 检查之前调用
    expect(focusWindow).toHaveBeenCalledWith('session')
    expect(api.sessionPanelInteraction.value.mode).toBeNull()
  })

  it('startSessionPanelMove 设置 interaction 并注册监听', () => {
    const { api, focusWindow } = makeHarness()
    const addEventListenerSpy = vi.spyOn(document, 'addEventListener')
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    const event = { target: { closest: vi.fn(() => null) }, clientX: 100, clientY: 100 }
    api.startSessionPanelMove(event, 'p1')
    expect(focusWindow).toHaveBeenCalledWith('session')
    expect(api.sessionPanelInteraction.value).toMatchObject({
      active: false,
      mode: 'move',
      direction: null,
      panelId: 'p1',
      startX: 100,
      startY: 100,
      startTop: 80,
      startLeft: 100,
      startWidth: 600,
      startHeight: 500,
    })
    expect(addEventListenerSpy).toHaveBeenCalledWith('mousemove', api.onSessionPanelPointerMove)
    expect(addEventListenerSpy).toHaveBeenCalledWith('mouseup', api.stopSessionPanelInteraction)
  })

  it('onSessionPanelPointerMove 移动距离小于激活阈值时不移动', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelMove({ target: { closest: () => null }, clientX: 100, clientY: 100 }, 'p1')
    api.onSessionPanelPointerMove({ clientX: 102, clientY: 100 })
    expect(api.sessionPanelInteraction.value.active).toBe(false)
    expect(api.sessionPanelRects.value.p1.left).toBe(100)
    expect(api.sessionPanelRects.value.p1.top).toBe(80)
  })

  it('onSessionPanelPointerMove 超过阈值后激活并移动', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelMove({ target: { closest: () => null }, clientX: 100, clientY: 100 }, 'p1')
    const preventDefault = vi.fn()
    api.onSessionPanelPointerMove({ clientX: 150, clientY: 130, preventDefault })
    expect(api.sessionPanelInteraction.value.active).toBe(true)
    expect(preventDefault).toHaveBeenCalled()
    expect(api.sessionPanelRects.value.p1.left).toBe(150)
    expect(api.sessionPanelRects.value.p1.top).toBe(110)
  })

  it('onSessionPanelPointerMove 移动被边界 clamp', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelMove({ target: { closest: () => null }, clientX: 100, clientY: 100 }, 'p1')
    // 大幅向右下移动，应被 maxLeft/maxTop 截断
    api.onSessionPanelPointerMove({ clientX: 10000, clientY: 10000, preventDefault: () => {} })
    const rect = api.sessionPanelRects.value.p1
    expect(rect.left).toBeLessThanOrEqual(1280 - 100)
    expect(rect.top).toBeLessThanOrEqual(800 - 32)
  })

  it('onSessionPanelPointerMove 无 rect 时直接返回', () => {
    const { api } = makeHarness()
    expect(() => api.onSessionPanelPointerMove({ clientX: 10, clientY: 10 })).not.toThrow()
  })
})

describe('useSessionPanel 拖拽缩放', () => {
  it('startSessionPanelResize 在窄窗口（<=768）下不执行', () => {
    const { api, windowWidth } = makeHarness()
    windowWidth.value = 768
    const event = { clientX: 100, clientY: 100, preventDefault: vi.fn(), stopPropagation: vi.fn() }
    api.startSessionPanelResize(event, 'e', 'p1')
    expect(api.sessionPanelInteraction.value.mode).toBeNull()
  })

  it('startSessionPanelResize 无 rect 时不执行', () => {
    const { api } = makeHarness()
    const event = { clientX: 100, clientY: 100, preventDefault: vi.fn(), stopPropagation: vi.fn() }
    api.startSessionPanelResize(event, 'e', 'p1')
    expect(api.sessionPanelInteraction.value.mode).toBeNull()
  })

  it('startSessionPanelResize 设置 interaction 并注册监听、阻止冒泡', () => {
    const { api } = makeHarness()
    const addEventListenerSpy = vi.spyOn(document, 'addEventListener')
    const preventDefault = vi.fn()
    const stopPropagation = vi.fn()
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelResize({ clientX: 100, clientY: 100, preventDefault, stopPropagation }, 'se', 'p1')
    expect(api.sessionPanelInteraction.value).toMatchObject({
      active: true,
      mode: 'resize',
      direction: 'se',
      panelId: 'p1',
    })
    expect(preventDefault).toHaveBeenCalled()
    expect(stopPropagation).toHaveBeenCalled()
    expect(addEventListenerSpy).toHaveBeenCalledWith('mousemove', api.onSessionPanelPointerMove)
    expect(addEventListenerSpy).toHaveBeenCalledWith('mouseup', api.stopSessionPanelInteraction)
  })

  it('onSessionPanelPointerMove resize 东向（e）改变宽度', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelResize({ clientX: 100, clientY: 100, preventDefault: () => {}, stopPropagation: () => {} }, 'e', 'p1')
    api.onSessionPanelPointerMove({ clientX: 200, clientY: 100 })
    const rect = api.sessionPanelRects.value.p1
    expect(rect.width).toBe(700)
    expect(rect.height).toBe(500)
    expect(rect.left).toBe(100)
  })

  it('onSessionPanelPointerMove resize 南向（s）改变高度', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelResize({ clientX: 100, clientY: 100, preventDefault: () => {}, stopPropagation: () => {} }, 's', 'p1')
    api.onSessionPanelPointerMove({ clientX: 100, clientY: 200 })
    const rect = api.sessionPanelRects.value.p1
    expect(rect.height).toBe(600)
    expect(rect.width).toBe(600)
  })

  it('onSessionPanelPointerMove resize 西向（w）改变宽度与 left', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelResize({ clientX: 100, clientY: 100, preventDefault: () => {}, stopPropagation: () => {} }, 'w', 'p1')
    api.onSessionPanelPointerMove({ clientX: 50, clientY: 100 })
    const rect = api.sessionPanelRects.value.p1
    expect(rect.left).toBe(50)
    expect(rect.width).toBe(650)
  })

  it('onSessionPanelPointerMove resize 北向（n）改变高度与 top', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelResize({ clientX: 100, clientY: 100, preventDefault: () => {}, stopPropagation: () => {} }, 'n', 'p1')
    api.onSessionPanelPointerMove({ clientX: 100, clientY: 50 })
    const rect = api.sessionPanelRects.value.p1
    // startTop=80, deltaY=-50 → desiredTop=clamp(30,0,280)=30, nextHeight=500-(-50)=550
    expect(rect.top).toBe(30)
    expect(rect.height).toBe(550)
  })

  it('onSessionPanelPointerMove resize 东向时宽度受最小宽度约束', () => {
    const { api } = makeHarness()
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelResize({ clientX: 100, clientY: 100, preventDefault: () => {}, stopPropagation: () => {} }, 'e', 'p1')
    // 向左拖到负值，宽度应被 clamp 到 400
    api.onSessionPanelPointerMove({ clientX: -1000, clientY: 100 })
    expect(api.sessionPanelRects.value.p1.width).toBe(400)
  })
})

describe('useSessionPanel 停止交互', () => {
  it('stopSessionPanelInteraction 重置状态并移除监听、保存 rect', () => {
    const { api } = makeHarness()
    const removeEventListenerSpy = vi.spyOn(document, 'removeEventListener')
    api.sessionPanelRects.value = { p1: { top: 80, left: 100, width: 600, height: 500 } }
    api.startSessionPanelMove({ target: { closest: () => null }, clientX: 100, clientY: 100 }, 'p1')
    api.stopSessionPanelInteraction()
    expect(api.sessionPanelInteraction.value).toEqual({
      active: false,
      mode: null,
      direction: null,
      panelId: null,
      startX: 0,
      startY: 0,
      startTop: 0,
      startLeft: 0,
      startWidth: 0,
      startHeight: 0,
    })
    expect(removeEventListenerSpy).toHaveBeenCalledWith('mousemove', api.onSessionPanelPointerMove)
    expect(removeEventListenerSpy).toHaveBeenCalledWith('mouseup', api.stopSessionPanelInteraction)
    expect(JSON.parse(localStorage.getItem('jarvis_session_panel_rect_p1'))).toEqual({ top: 80, left: 100, width: 600, height: 500 })
  })

  it('stopSessionPanelInteraction 无 panelId 时不保存', () => {
    const { api } = makeHarness()
    api.stopSessionPanelInteraction()
    expect(localStorage.getItem('jarvis_session_panel_rect_p1')).toBeNull()
  })
})
