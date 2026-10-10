// useSettings 单元测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useSettings } from './useSettings.js'

// 刷新所有微任务（async 函数多层 await 时用）
async function flushPromises() {
  for (let i = 0; i < 20; i++) {
    await Promise.resolve()
  }
}

// 构造 useSettings 依赖注入 harness
function makeHarness(overrides = {}) {
  const showToast = vi.fn()
  const showConfirm = vi.fn()
  const showAdminPanel = ref(false)
  const adminPanelRef = ref(null)
  const pushOverlayState = vi.fn()
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: 8080 }))
  const getHttpProtocol = vi.fn(() => 'http')
  const fetchWithAuth = vi.fn()
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/nodes/${nodeId}/${path}`)
  const availableNodeOptions = ref([])
  const isRestartingGateway = ref(false)
  const restartFrontendService = ref(false)

  const api = useSettings({
    showAdminPanel,
    adminPanelRef,
    pushOverlayState: () => pushOverlayState,
    getGatewayAddress,
    getHttpProtocol,
    fetchWithAuth,
    buildNodeHttpUrl,
    showToast,
    showConfirm,
    availableNodeOptions,
    isRestartingGateway: () => isRestartingGateway,
    restartFrontendService: () => restartFrontendService,
    ...overrides,
  })
  return {
    api,
    showToast,
    showConfirm,
    showAdminPanel,
    adminPanelRef,
    pushOverlayState,
    getGatewayAddress,
    getHttpProtocol,
    fetchWithAuth,
    buildNodeHttpUrl,
    availableNodeOptions,
    isRestartingGateway,
    restartFrontendService,
  }
}

describe('useSettings', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('初始状态：通知开关读 localStorage，同步/更新状态默认', () => {
    localStorage.setItem('jarvis_notify_on_exit', 'true')
    localStorage.setItem('jarvis_notify_on_input', 'false')
    const { api } = makeHarness()
    expect(api.notifyOnExit.value).toBe(true)
    expect(api.notifyOnInput.value).toBe(false)
    expect(api.syncConfigSourceNode.value).toBe('')
    expect(api.syncConfigTargetNodes.value).toEqual([])
    expect(api.syncConfigSections.value).toEqual(['llms', 'llm_groups'])
    expect(api.isSyncingConfig.value).toBe(false)
    expect(api.isUpdatingCode.value).toBe(false)
  })

  it('saveNotifySettings 写入 localStorage', () => {
    const { api } = makeHarness()
    api.notifyOnExit.value = true
    api.notifyOnInput.value = true
    api.saveNotifySettings()
    expect(localStorage.getItem('jarvis_notify_on_exit')).toBe('true')
    expect(localStorage.getItem('jarvis_notify_on_input')).toBe('true')
  })

  it('handleSyncConfig 设置源节点并弹出确认框，确认后调用 syncConfig', async () => {
    const { api, showConfirm, fetchWithAuth, availableNodeOptions } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'node-1' }, { node_id: 'master' }]
    // syncConfig 依赖：GET 源配置 + POST 目标配置
    fetchWithAuth.mockImplementation(async (url, options) => {
      if (options.method === 'GET') {
        return { ok: true, json: async () => ({ success: true, data: { config: { llms: [{ id: 'llm-1' }] } } }) }
      }
      return { ok: true, json: async () => ({ success: true, data: {} }) }
    })
    api.handleSyncConfig({ sourceNodeId: 'node-1' })
    expect(api.syncConfigSourceNode.value).toBe('node-1')
    expect(showConfirm).toHaveBeenCalledTimes(1)
    // 执行确认回调（内部调用 async syncConfig，需等待微任务完成）
    const confirmCallback = showConfirm.mock.calls[0][1]
    confirmCallback()
    await flushPromises()
    expect(api.isSyncingConfig.value).toBe(false)
    expect(fetchWithAuth).toHaveBeenCalled()
  })

  it('handleSyncConfig 未传 sourceNodeId 时回退为空字符串', () => {
    const { api, showConfirm } = makeHarness()
    api.handleSyncConfig({ sourceNodeId: '' })
    expect(api.syncConfigSourceNode.value).toBe('')
    expect(showConfirm).toHaveBeenCalledTimes(1)
  })

  it('openAdminSystemAction 打开管理面板、推历史状态并定位到系统配置', async () => {
    const { api, showAdminPanel, pushOverlayState, adminPanelRef } = makeHarness()
    const openSystemAction = vi.fn()
    adminPanelRef.value = { openSystemAction }
    api.openAdminSystemAction('restart')
    expect(showAdminPanel.value).toBe(true)
    expect(pushOverlayState).toHaveBeenCalledTimes(1)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(openSystemAction).toHaveBeenCalledWith('restart')
  })

  it('openAdminSystemAction adminPanelRef 为空时安全跳过', async () => {
    const { api, showAdminPanel } = makeHarness()
    api.openAdminSystemAction('restart')
    expect(showAdminPanel.value).toBe(true)
    await new Promise(resolve => setTimeout(resolve, 0))
  })

  it('confirmUpdateCodeToMain 弹出确认框，确认后调用 updateCodeToMain', async () => {
    const { api, showConfirm, fetchWithAuth, availableNodeOptions } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'master' }]
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true, data: { message: 'ok' } }) })
    api.confirmUpdateCodeToMain()
    expect(showConfirm).toHaveBeenCalledTimes(1)
    const confirmCallback = showConfirm.mock.calls[0][1]
    confirmCallback()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    expect(api.isUpdatingCode.value).toBe(false)
    expect(fetchWithAuth).toHaveBeenCalled()
  })

  it('confirmRestartAllNodes 弹出确认框，确认后调用 restartAllNodes', async () => {
    vi.useFakeTimers()
    const { api, showConfirm, fetchWithAuth, availableNodeOptions, isRestartingGateway } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'node-1' }, { node_id: 'master' }]
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    api.confirmRestartAllNodes()
    expect(showConfirm).toHaveBeenCalledTimes(1)
    const confirmCallback = showConfirm.mock.calls[0][1]
    confirmCallback()
    // restartAllNodes 内部有 1s 节点间隔 + 3s 复位定时器，推进定时器并 flush 微任务
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(isRestartingGateway.value).toBe(false)
    expect(fetchWithAuth).toHaveBeenCalled()
  })

  it('restartAllNodes 依次重启子节点与 master，节点间间隔 1 秒', async () => {
    vi.useFakeTimers()
    const { api, fetchWithAuth, availableNodeOptions, isRestartingGateway, showToast } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'node-1' }, { node_id: 'node-2' }, { node_id: 'master' }]
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true }) })
    const promise = api.restartAllNodes()
    // 子节点 node-1 重启（第1次调用）
    await flushPromises()
    expect(fetchWithAuth).toHaveBeenCalledTimes(1)
    // node-1 重启后等待 1s，然后 node-2 重启（第2次调用）
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchWithAuth).toHaveBeenCalledTimes(2)
    // node-2 重启后等待 1s，然后 master 重启（第3次调用，master 不等待）
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchWithAuth).toHaveBeenCalledTimes(3)
    // finally 里 3000ms 后复位 isRestartingGateway
    await vi.advanceTimersByTimeAsync(3000)
    await promise
    expect(isRestartingGateway.value).toBe(false)
    expect(showToast).toHaveBeenCalledWith('所有节点重启命令已发送完成', 'success')
  })

  it('restartAllNodes 子节点重启失败时继续并提示', async () => {
    vi.useFakeTimers()
    const { api, fetchWithAuth, availableNodeOptions, showToast } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'node-1' }, { node_id: 'master' }]
    fetchWithAuth.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    const promise = api.restartAllNodes()
    await flushPromises()
    expect(showToast).toHaveBeenCalledWith('节点 "node-1" 重启失败：HTTP 500', 'error')
    // node-1 重启后等待 1s，然后 master 重启
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchWithAuth).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(3000)
    await promise
  })

  it('syncConfig 无目标节点时提示 warning', async () => {
    const { api, availableNodeOptions, showToast } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'master' }]
    await api.syncConfig()
    expect(showToast).toHaveBeenCalledWith('没有其他节点可以同步', 'warning')
  })

  it('syncConfig 同步成功到全部目标节点', async () => {
    const { api, fetchWithAuth, availableNodeOptions, showToast } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'node-1' }, { node_id: 'node-2' }, { node_id: 'master' }]
    fetchWithAuth.mockImplementation(async (url, options) => {
      if (options.method === 'GET') {
        return { ok: true, json: async () => ({ success: true, data: { config: { llms: [{ id: 'llm-1' }], llm_groups: [] } } }) }
      }
      return { ok: true, json: async () => ({ success: true, data: {} }) }
    })
    await api.syncConfig()
    expect(showToast).toHaveBeenCalledWith('配置同步成功，已同步到 2 个节点', 'success')
    expect(api.isSyncingConfig.value).toBe(false)
  })

  it('syncConfig 源配置为空时提示 warning', async () => {
    const { api, fetchWithAuth, availableNodeOptions, showToast } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'node-1' }, { node_id: 'master' }]
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true, data: { config: {} } }) })
    await api.syncConfig()
    expect(showToast).toHaveBeenCalledWith('没有可同步的配置数据', 'warning')
  })

  it('syncConfig 防重入：isSyncingConfig 为 true 时直接返回', async () => {
    const { api, fetchWithAuth } = makeHarness()
    api.isSyncingConfig.value = true
    await api.syncConfig()
    expect(fetchWithAuth).not.toHaveBeenCalled()
  })

  it('updateCodeToMain 无在线节点时提示 warning', async () => {
    const { api, availableNodeOptions, showToast } = makeHarness()
    availableNodeOptions.value = []
    await api.updateCodeToMain()
    expect(showToast).toHaveBeenCalledWith('没有在线节点可更新', 'warning')
  })

  it('updateCodeToMain 全部节点更新成功', async () => {
    const { api, fetchWithAuth, availableNodeOptions, showToast } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'node-1' }, { node_id: 'node-2' }]
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ success: true, data: { message: 'ok' } }) })
    await api.updateCodeToMain()
    expect(showToast).toHaveBeenCalledWith('代码更新成功，已更新 2/2 个节点', 'success')
    expect(api.isUpdatingCode.value).toBe(false)
  })

  it('updateCodeToMain 部分节点失败时提示部分成功', async () => {
    const { api, fetchWithAuth, availableNodeOptions, showToast } = makeHarness()
    availableNodeOptions.value = [{ node_id: 'node-1' }, { node_id: 'node-2' }]
    fetchWithAuth
      .mockResolvedValueOnce({ ok: true, json: async () => ({ success: true, data: { message: 'ok' } }) })
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ error: { message: '失败' } }) })
    await api.updateCodeToMain()
    expect(showToast).toHaveBeenCalledWith('代码更新部分成功，成功 1/2 个节点', 'warning')
  })

  it('updateCodeToMain 防重入：isUpdatingCode 为 true 时直接返回', async () => {
    const { api, fetchWithAuth } = makeHarness()
    api.isUpdatingCode.value = true
    await api.updateCodeToMain()
    expect(fetchWithAuth).not.toHaveBeenCalled()
  })
})
