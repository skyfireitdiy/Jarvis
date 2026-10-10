// useAuthBridge 单元测试
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useAuthBridge } from './useAuthBridge.js'

function parseGatewayAddress(address) {
  address = String(address || '').trim()
  if (!address) return null
  try {
    const url = new URL(address)
    return {
      protocol: url.protocol.replace(':', ''),
      host: url.hostname,
      port: url.port || (url.protocol === 'https:' || url.protocol === 'wss:' ? '443' : '80'),
      path: url.pathname,
    }
  } catch {
    return null
  }
}

function makeHarness() {
  const auth = ref({ token: 'token-abc', password: '', userInfo: null })
  const terminalName = ref('my-terminal')
  const gatewayUrl = ref('ws://127.0.0.1:8000')
  const syncTokenToDaemon = vi.fn()
  const api = useAuthBridge({ auth, terminalName, gatewayUrl, parseGatewayAddress, syncTokenToDaemon })
  api.installAuthBridge()
  return { api, auth, terminalName, gatewayUrl, syncTokenToDaemon }
}

describe('useAuthBridge', () => {
  beforeEach(() => {
    localStorage.clear()
    delete window.__jarvisAuthBridge
  })

  it('installAuthBridge 挂载 window.__jarvisAuthBridge', () => {
    makeHarness()
    expect(window.__jarvisAuthBridge).toBeDefined()
    expect(typeof window.__jarvisAuthBridge.getToken).toBe('function')
    expect(typeof window.__jarvisAuthBridge.getName).toBe('function')
    expect(typeof window.__jarvisAuthBridge.getGateway).toBe('function')
    expect(typeof window.__jarvisAuthBridge.syncToDaemon).toBe('function')
  })

  it('getToken 优先返回内存 token', () => {
    const { auth } = makeHarness()
    auth.value.token = 'mem-token'
    expect(window.__jarvisAuthBridge.getToken()).toBe('mem-token')
  })

  it('getToken 内存为空时回退 localStorage', () => {
    const { auth } = makeHarness()
    auth.value.token = ''
    localStorage.setItem('jarvis_auth_token', 'saved-token')
    expect(window.__jarvisAuthBridge.getToken()).toBe('saved-token')
  })

  it('getToken 都为空时返回 null', () => {
    const { auth } = makeHarness()
    auth.value.token = ''
    expect(window.__jarvisAuthBridge.getToken()).toBeNull()
  })

  it('getName 返回终端名称', () => {
    makeHarness()
    expect(window.__jarvisAuthBridge.getName()).toBe('my-terminal')
  })

  it('getGateway 把 ws 转为 http 基地址', () => {
    makeHarness()
    expect(window.__jarvisAuthBridge.getGateway()).toBe('http://127.0.0.1:8000')
  })

  it('getGateway 把 wss 转为 https 基地址', () => {
    const { gatewayUrl } = makeHarness()
    gatewayUrl.value = 'wss://example.com:443'
    expect(window.__jarvisAuthBridge.getGateway()).toBe('https://example.com:443')
  })

  it('getGateway 对非法地址返回 null', () => {
    const { gatewayUrl } = makeHarness()
    gatewayUrl.value = 'not a url'
    expect(window.__jarvisAuthBridge.getGateway()).toBeNull()
  })

  it('syncToDaemon 调用注入的 syncTokenToDaemon', () => {
    const { syncTokenToDaemon, auth } = makeHarness()
    window.__jarvisAuthBridge.syncToDaemon()
    expect(syncTokenToDaemon).toHaveBeenCalledWith(
      auth.value.token,
      window.__jarvisAuthBridge.getGateway()
    )
  })
})
