// useFocus 单元测试
// useFocus 不依赖 monaco，无需 mock monaco 模块。
// 依赖注入全部为 getter 形式：ref 型使用处 xxx().value 二次求值，函数型 xxx()() 二次求值，
// 普通 Map（sessionPanelRefs）直接 xxx().get() 调用。
// 注意：ref.value 赋值数组/对象后元素被 Vue reactive 代理，引用比较需用 toStrictEqual 或比较字段。
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useFocus } from './useFocus.js'

// 构造测试 harness，注入全部 getter 依赖
function makeHarness(overrides = {}) {
  const panels = ref([])
  const sessionPanelRefs = new Map()
  const showTerminalPanel = ref(false)
  const showWorkspacePanel = ref(false)
  const showChatPanel = ref(false)
  const activeWindow = ref(null)
  const focusWindow = vi.fn()
  const getActiveWorkspaceView = vi.fn(() => null)
  const activatePanel = vi.fn()
  const isAnyModalOpen = vi.fn(() => false)
  const focusCurrentPanelInput = vi.fn()
  const getCurrentPanel = vi.fn(() => null)
  const terminalSessions = ref([])
  const activeTerminalId = ref(null)

  const api = useFocus({
    panels: () => panels,
    sessionPanelRefs: () => sessionPanelRefs,
    showTerminalPanel: () => showTerminalPanel,
    showWorkspacePanel: () => showWorkspacePanel,
    showChatPanel: () => showChatPanel,
    activeWindow: () => activeWindow,
    focusWindow: () => focusWindow,
    getActiveWorkspaceView: () => getActiveWorkspaceView,
    activatePanel: () => activatePanel,
    isAnyModalOpen: () => isAnyModalOpen,
    focusCurrentPanelInput: () => focusCurrentPanelInput,
    getCurrentPanel: () => getCurrentPanel,
    terminalSessions: () => terminalSessions,
    activeTerminalId: () => activeTerminalId,
    ...overrides,
  })
  return {
    api,
    panels,
    sessionPanelRefs,
    showTerminalPanel,
    showWorkspacePanel,
    showChatPanel,
    activeWindow,
    focusWindow,
    getActiveWorkspaceView,
    activatePanel,
    isAnyModalOpen,
    focusCurrentPanelInput,
    getCurrentPanel,
    terminalSessions,
    activeTerminalId,
  }
}

beforeEach(() => {
  vi.restoreAllMocks()
  // 清空 document.body，避免测试间 DOM 残留
  document.body.innerHTML = ''
})

describe('focusActiveTerminal', () => {
  it('聚焦活动终端并返回 true', () => {
    const { api, terminalSessions, activeTerminalId } = makeHarness()
    const focus = vi.fn()
    terminalSessions.value = [
      { terminal_id: 't1', terminal: { focus } },
      { terminal_id: 't2', terminal: { focus: vi.fn() } },
    ]
    activeTerminalId.value = 't1'
    expect(api.focusActiveTerminal()).toBe(true)
    expect(focus).toHaveBeenCalled()
  })

  it('无活动终端时聚焦第一个终端', () => {
    const { api, terminalSessions } = makeHarness()
    const focus = vi.fn()
    terminalSessions.value = [{ terminal_id: 't1', terminal: { focus } }]
    expect(api.focusActiveTerminal()).toBe(true)
    expect(focus).toHaveBeenCalled()
  })

  it('无终端时返回 false', () => {
    const { api } = makeHarness()
    expect(api.focusActiveTerminal()).toBe(false)
  })
})

describe('focusZoneContainer', () => {
  it('无 tabindex 时设置 tabindex=-1 并聚焦', () => {
    const { api } = makeHarness()
    const focus = vi.fn()
    const el = { hasAttribute: () => false, setAttribute: vi.fn(), focus }
    api.focusZoneContainer(el)
    expect(el.setAttribute).toHaveBeenCalledWith('tabindex', '-1')
    expect(focus).toHaveBeenCalledWith({ preventScroll: true })
  })

  it('已有 tabindex 时不重复设置', () => {
    const { api } = makeHarness()
    const focus = vi.fn()
    const el = { hasAttribute: () => true, setAttribute: vi.fn(), focus }
    api.focusZoneContainer(el)
    expect(el.setAttribute).not.toHaveBeenCalled()
    expect(focus).toHaveBeenCalled()
  })

  it('空元素直接返回', () => {
    const { api } = makeHarness()
    expect(() => api.focusZoneContainer(null)).not.toThrow()
  })
})

