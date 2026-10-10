// useDiff 单元测试
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useDiff } from './useDiff.js'

function makeHarness({ windowWidthValue = 1200 } = {}) {
  const windowWidth = ref(windowWidthValue)
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const getCurrentAgentNodeId = vi.fn(() => '')
  const fetchWithAuth = vi.fn()
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/node/${nodeId}/${path}`)
  const api = useDiff({
    windowWidth,
    getGatewayAddress,
    getCurrentAgentNodeId,
    fetchWithAuth,
    buildNodeHttpUrl
  })
  return { api, windowWidth, getGatewayAddress, getCurrentAgentNodeId, fetchWithAuth, buildNodeHttpUrl }
}

// 构造一个合法的 diff 文件对象（与后端返回结构一致）
function makeFile(filePath, additions, deletions, rows) {
  return { file_path: filePath, additions, deletions, rows }
}

describe('useDiff', () => {
  it('暴露预期接口', () => {
    const { api } = makeHarness()
    expect(typeof api.showDiffModal).toBe('object') // ref
    expect(typeof api.diffFiles).toBe('object') // ref
    expect(typeof api.diffActiveIndex).toBe('object') // ref
    expect(typeof api.diffLoading).toBe('object') // ref
    expect(typeof api.diffError).toBe('object') // ref
    expect(typeof api.diffMobileShowDetail).toBe('object') // ref
    expect(typeof api.diffActiveHtml).toBe('object') // computed ref
    expect(typeof api.selectDiffFile).toBe('function')
    expect(typeof api.viewDiff).toBe('function')
  })

  it('初始状态：弹窗隐藏、无文件、无错误、未加载', () => {
    const { api } = makeHarness()
    expect(api.showDiffModal.value).toBe(false)
    expect(api.diffFiles.value).toEqual([])
    expect(api.diffActiveIndex.value).toBe(0)
    expect(api.diffLoading.value).toBe(false)
    expect(api.diffError.value).toBe('')
    expect(api.diffMobileShowDetail.value).toBe(false)
    expect(api.diffActiveHtml.value).toBe('')
  })

  describe('diffActiveHtml', () => {
    it('无选中文件时返回空串', () => {
      const { api } = makeHarness()
      expect(api.diffActiveHtml.value).toBe('')
    })
    it('有选中文件时返回渲染结果（非空 HTML）', () => {
      const { api } = makeHarness()
      const file = makeFile('a.py', 1, 0, [{ type: 'insert', content: 'x = 1' }])
      api.diffFiles.value = [file]
      api.diffActiveIndex.value = 0
      expect(typeof api.diffActiveHtml.value).toBe('string')
      expect(api.diffActiveHtml.value.length).toBeGreaterThan(0)
    })
    it('随选中文件索引变化而更新', () => {
      const { api } = makeHarness()
      const fileA = makeFile('a.py', 1, 0, [{ type: 'insert', content: 'a' }])
      const fileB = makeFile('b.py', 0, 1, [{ type: 'delete', content: 'b' }])
      api.diffFiles.value = [fileA, fileB]
      api.diffActiveIndex.value = 0
      const htmlA = api.diffActiveHtml.value
      api.diffActiveIndex.value = 1
      const htmlB = api.diffActiveHtml.value
      expect(htmlA).not.toBe(htmlB)
    })
  })

  describe('selectDiffFile', () => {
    it('桌面端：切换索引但不进入移动端详情', () => {
      const { api } = makeHarness({ windowWidthValue: 1200 })
      api.selectDiffFile(2)
      expect(api.diffActiveIndex.value).toBe(2)
      expect(api.diffMobileShowDetail.value).toBe(false)
    })
    it('移动端（≤768）：切换索引并进入全屏详情', () => {
      const { api } = makeHarness({ windowWidthValue: 768 })
      api.selectDiffFile(1)
      expect(api.diffActiveIndex.value).toBe(1)
      expect(api.diffMobileShowDetail.value).toBe(true)
    })
    it('移动端边界：768 视为窄屏', () => {
      const { api } = makeHarness({ windowWidthValue: 768 })
      api.selectDiffFile(0)
      expect(api.diffMobileShowDetail.value).toBe(true)
    })
  })

  describe('viewDiff', () => {
    it('无效 agent（无 agent_id）直接返回，不发起请求', async () => {
      const { api, fetchWithAuth } = makeHarness()
      await api.viewDiff(null)
      await api.viewDiff({})
      expect(fetchWithAuth).not.toHaveBeenCalled()
      expect(api.showDiffModal.value).toBe(false)
    })

    it('成功：拉取结构化 diff 并填充文件列表', async () => {
      const { api, fetchWithAuth, buildNodeHttpUrl, getGatewayAddress } = makeHarness()
      const file = makeFile('src/a.js', 3, 1, [
        { type: 'equal', content: 'line1' },
        { type: 'insert', content: 'line2' },
        { type: 'delete', content: 'line3' }
      ])
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ files: [file] })
      })
      await api.viewDiff({ agent_id: 'agent-1' })
      expect(api.showDiffModal.value).toBe(true)
      expect(api.diffLoading.value).toBe(false)
      expect(api.diffError.value).toBe('')
      expect(api.diffFiles.value).toEqual([file])
      expect(api.diffActiveIndex.value).toBe(0)
      expect(api.diffMobileShowDetail.value).toBe(false)
      // 构建了正确的节点 URL
      expect(getGatewayAddress).toHaveBeenCalled()
      expect(buildNodeHttpUrl).toHaveBeenCalledWith('127.0.0.1', '8000', 'master', 'agent/agent-1/diff')
      expect(fetchWithAuth).toHaveBeenCalledTimes(1)
    })

    it('成功：agent 携带 node_id 时优先使用该节点', async () => {
      const { api, fetchWithAuth, buildNodeHttpUrl } = makeHarness()
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ files: [] })
      })
      await api.viewDiff({ agent_id: 'agent-1', node_id: 'node-9' })
      expect(buildNodeHttpUrl).toHaveBeenCalledWith('127.0.0.1', '8000', 'node-9', 'agent/agent-1/diff')
    })

    it('成功：agent 无 node_id 时回退到当前 Agent 节点', async () => {
      const { api, fetchWithAuth, buildNodeHttpUrl, getCurrentAgentNodeId } = makeHarness()
      getCurrentAgentNodeId.mockReturnValue('cur-node')
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ files: [] })
      })
      await api.viewDiff({ agent_id: 'agent-1' })
      expect(buildNodeHttpUrl).toHaveBeenCalledWith('127.0.0.1', '8000', 'cur-node', 'agent/agent-1/diff')
    })

    it('成功：后端返回空文件列表时保持空数组', async () => {
      const { api, fetchWithAuth } = makeHarness()
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ files: [] })
      })
      await api.viewDiff({ agent_id: 'agent-1' })
      expect(api.diffFiles.value).toEqual([])
      expect(api.diffError.value).toBe('')
    })

    it('HTTP 非 2xx：设置错误信息', async () => {
      const { api, fetchWithAuth } = makeHarness()
      fetchWithAuth.mockResolvedValue({ ok: false, status: 500 })
      await api.viewDiff({ agent_id: 'agent-1' })
      expect(api.diffError.value).toBe('获取 diff 失败')
      expect(api.diffFiles.value).toEqual([])
      expect(api.diffLoading.value).toBe(false)
    })

    it('请求异常：设置带错误详情的错误信息', async () => {
      const { api, fetchWithAuth } = makeHarness()
      fetchWithAuth.mockRejectedValue(new Error('network down'))
      await api.viewDiff({ agent_id: 'agent-1' })
      expect(api.diffError.value).toContain('获取 diff 失败')
      expect(api.diffError.value).toContain('network down')
      expect(api.diffLoading.value).toBe(false)
    })

    it('过滤无效文件数据（缺 rows / 非法 row type）', async () => {
      const { api, fetchWithAuth } = makeHarness()
      const validFile = makeFile('ok.py', 1, 0, [{ type: 'insert', content: 'x' }])
      const badRows = makeFile('bad.py', 1, 0, [{ type: 'weird' }])
      const noRows = makeFile('norows.py', 1, 0, null)
      const notObject = 'not-an-object'
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ files: [validFile, badRows, noRows, notObject] })
      })
      await api.viewDiff({ agent_id: 'agent-1' })
      expect(api.diffFiles.value).toEqual([validFile])
    })
  })
})
