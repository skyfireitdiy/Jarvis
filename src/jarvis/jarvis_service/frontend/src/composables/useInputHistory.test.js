// useInputHistory 单元测试
import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useInputHistory } from './useInputHistory.js'

function makeHarness() {
  const inputText = ref('')
  const panelInputTexts = ref(new Map())
  const api = useInputHistory({ inputText, panelInputTexts })
  return { api, inputText, panelInputTexts }
}

describe('useInputHistory', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('暴露预期接口', () => {
    const { api } = makeHarness()
    expect(typeof api.loadInputHistory).toBe('function')
    expect(typeof api.saveInputHistory).toBe('function')
    expect(typeof api.saveToHistory).toBe('function')
    expect(typeof api.navigateHistory).toBe('function')
    expect(typeof api.onLobbyHistoryNav).toBe('function')
    expect(Array.isArray(api.inputHistory.value)).toBe(true)
    expect(api.MAX_INPUT_HISTORY_COUNT).toBe(100)
  })

  it('saveToHistory 保存输入并持久化到 localStorage', () => {
    const { api } = makeHarness()
    api.saveToHistory('第一条')
    expect(api.inputHistory.value).toEqual(['第一条'])
    expect(JSON.parse(localStorage.getItem('jarvis_input_history'))).toEqual(['第一条'])
  })

  it('saveToHistory 跳过空文本', () => {
    const { api } = makeHarness()
    api.saveToHistory('')
    api.saveToHistory('   ')
    expect(api.inputHistory.value).toEqual([])
  })

  it('saveToHistory 去重相邻重复输入', () => {
    const { api } = makeHarness()
    api.saveToHistory('重复')
    api.saveToHistory('重复')
    expect(api.inputHistory.value).toEqual(['重复'])
  })

  it('saveToHistory 超过上限时弹出最旧记录', () => {
    const { api } = makeHarness()
    for (let i = 0; i < 105; i++) {
      api.saveToHistory(`输入-${i}`)
    }
    expect(api.inputHistory.value.length).toBe(100)
    expect(api.inputHistory.value[0]).toBe('输入-104')
    expect(api.inputHistory.value[99]).toBe('输入-5')
  })

  it('navigateHistory 向上翻阅全局输入历史', () => {
    const { api, inputText } = makeHarness()
    api.saveToHistory('历史A')
    api.saveToHistory('历史B')
    inputText.value = '当前'
    api.navigateHistory('up')
    expect(inputText.value).toBe('历史B')
    api.navigateHistory('up')
    expect(inputText.value).toBe('历史A')
    // 向下回到最新，恢复临时内容
    api.navigateHistory('down')
    expect(inputText.value).toBe('历史B')
    api.navigateHistory('down')
    expect(inputText.value).toBe('当前')
  })

  it('navigateHistory 指定 agentId 操作 Panel 隔离输入', () => {
    const { api, panelInputTexts } = makeHarness()
    api.saveToHistory('Panel历史')
    panelInputTexts.value.set('agent-1', '当前')
    api.navigateHistory('up', 'agent-1')
    expect(panelInputTexts.value.get('agent-1')).toBe('Panel历史')
    api.navigateHistory('down', 'agent-1')
    expect(panelInputTexts.value.get('agent-1')).toBe('当前')
  })

  it('loadInputHistory 从 localStorage 加载并过滤非法项', () => {
    const { api } = makeHarness()
    localStorage.setItem('jarvis_input_history', JSON.stringify(['有效', '', 123, '  ']))
    api.inputHistory.value = api.loadInputHistory()
    expect(api.inputHistory.value).toEqual(['有效'])
  })

  it('loadInputHistory 对损坏数据静默回退空数组', () => {
    const { api } = makeHarness()
    localStorage.setItem('jarvis_input_history', '{{{bad json')
    expect(api.loadInputHistory()).toEqual([])
  })

  it('onLobbyHistoryNav 宠物大厅翻阅历史', () => {
    const { api } = makeHarness()
    api.saveToHistory('大厅A')
    api.saveToHistory('大厅B')
    expect(api.onLobbyHistoryNav('agent-1', 'up', '当前')).toBe('大厅B')
    expect(api.onLobbyHistoryNav('agent-1', 'up', '大厅B')).toBe('大厅A')
    expect(api.onLobbyHistoryNav('agent-1', 'down', '大厅A')).toBe('大厅B')
    expect(api.onLobbyHistoryNav('agent-1', 'down', '大厅B')).toBe('当前')
  })

  it('onLobbyHistoryNav 无更多历史时返回当前文本', () => {
    const { api } = makeHarness()
    api.saveToHistory('唯一')
    expect(api.onLobbyHistoryNav('agent-1', 'up', '当前')).toBe('唯一')
    expect(api.onLobbyHistoryNav('agent-1', 'up', '唯一')).toBe('唯一')
  })
})