describe('isFocusableTarget', () => {
  it('可聚焦元素返回 true', () => {
    const { api } = makeHarness()
    const el = { focus: () => {}, disabled: false, getAttribute: () => '0' }
    expect(api.isFocusableTarget(el)).toBe(true)
  })

  it('disabled 元素返回 false', () => {
    const { api } = makeHarness()
    expect(api.isFocusableTarget({ focus: () => {}, disabled: true })).toBe(false)
    expect(api.isFocusableTarget({ focus: () => {}, hasAttribute: () => true, getAttribute: () => '0' })).toBe(false)
  })

  it('tabindex=-1 元素返回 false', () => {
    const { api } = makeHarness()
    const el = { focus: () => {}, disabled: false, getAttribute: () => '-1' }
    expect(api.isFocusableTarget(el)).toBe(false)
  })

  it('无 focus 方法返回 false', () => {
    const { api } = makeHarness()
    expect(api.isFocusableTarget({})).toBe(false)
    expect(api.isFocusableTarget(null)).toBe(false)
  })
})

describe('focusFirstIn', () => {
  it('聚焦区域内首个可聚焦元素', () => {
    const { api } = makeHarness()
    const focus = vi.fn()
    const target = { focus, disabled: false, getAttribute: () => '0' }
    const container = { querySelectorAll: () => [target] }
    api.focusFirstIn(container)
    expect(focus).toHaveBeenCalledWith({ preventScroll: true })
  })

  it('跳过不可聚焦元素，回退聚焦容器', () => {
    const { api } = makeHarness()
    const containerFocus = vi.fn()
    const disabled = { focus: () => {}, disabled: true, getAttribute: () => '0' }
    const container = {
      querySelectorAll: () => [disabled],
      hasAttribute: () => false,
      setAttribute: vi.fn(),
      focus: containerFocus,
    }
    api.focusFirstIn(container)
    expect(containerFocus).toHaveBeenCalled()
  })

  it('支持自定义 selector', () => {
    const { api } = makeHarness()
    const focus = vi.fn()
    const target = { focus, disabled: false, getAttribute: () => '0' }
    const container = { querySelectorAll: (sel) => { expect(sel).toBe('.chat-input:not([disabled])'); return [target] } }
    api.focusFirstIn(container, '.chat-input')
    expect(focus).toHaveBeenCalled()
  })

  it('空元素直接返回', () => {
    const { api } = makeHarness()
    expect(() => api.focusFirstIn(null)).not.toThrow()
  })
})

describe('getFocusZones', () => {
  it('按可见区域构建 zones（session/terminal/workspace/chat）', () => {
    const { api, panels, showTerminalPanel, showWorkspacePanel, showChatPanel } = makeHarness()
    panels.value = [{ id: 'p1', agentId: 'a1' }, { id: 'p2', agentId: null }]
    showTerminalPanel.value = true
    showWorkspacePanel.value = true
    showChatPanel.value = true
    const zones = api.getFocusZones()
    expect(zones.map(z => z.key)).toEqual(['session:p1', 'terminal', 'workspace', 'chat'])
  })

  it('无 agentId 的 panel 不生成 zone', () => {
    const { api, panels } = makeHarness()
    panels.value = [{ id: 'p1', agentId: null }]
    expect(api.getFocusZones()).toEqual([])
  })

  it('全部面板关闭时返回空数组', () => {
    const { api } = makeHarness()
    expect(api.getFocusZones()).toEqual([])
  })

  it('session zone 的 focus 调用 activatePanel 与 focusCurrentPanelInput', async () => {
    const { api, panels, activatePanel, focusCurrentPanelInput } = makeHarness()
    panels.value = [{ id: 'p1', agentId: 'a1' }]
    const zones = api.getFocusZones()
    zones[0].focus()
    expect(activatePanel).toHaveBeenCalledWith('p1')
    await new Promise((r) => setTimeout(r, 0))
    expect(focusCurrentPanelInput).toHaveBeenCalledWith(true)
  })

  it('terminal zone 的 focus 调用 focusWindow', async () => {
    const { api, showTerminalPanel, focusWindow } = makeHarness()
    showTerminalPanel.value = true
    const zones = api.getFocusZones()
    zones[0].focus()
    expect(focusWindow).toHaveBeenCalledWith('terminal')
    await new Promise((r) => setTimeout(r, 0))
  })
})

