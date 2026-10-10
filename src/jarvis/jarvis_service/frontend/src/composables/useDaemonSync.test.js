// useDaemonSync 单元测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useDaemonSync } from './useDaemonSync.js'

function makeHarness() {
  const auth = ref({ token: 'token-123', password: '', userInfo: null })
  const terminalName = ref('test-terminal')
  const autoInstallBrowserExt = ref(true)
  const getGateway = vi.fn(() => 'http://127.0.0.1:8000')
  const api = useDaemonSync({ auth, terminalName, autoInstallBrowserExt, getGateway })
  return { api, auth, terminalName, autoInstallBrowserExt, getGateway }
}

describe('useDaemonSync', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('暴露预期接口', () => {
    const { api } = makeHarness()
    expect(typeof api.syncTokenToDaemon).toBe('function')
    expect(typeof api.saveDaemonPortSetting).toBe('function')
    expect(typeof api.getDaemonUrl).toBe('function')
    expect(typeof api.startLocalDaemonProbe).toBe('function')
    expect(typeof api.stopLocalDaemonProbe).toBe('function')
    expect(api.daemonPort.value).toBe('17800')
    expect(api.localDaemonOnline.value).toBe(false)
  })

  it('getDaemonUrl 默认回环 17800', () => {
    const { api } = makeHarness()
    expect(api.getDaemonUrl()).toBe('http://127.0.0.1:17800')
  })

  it('getDaemonUrl 读取 localStorage 覆盖端口', () => {
    const { api } = makeHarness()
    localStorage.setItem('jarvis_daemon_url', 'http://127.0.0.1:18000')
    expect(api.getDaemonUrl()).toBe('http://127.0.0.1:18000')
  })

  it('syncTokenToDaemon 有 token 时 POST /api/auth', () => {
    const { api } = makeHarness()
    const fetchMock = vi.fn(() => Promise.resolve())
    globalThis.fetch = fetchMock
    api.syncTokenToDaemon('token-123', 'http://127.0.0.1:8000')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:17800/api/auth',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          gateway: 'http://127.0.0.1:8000',
          token: 'token-123',
          name: 'test-terminal',
          auto_install_browser_ext: true,
        }),
      })
    )
  })

  it('syncTokenToDaemon token 为空时 POST /api/logout', () => {
    const { api } = makeHarness()
    const fetchMock = vi.fn(() => Promise.resolve())
    globalThis.fetch = fetchMock
    api.syncTokenToDaemon('', 'http://127.0.0.1:8000')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:17800/api/logout',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ gateway: 'http://127.0.0.1:8000' }),
      })
    )
  })

  it('syncTokenToDaemon 无 gateway 时静默返回不请求', () => {
    const { api } = makeHarness()
    const fetchMock = vi.fn()
    globalThis.fetch = fetchMock
    api.syncTokenToDaemon('token', null)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('saveDaemonPortSetting 默认端口时清除覆盖项', () => {
    const { api } = makeHarness()
    localStorage.setItem('jarvis_daemon_url', 'http://127.0.0.1:18000')
    api.saveDaemonPortSetting('17800')
    expect(api.daemonPort.value).toBe('17800')
    expect(localStorage.getItem('jarvis_daemon_url')).toBeNull()
  })

  it('saveDaemonPortSetting 自定义端口时写入 localStorage 并重新推送', () => {
    const { api } = makeHarness()
    const fetchMock = vi.fn(() => Promise.resolve())
    globalThis.fetch = fetchMock
    api.saveDaemonPortSetting('19000')
    expect(api.daemonPort.value).toBe('19000')
    expect(localStorage.getItem('jarvis_daemon_url')).toBe('http://127.0.0.1:19000')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:19000/api/auth',
      expect.anything()
    )
  })

  it('probeLocalDaemon 探测成功时置 online', async () => {
    const { api } = makeHarness()
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    }))
    await api.probeLocalDaemon()
    expect(api.localDaemonOnline.value).toBe(true)
  })

  it('probeLocalDaemon 探测失败时置 offline', async () => {
    const { api } = makeHarness()
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('ECONNREFUSED')))
    await api.probeLocalDaemon()
    expect(api.localDaemonOnline.value).toBe(false)
  })
})
