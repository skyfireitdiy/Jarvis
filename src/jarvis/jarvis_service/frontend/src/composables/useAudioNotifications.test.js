// 临时验证 useAudioNotifications 行为（验证后删除）
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useAudioNotifications } from './useAudioNotifications.js'

function makeHarness() {
  const sessionPanelRefs = new Map()
  const allOutputs = ref(new Map())
  const panelInputTips = ref(new Map())
  const panels = ref([])
  const panelAutoReads = ref(new Map())
  const isAutoReadEnabled = (agentId) => panelAutoReads.value.get(agentId) === true
  const api = useAudioNotifications({ sessionPanelRefs, allOutputs, panelInputTips, panels, isAutoReadEnabled })
  return { api, sessionPanelRefs, allOutputs, panelInputTips, panels, panelAutoReads }
}

describe('useAudioNotifications', () => {
  it('暴露预期接口', () => {
    const { api } = makeHarness()
    expect(typeof api.notifyInputRequest).toBe('function')
    expect(typeof api.playChatNotificationSound).toBe('function')
    expect(typeof api.stopAutoRead).toBe('function')
    expect(typeof api.handleAutoRead).toBe('function')
    expect(typeof api.sendSystemNotification).toBe('function')
    expect(typeof api.autoReadSupported).toBe('boolean')
  })

  it('handleAutoRead 在未开启自动朗读时直接返回', async () => {
    const { api } = makeHarness()
    const result = await api.handleAutoRead('agent-1', 'waiting_single')
    expect(result).toBeUndefined()
  })

  it('handleAutoRead 开启后调用 SessionPanel 的 speakText', async () => {
    const { api, panelAutoReads, panelInputTips, panels, sessionPanelRefs } = makeHarness()
    panelAutoReads.value.set('agent-1', true)
    panelInputTips.value.set('agent-1', '你好')
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }]
    const speakText = vi.fn()
    const sp = { speakText, speakMessage: vi.fn() }
    sessionPanelRefs.set('panel-1', sp)
    await api.handleAutoRead('agent-1', 'waiting_single')
    expect(speakText).toHaveBeenCalledWith('你好')
  })

  it('handleAutoRead 多行输入取最后一条有文本的消息', async () => {
    const { api, panelAutoReads, allOutputs, panels, sessionPanelRefs } = makeHarness()
    panelAutoReads.value.set('agent-1', true)
    allOutputs.value.set('agent-1', [
      { html: '<p>第一条</p>' },
      { html: '<p>第二条</p>' },
    ])
    panels.value = [{ id: 'panel-1', agentId: 'agent-1' }]
    const speakMessage = vi.fn()
    sessionPanelRefs.set('panel-1', { speakMessage, speakText: vi.fn() })
    await api.handleAutoRead('agent-1', 'waiting_multi')
    expect(speakMessage).toHaveBeenCalled()
    // 应取最后一条有文本的消息
    expect(speakMessage.mock.calls[0][0]).toEqual({ html: '<p>第二条</p>' })
  })

  it('stopAutoRead 遍历所有 SessionPanel 调用 stopSpeak', () => {
    // jsdom 无 speechSynthesis，需 mock 让 autoReadSupported 为 true
    globalThis.speechSynthesis = {}
    const { api, sessionPanelRefs } = makeHarness()
    const sp1 = { stopSpeak: vi.fn() }
    const sp2 = { stopSpeak: vi.fn() }
    sessionPanelRefs.set('p1', sp1)
    sessionPanelRefs.set('p2', sp2)
    api.stopAutoRead()
    expect(sp1.stopSpeak).toHaveBeenCalled()
    expect(sp2.stopSpeak).toHaveBeenCalled()
  })

  it('sendSystemNotification 在无 Notification API 时静默返回', () => {
    const { api } = makeHarness()
    expect(() => api.sendSystemNotification('test')).not.toThrow()
  })
})
