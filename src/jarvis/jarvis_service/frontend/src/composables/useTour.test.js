// useTour 单元测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTour } from './useTour.js'

// 构造 useTour 依赖注入 harness（getter 形式注入，与 App.vue 一致）
function makeHarness() {
  const showToast = vi.fn()
  const openWorkspaceAgentList = vi.fn()
  const api = useTour({
    showToast: () => showToast,
    openWorkspaceAgentList: () => openWorkspaceAgentList,
  })
  return { api, showToast, openWorkspaceAgentList }
}

// 内存版 localStorage mock
function makeLocalStorageMock() {
  const store = new Map()
  return {
    getItem: vi.fn((key) => (store.has(key) ? store.get(key) : null)),
    setItem: vi.fn((key, value) => store.set(key, String(value))),
    removeItem: vi.fn((key) => store.delete(key)),
    key: vi.fn((i) => Array.from(store.keys())[i] ?? null),
    get length() {
      return store.size
    },
    _store: store,
  }
}

describe('useTour', () => {
  let ls
  beforeEach(() => {
    ls = makeLocalStorageMock()
    vi.stubGlobal('localStorage', ls)
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('初始状态：无进行中的引导，步骤为空', () => {
    const { api } = makeHarness()
    expect(api.activeTourId.value).toBe(null)
    expect(api.showOnboarding.value).toBe(false)
    expect(api.activeTourSteps.value).toEqual([])
  })

  it('startOnboarding 打开指定场景引导（不写标记）', () => {
    const { api } = makeHarness()
    api.startOnboarding('lobby')
    expect(api.activeTourId.value).toBe('lobby')
    expect(api.showOnboarding.value).toBe(true)
    expect(api.activeTourSteps.value.length).toBeGreaterThan(0)
    // 未调用 markTourSeen，标记不应被写入
    expect(ls.getItem('jarvis_onboarding_lobby_v1')).toBe(null)
  })

  it('startOnboarding 默认打开 welcome 场景', () => {
    const { api } = makeHarness()
    api.startOnboarding()
    expect(api.activeTourId.value).toBe('welcome')
    expect(api.activeTourSteps.value).toHaveLength(6)
  })

  it('startOnboarding 的 sidebar 场景会调用 openWorkspaceAgentList', () => {
    const { api, openWorkspaceAgentList } = makeHarness()
    api.startOnboarding('sidebar')
    expect(openWorkspaceAgentList).toHaveBeenCalledTimes(1)
  })

  it('startOnboarding 的非 sidebar 场景不调用 openWorkspaceAgentList', () => {
    const { api, openWorkspaceAgentList } = makeHarness()
    api.startOnboarding('welcome')
    expect(openWorkspaceAgentList).not.toHaveBeenCalled()
  })

  it('finishTour 记录已看并收起，welcome 场景提示 toast', () => {
    const { api, showToast } = makeHarness()
    api.startOnboarding('welcome')
    api.finishTour()
    expect(api.activeTourId.value).toBe(null)
    expect(api.showOnboarding.value).toBe(false)
    expect(ls.getItem('jarvis_onboarding_welcome_v1')).toBe('1')
    expect(showToast).toHaveBeenCalledWith('引导完成，开始使用 Jarvis 吧', 'success')
  })

  it('finishTour 非 welcome 场景不提示 toast', () => {
    const { api, showToast } = makeHarness()
    api.startOnboarding('agent')
    api.finishTour()
    expect(showToast).not.toHaveBeenCalled()
  })

  it('showOnboarding 置 false 会触发 finishTour（v-model 关闭）', () => {
    const { api } = makeHarness()
    api.startOnboarding('panel')
    api.showOnboarding.value = false
    expect(api.activeTourId.value).toBe(null)
    expect(ls.getItem('jarvis_onboarding_panel_v1')).toBe('1')
  })

  it('maybeStartTour 延迟后触发未看过的场景', () => {
    const { api } = makeHarness()
    api.maybeStartTour('lobby')
    expect(api.activeTourId.value).toBe(null) // 延迟未到
    vi.advanceTimersByTime(800)
    expect(api.activeTourId.value).toBe('lobby')
  })

  it('maybeStartTour 跳过已看过的场景', () => {
    const { api } = makeHarness()
    ls.setItem('jarvis_onboarding_lobby_v1', '1')
    api.maybeStartTour('lobby')
    vi.advanceTimersByTime(800)
    expect(api.activeTourId.value).toBe(null)
  })

  it('maybeStartTour 跳过进行中的引导', () => {
    const { api } = makeHarness()
    api.startOnboarding('welcome')
    api.maybeStartTour('lobby')
    vi.advanceTimersByTime(800)
    expect(api.activeTourId.value).toBe('welcome')
  })

  it('hasSeenTour 识别旧版单一引导标记（welcome）', () => {
    const { api } = makeHarness()
    ls.setItem('jarvis_onboarding_done_v1', '1')
    api.maybeStartTour('welcome')
    vi.advanceTimersByTime(800)
    expect(api.activeTourId.value).toBe(null)
  })

  it('resetOnboardingMarks 清除全部引导标记', () => {
    const { api } = makeHarness()
    ls.setItem('jarvis_onboarding_welcome_v1', '1')
    ls.setItem('jarvis_onboarding_lobby_v1', '1')
    ls.setItem('jarvis_onboarding_done_v1', '1')
    ls.setItem('unrelated_key', '1')
    api.resetOnboardingMarks()
    expect(ls.getItem('jarvis_onboarding_welcome_v1')).toBe(null)
    expect(ls.getItem('jarvis_onboarding_lobby_v1')).toBe(null)
    expect(ls.getItem('jarvis_onboarding_done_v1')).toBe(null)
    // 无关 key 不受影响
    expect(ls.getItem('unrelated_key')).toBe('1')
  })

  it('clearOnboardingTimer 取消未触发的引导', () => {
    const { api } = makeHarness()
    api.maybeStartTour('panel')
    api.clearOnboardingTimer()
    vi.advanceTimersByTime(800)
    expect(api.activeTourId.value).toBe(null)
  })

  it('各场景步骤常量可通过 getTourSteps 获取', () => {
    const { api } = makeHarness()
    expect(api.activeTourSteps.value).toEqual([])
    // 通过 startOnboarding 触发各场景，检查步骤非空
    api.startOnboarding('welcome')
    expect(api.activeTourSteps.value.length).toBeGreaterThan(0)
    api.startOnboarding('lobby')
    expect(api.activeTourSteps.value.length).toBeGreaterThan(0)
    api.startOnboarding('agent')
    expect(api.activeTourSteps.value.length).toBeGreaterThan(0)
    api.startOnboarding('panel')
    expect(api.activeTourSteps.value.length).toBeGreaterThan(0)
    api.startOnboarding('sidebar')
    expect(api.activeTourSteps.value.length).toBeGreaterThan(0)
  })
})
