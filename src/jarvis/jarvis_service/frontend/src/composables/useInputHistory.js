import { ref } from 'vue'

// 历史输入管理 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出，保持行为完全一致：
// - inputHistory：历史输入数组（localStorage 持久化，key 为 jarvis_input_history）
// - 上下键翻阅历史（Panel 与宠物大厅两套入口，共享同一份历史数组）
// - saveToHistory：发送输入时记录历史，去重 + 限量 + 重置翻阅游标
//
// 依赖注入：
// - inputText：ref(string)（全局输入框文本）
// - panelInputTexts：ref(Map)（agentId -> Panel 输入文本）
export function useInputHistory({ inputText, panelInputTexts }) {
  const INPUT_HISTORY_STORAGE_KEY = 'jarvis_input_history'
  const MAX_INPUT_HISTORY_COUNT = 100

  const inputHistory = ref([]) // 历史输入记录数组
  const historyIndex = ref(-1) // 当前浏览的历史记录索引（-1 表示未浏览历史）
  const currentTempInput = ref('') // 用户正在编辑的临时内容
  const panelTempInputs = ref(new Map()) // 每个 Panel 的临时编辑内容 (key: agentId, value: 内容)

  // 宠物大厅：每个 Agent 独立的历史翻阅游标与暂存内容
  const lobbyHistoryIndex = new Map() // agentId -> index（-1 表示回到最新）
  const lobbyHistoryTemp = new Map() // agentId -> 翻阅前暂存的内容

  function loadInputHistory() {
    const savedValue = localStorage.getItem(INPUT_HISTORY_STORAGE_KEY)
    if (!savedValue) {
      return []
    }

    try {
      const parsedValue = JSON.parse(savedValue)
      if (!Array.isArray(parsedValue)) {
        return []
      }

      return parsedValue
        .filter(historyItem => typeof historyItem === 'string' && historyItem.trim())
        .slice(0, MAX_INPUT_HISTORY_COUNT)
    } catch {
      return []
    }
  }

  function saveInputHistory() {
    localStorage.setItem(
      INPUT_HISTORY_STORAGE_KEY,
      JSON.stringify(inputHistory.value.slice(0, MAX_INPUT_HISTORY_COUNT))
    )
  }

  // 保存输入到历史记录
  function saveToHistory(text) {
    if (!text || !text.trim()) return

    // 避免保存重复的历史记录
    const lastHistory = inputHistory.value[0]
    if (lastHistory && lastHistory.trim() === text.trim()) {
      return
    }

    // 将新输入添加到历史记录开头
    inputHistory.value.unshift(text)

    // 限制历史记录数量
    if (inputHistory.value.length > MAX_INPUT_HISTORY_COUNT) {
      inputHistory.value.pop()
    }

    saveInputHistory()

    // 重置历史浏览状态
    historyIndex.value = -1
    currentTempInput.value = ''
  }

  // 翻阅历史记录
  function navigateHistory(direction, agentId = null) {
    // direction: 'up' 或 'down'
    // agentId: 指定 Panel 的 agentId，传入时操作 Panel 隔离的输入

    const isPanel = agentId !== null
    const getInput = () => isPanel ? (panelInputTexts.value.get(agentId) || '') : inputText.value
    const setInput = (val) => {
      if (isPanel) {
        panelInputTexts.value.set(agentId, val)
      } else {
        inputText.value = val
      }
    }
    const getTemp = () => isPanel ? (panelTempInputs.value.get(agentId) || '') : currentTempInput.value
    const setTemp = (val) => {
      if (isPanel) {
        panelTempInputs.value.set(agentId, val)
      } else {
        currentTempInput.value = val
      }
    }

    if (direction === 'up') {
      // 向上翻阅：加载更早的历史记录
      if (historyIndex.value < inputHistory.value.length - 1) {
        // 第一次翻阅时，保存当前正在编辑的内容
        if (historyIndex.value === -1) {
          setTemp(getInput())
        }
        historyIndex.value++
        setInput(inputHistory.value[historyIndex.value])
      }
    } else if (direction === 'down') {
      // 向下翻阅：加载更新的历史记录
      if (historyIndex.value > -1) {
        historyIndex.value--
        if (historyIndex.value === -1) {
          // 回到最新状态，恢复临时编辑的内容
          setInput(getTemp())
        } else {
          setInput(inputHistory.value[historyIndex.value])
        }
      }
    }
  }

  // 宠物大厅：输入历史翻阅（与 Panel 行为一致，返回翻阅后的文本）
  function onLobbyHistoryNav(agentId, direction, currentText = '') {
    const current = currentText || ''
    let index = lobbyHistoryIndex.has(agentId) ? lobbyHistoryIndex.get(agentId) : -1
    if (direction === 'up') {
      if (index < inputHistory.value.length - 1) {
        if (index === -1) lobbyHistoryTemp.set(agentId, current)
        index++
        lobbyHistoryIndex.set(agentId, index)
        return inputHistory.value[index]
      }
      return current
    } else {
      if (index > -1) {
        index--
        lobbyHistoryIndex.set(agentId, index)
        if (index === -1) return lobbyHistoryTemp.get(agentId) || ''
        return inputHistory.value[index]
      }
      return current
    }
  }

  return {
    inputHistory,
    historyIndex,
    currentTempInput,
    panelTempInputs,
    lobbyHistoryIndex,
    lobbyHistoryTemp,
    MAX_INPUT_HISTORY_COUNT,
    loadInputHistory,
    saveInputHistory,
    saveToHistory,
    navigateHistory,
    onLobbyHistoryNav,
  }
}
