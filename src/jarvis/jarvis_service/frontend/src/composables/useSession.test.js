// useSession 单元测试
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useSession } from './useSession.js'

function makeHarness({ agentId = null } = {}) {
  const currentAgentId = ref(agentId)
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const getCurrentAgentNodeId = vi.fn(() => '')
  const fetchWithAuth = vi.fn()
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/node/${nodeId}/${path}`)
  const loadHistoryMessages = vi.fn()
  const api = useSession({
    currentAgentId,
    getGatewayAddress,
    getCurrentAgentNodeId,
    fetchWithAuth,
    buildNodeHttpUrl,
    loadHistoryMessages
  })
  return { api, currentAgentId, getGatewayAddress, getCurrentAgentNodeId, fetchWithAuth, buildNodeHttpUrl, loadHistoryMessages }
}

describe('useSession', () => {
  beforeEach(() => {
    // 全局 alert 在 Node 环境不存在，mock 掉避免报错
    globalThis.alert = vi.fn()
  })

  it('暴露预期接口', () => {
    const { api } = makeHarness()
    expect(typeof api.showSessionDialog).toBe('object') // ref
    expect(typeof api.availableSessions).toBe('object') // ref
    expect(typeof api.restoreSession).toBe('function')
    expect(typeof api.cancelSessionDialog).toBe('function')
  })

  it('初始状态：对话框隐藏、session 列表为空', () => {
    const { api } = makeHarness()
    expect(api.showSessionDialog.value).toBe(false)
    expect(api.availableSessions.value).toEqual([])
  })

  describe('restoreSession', () => {
    it('无 sessionFile 时不发起请求', async () => {
      const { api, fetchWithAuth } = makeHarness({ agentId: 'agent-1' })
      await api.restoreSession(null)
      await api.restoreSession('')
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })

    it('无 currentAgentId 时不发起请求', async () => {
      const { api, fetchWithAuth } = makeHarness({ agentId: null })
      await api.restoreSession('session.json')
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })

    it('成功：关闭对话框并加载历史消息', async () => {
      const { api, fetchWithAuth, buildNodeHttpUrl, getGatewayAddress, loadHistoryMessages } = makeHarness({ agentId: 'agent-1' })
      fetchWithAuth.mockResolvedValue({
        json: async () => ({ success: true })
      })
      api.showSessionDialog.value = true
      await api.restoreSession('session.json')
      expect(api.showSessionDialog.value).toBe(false)
      expect(loadHistoryMessages).toHaveBeenCalledWith(false)
      expect(getGatewayAddress).toHaveBeenCalled()
      expect(buildNodeHttpUrl).toHaveBeenCalledWith('127.0.0.1', '8000', 'master', 'agents/agent-1/sessions')
      expect(fetchWithAuth).toHaveBeenCalledTimes(1)
      // POST 请求体包含 session_file 与 node_id
      const [, options] = fetchWithAuth.mock.calls[0]
      expect(options.method).toBe('POST')
      expect(JSON.parse(options.body)).toEqual({ session_file: 'session.json', node_id: 'master' })
    })

    it('有 node_id 时优先使用当前 Agent 节点', async () => {
      const { api, fetchWithAuth, buildNodeHttpUrl, getCurrentAgentNodeId } = makeHarness({ agentId: 'agent-1' })
      getCurrentAgentNodeId.mockReturnValue('node-9')
      fetchWithAuth.mockResolvedValue({
        json: async () => ({ success: true })
      })
      await api.restoreSession('session.json')
      expect(buildNodeHttpUrl).toHaveBeenCalledWith('127.0.0.1', '8000', 'node-9', 'agents/agent-1/sessions')
    })

    it('后端返回失败：弹出错误提示且不关闭对话框', async () => {
      const { api, fetchWithAuth, loadHistoryMessages } = makeHarness({ agentId: 'agent-1' })
      fetchWithAuth.mockResolvedValue({
        json: async () => ({ success: false, error: '文件不存在' })
      })
      api.showSessionDialog.value = true
      await api.restoreSession('session.json')
      expect(api.showSessionDialog.value).toBe(true)
      expect(globalThis.alert).toHaveBeenCalledWith('恢复会话失败: 文件不存在')
      expect(loadHistoryMessages).not.toHaveBeenCalled()
    })

    it('请求异常：弹出带错误详情的提示', async () => {
      const { api, fetchWithAuth } = makeHarness({ agentId: 'agent-1' })
      fetchWithAuth.mockRejectedValue(new Error('network down'))
      await api.restoreSession('session.json')
      expect(globalThis.alert).toHaveBeenCalledWith('恢复会话失败: network down')
    })
  })

  describe('cancelSessionDialog', () => {
    it('关闭对话框并加载历史消息（不恢复 session）', () => {
      const { api, loadHistoryMessages } = makeHarness()
      api.showSessionDialog.value = true
      api.cancelSessionDialog()
      expect(api.showSessionDialog.value).toBe(false)
      expect(loadHistoryMessages).toHaveBeenCalledWith(false)
    })
  })
})