describe('getFocusedZoneKey', () => {
  it('根据 document.activeElement 推断区域', () => {
    const { api } = makeHarness()
    const el = { tagName: 'INPUT' }
    const termEl = { contains: (e) => e === el }
    document.querySelector = vi.fn((sel) => sel === '.terminal-panel' ? termEl : null)
    Object.defineProperty(document, 'activeElement', { value: el, configurable: true })
    expect(api.getFocusedZoneKey()).toBe('terminal')
  })

  it('session panel 内的元素推断为 session key', () => {
    const { api, panels, sessionPanelRefs } = makeHarness()
    panels.value = [{ id: 'p1', agentId: 'a1' }]
    const el = { tagName: 'BUTTON' }
    const root = { $el: { contains: (e) => e === el } }
    sessionPanelRefs.set('p1', root)
    document.querySelector = vi.fn(() => null)
    Object.defineProperty(document, 'activeElement', { value: el, configurable: true })
    expect(api.getFocusedZoneKey()).toBe('session:p1')
  })

  it('无焦点时返回 null', () => {
    const { api } = makeHarness()
    Object.defineProperty(document, 'activeElement', { value: null, configurable: true })
    expect(api.getFocusedZoneKey()).toBeNull()
  })
})

describe('getActiveFocusZoneKey', () => {
  it('优先依据真实焦点位置', () => {
    const { api } = makeHarness()
    const el = { tagName: 'INPUT' }
    const termEl = { contains: (e) => e === el }
    document.querySelector = vi.fn((sel) => sel === '.terminal-panel' ? termEl : null)
    Object.defineProperty(document, 'activeElement', { value: el, configurable: true })
    expect(api.getActiveFocusZoneKey()).toBe('terminal')
  })

  it('无真实焦点时回退 activeWindow', () => {
    const { api, activeWindow, showTerminalPanel } = makeHarness()
    Object.defineProperty(document, 'activeElement', { value: null, configurable: true })
    activeWindow.value = 'terminal'
    showTerminalPanel.value = true
    expect(api.getActiveFocusZoneKey()).toBe('terminal')
  })

  it('无真实焦点且无 activeWindow 时回退当前 panel', () => {
    const { api, getCurrentPanel } = makeHarness()
    Object.defineProperty(document, 'activeElement', { value: null, configurable: true })
    getCurrentPanel.mockReturnValue({ id: 'p1', agentId: 'a1' })
    expect(api.getActiveFocusZoneKey()).toBe('session:p1')
  })

  it('全部不可用时返回 null', () => {
    const { api } = makeHarness()
    Object.defineProperty(document, 'activeElement', { value: null, configurable: true })
    expect(api.getActiveFocusZoneKey()).toBeNull()
  })
})

describe('getFocusZoneRect', () => {
  it('session zone 取 sessionPanelRefs 的矩形', () => {
    const { api, sessionPanelRefs } = makeHarness()
    const rect = { left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100 }
    sessionPanelRefs.set('p1', { $el: { getBoundingClientRect: () => rect } })
    expect(api.getFocusZoneRect({ kind: 'session', key: 'session:p1' })).toEqual(rect)
  })

  it('terminal zone 取 .terminal-panel 的矩形', () => {
    const { api } = makeHarness()
    const rect = { left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100 }
    document.querySelector = vi.fn(() => ({ getBoundingClientRect: () => rect }))
    expect(api.getFocusZoneRect({ kind: 'terminal' })).toEqual(rect)
  })

  it('不可见（宽高为 0）时返回 null', () => {
    const { api } = makeHarness()
    document.querySelector = vi.fn(() => ({ getBoundingClientRect: () => ({ left: 0, top: 0, width: 0, height: 0 }) }))
    expect(api.getFocusZoneRect({ kind: 'terminal' })).toBeNull()
  })

  it('无 DOM 时返回 null', () => {
    const { api } = makeHarness()
    document.querySelector = vi.fn(() => null)
    expect(api.getFocusZoneRect({ kind: 'terminal' })).toBeNull()
    expect(api.getFocusZoneRect(null)).toBeNull()
  })
})

