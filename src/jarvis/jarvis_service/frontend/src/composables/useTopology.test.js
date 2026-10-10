// useTopology 单元测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTopology } from './useTopology.js'

// 构造 useTopology 依赖注入 harness
function makeHarness({ extSessions = [], daemonSessions = [] } = {}) {
  const fetchBrowserExtensionSessions = vi.fn(async () => extSessions)
  const fetchDaemonSessions = vi.fn(async () => daemonSessions)
  const api = useTopology({
    fetchBrowserExtensionSessions,
    fetchDaemonSessions,
  })
  return { api, fetchBrowserExtensionSessions, fetchDaemonSessions }
}

describe('useTopology', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('初始状态：会话列表为空，浮层关闭', () => {
    const { api } = makeHarness()
    expect(api.topologyExtensionSessions.value).toEqual([])
    expect(api.topologyDaemonSessions.value).toEqual([])
    expect(api.showTopologyOverlay.value).toBe(false)
  })

  it('refreshTopologyAccessSessions 拉取扩展与 daemon 会话', async () => {
    const { api, fetchBrowserExtensionSessions, fetchDaemonSessions } = makeHarness({
      extSessions: [{ session_id: 'ext-1' }],
      daemonSessions: [{ session_id: 'daemon-1' }],
    })
    await api.refreshTopologyAccessSessions()
    expect(fetchBrowserExtensionSessions).toHaveBeenCalledTimes(1)
    expect(fetchDaemonSessions).toHaveBeenCalledTimes(1)
    expect(api.topologyExtensionSessions.value).toEqual([{ session_id: 'ext-1' }])
    expect(api.topologyDaemonSessions.value).toEqual([{ session_id: 'daemon-1' }])
  })

  it('refreshTopologyAccessSessions 非数组结果降级为空数组', async () => {
    const { api, fetchBrowserExtensionSessions, fetchDaemonSessions } = makeHarness()
    fetchBrowserExtensionSessions.mockResolvedValue(null)
    fetchDaemonSessions.mockResolvedValue(undefined)
    await api.refreshTopologyAccessSessions()
    expect(api.topologyExtensionSessions.value).toEqual([])
    expect(api.topologyDaemonSessions.value).toEqual([])
  })

  it('startTopologyAccessPolling 立即刷新并启动 5 秒轮询', async () => {
    const { api, fetchBrowserExtensionSessions } = makeHarness({ extSessions: [{ session_id: 'e1' }] })
    api.startTopologyAccessPolling()
    // 立即刷新
    await Promise.resolve()
    await Promise.resolve()
    expect(fetchBrowserExtensionSessions).toHaveBeenCalledTimes(1)
    // 5 秒后再次刷新
    vi.advanceTimersByTime(5000)
    await Promise.resolve()
    await Promise.resolve()
    expect(fetchBrowserExtensionSessions).toHaveBeenCalledTimes(2)
  })

  it('startTopologyAccessPolling 重复调用不重复启动', async () => {
    const { api, fetchBrowserExtensionSessions } = makeHarness()
    api.startTopologyAccessPolling()
    api.startTopologyAccessPolling()
    await Promise.resolve()
    await Promise.resolve()
    expect(fetchBrowserExtensionSessions).toHaveBeenCalledTimes(1)
  })

  it('stopTopologyAccessPolling 停止轮询', async () => {
    const { api, fetchBrowserExtensionSessions } = makeHarness()
    api.startTopologyAccessPolling()
    api.stopTopologyAccessPolling()
    const callsBefore = fetchBrowserExtensionSessions.mock.calls.length
    vi.advanceTimersByTime(15000)
    expect(fetchBrowserExtensionSessions.mock.calls.length).toBe(callsBefore)
  })

  it('openTopologyOverlay 打开浮层并启动轮询', async () => {
    const { api, fetchBrowserExtensionSessions } = makeHarness()
    api.openTopologyOverlay()
    expect(api.showTopologyOverlay.value).toBe(true)
    await Promise.resolve()
    await Promise.resolve()
    expect(fetchBrowserExtensionSessions).toHaveBeenCalled()
  })

  it('closeTopologyOverlay 关闭浮层并停止轮询', async () => {
    const { api, fetchBrowserExtensionSessions } = makeHarness()
    api.openTopologyOverlay()
    api.closeTopologyOverlay()
    expect(api.showTopologyOverlay.value).toBe(false)
    const callsBefore = fetchBrowserExtensionSessions.mock.calls.length
    vi.advanceTimersByTime(15000)
    expect(fetchBrowserExtensionSessions.mock.calls.length).toBe(callsBefore)
  })
})