describe('scoreFocusZoneByDirection', () => {
  const cur = { left: 100, top: 100, width: 100, height: 100, right: 200, bottom: 200 }
  const right = { left: 300, top: 100, width: 100, height: 100, right: 400, bottom: 200 }
  const left = { left: 0, top: 100, width: 100, height: 100, right: 100, bottom: 200 }
  const up = { left: 100, top: 0, width: 100, height: 100, right: 200, bottom: 100 }
  const down = { left: 100, top: 300, width: 100, height: 100, right: 200, bottom: 400 }

  it('右侧区域对 right 方向返回正打分', () => {
    const { api } = makeHarness()
    const score = api.scoreFocusZoneByDirection(cur, right, 'right')
    expect(score).toBeGreaterThan(0)
  })

  it('左侧区域对 right 方向返回 null（不在右侧）', () => {
    const { api } = makeHarness()
    expect(api.scoreFocusZoneByDirection(cur, left, 'right')).toBeNull()
  })

  it('四个方向均正确判定', () => {
    const { api } = makeHarness()
    expect(api.scoreFocusZoneByDirection(cur, left, 'left')).not.toBeNull()
    expect(api.scoreFocusZoneByDirection(cur, up, 'up')).not.toBeNull()
    expect(api.scoreFocusZoneByDirection(cur, down, 'down')).not.toBeNull()
    expect(api.scoreFocusZoneByDirection(cur, right, 'left')).toBeNull()
    expect(api.scoreFocusZoneByDirection(cur, right, 'up')).toBeNull()
    expect(api.scoreFocusZoneByDirection(cur, right, 'down')).toBeNull()
  })

  it('非法方向返回 null', () => {
    const { api } = makeHarness()
    expect(api.scoreFocusZoneByDirection(cur, right, 'diagonal')).toBeNull()
  })
})

describe('moveFocusInDirection', () => {
  it('无 zones 时直接返回', () => {
    const { api } = makeHarness()
    expect(() => api.moveFocusInDirection('right')).not.toThrow()
  })

  it('无当前区域矩形时直接返回', () => {
    const { api, panels, showTerminalPanel } = makeHarness()
    panels.value = [{ id: 'p1', agentId: 'a1' }]
    showTerminalPanel.value = true
    // 无 DOM，getFocusZoneRect 返回 null
    document.querySelector = vi.fn(() => null)
    expect(() => api.moveFocusInDirection('right')).not.toThrow()
  })

  it('移动到该方向最贴近的区域并聚焦', () => {
    const { api, panels, showTerminalPanel, sessionPanelRefs, activatePanel, focusCurrentPanelInput } = makeHarness()
    panels.value = [{ id: 'p1', agentId: 'a1' }]
    showTerminalPanel.value = true
    const sessionRect = { left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100 }
    const terminalRect = { left: 200, top: 0, width: 100, height: 100, right: 300, bottom: 100 }
    const termEl = { getBoundingClientRect: () => terminalRect, contains: () => true }
    // 让 getActiveFocusZoneKey 返回 'terminal'（真实焦点在 terminal 内）
    const activeEl = { tagName: 'BUTTON' }
    document.querySelector = vi.fn((sel) => {
      if (sel === '.terminal-panel') return termEl
      return null
    })
    Object.defineProperty(document, 'activeElement', { value: activeEl, configurable: true })
    // session zone 的 getFocusZoneRect 依赖 sessionPanelRefs 提供根元素
    const sessionRoot = { $el: { getBoundingClientRect: () => sessionRect, contains: () => false } }
    sessionPanelRefs.set('p1', sessionRoot)
    api.moveFocusInDirection('left')
    // terminal 在右侧，session 在左侧，方向 'left' 应选中 session 并聚焦
    expect(activatePanel).toHaveBeenCalledWith('p1')
    // focusCurrentPanelInput 在 nextTick 中调用，需 flush
    return new Promise((resolve) => setTimeout(resolve, 0)).then(() => {
      expect(focusCurrentPanelInput).toHaveBeenCalledWith(true)
    })
  })
})
