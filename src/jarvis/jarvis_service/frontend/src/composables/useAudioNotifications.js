// 音频提示 / 自动朗读 / 系统通知 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（原 20747-20895 行），保持行为完全一致：
// - 提示音：playNotificationSound / playChatNotificationSound（Web Audio API，自包含）
// - 自动朗读：基于浏览器内置 SpeechSynthesis，复用 SessionPanel 组件的 speakMessage/speakText
// - 系统通知：Notification API（仅弹窗，不播放提示音）
//
// 依赖注入：
// - sessionPanelRefs：普通 Map（panelId -> SessionPanel 组件实例）
// - allOutputs：ref(Map)（agent_id -> outputs array）
// - panelInputTips：ref(Map)（agentId -> 输入提示字符串）
// - panels：ref(数组)（[{ id, agentId }]）
// - isAutoReadEnabled：函数（agentId -> boolean）
export function useAudioNotifications({
  sessionPanelRefs,
  allOutputs,
  panelInputTips,
  panels,
  isAutoReadEnabled,
}) {
  // 播放单次提示音
  function playSingleBeep(audioContext, startTime) {
    const oscillator = audioContext.createOscillator()
    const gainNode = audioContext.createGain()
    oscillator.connect(gainNode)
    gainNode.connect(audioContext.destination)
    oscillator.frequency.value = 800
    oscillator.type = 'sine'
    gainNode.gain.setValueAtTime(0.3, startTime)
    gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + 0.2)
    oscillator.start(startTime)
    oscillator.stop(startTime + 0.2)
  }

  // 播放聊天室新消息提示音（双音阶，区别于普通提示音）
  function playChatNotificationSound() {
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)()
      const now = audioContext.currentTime
      // 播放两个不同频率的音符，形成"叮咚"效果
      playChatSingleTone(audioContext, now, 880, 'triangle', 0.25)
      playChatSingleTone(audioContext, now + 0.18, 1320, 'triangle', 0.3)
    } catch {
      // 浏览器不支持 Web Audio 时静默忽略
    }
  }

  // 播放单次聊天提示音
  function playChatSingleTone(audioContext, startTime, frequency, type, duration) {
    const oscillator = audioContext.createOscillator()
    const gainNode = audioContext.createGain()
    oscillator.connect(gainNode)
    gainNode.connect(audioContext.destination)
    oscillator.frequency.value = frequency
    oscillator.type = type
    gainNode.gain.setValueAtTime(0.25, startTime)
    gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duration)
    oscillator.start(startTime)
    oscillator.stop(startTime + duration)
  }

  // 播放提示音（连续三次），返回在最后一声结束后 resolve 的 Promise
  function playNotificationSound() {
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)()
      const now = audioContext.currentTime
      // 连续播放三次提示音，每次间隔0.25秒
      playSingleBeep(audioContext, now)
      playSingleBeep(audioContext, now + 0.25)
      playSingleBeep(audioContext, now + 0.5)
      // 最后一声在 now + 0.5 开始、持续 0.2s，留出少量余量
      return new Promise(resolve => setTimeout(resolve, 750))
    } catch {
      // 浏览器不支持 Web Audio 时静默忽略，返回已 resolve 的 Promise
      return Promise.resolve()
    }
  }

  // 收到输入请求时播放提示音（不受自动朗读开关限制，任何情况下都播放）
  function notifyInputRequest() {
    playNotificationSound()
  }

  // ---- 自动朗读（浏览器内置 SpeechSynthesis） ----
  const autoReadSupported = typeof window !== 'undefined' && 'speechSynthesis' in window

  // 停止自动朗读（复用 SessionPanel 的停止逻辑，保证图标状态同步）
  function stopAutoRead() {
    if (!autoReadSupported) return
    for (const sp of sessionPanelRefs.values()) {
      sp?.stopSpeak?.()
    }
  }

  // 从渲染后的 HTML 提取纯文本，避免把 Markdown 标记念出来
  function extractAutoReadText(item) {
    if (!item) return ''
    if (item.html) {
      const tmp = document.createElement('div')
      tmp.innerHTML = item.html
      return (tmp.textContent || '').replace(/\s+/g, ' ').trim()
    }
    return String(item.text || '').trim()
  }

  // 获取自动朗读目标：多行输入取最后一条有文本的消息，单行/确认取输入提示
  function getAutoReadTarget(agentId, executionStatus) {
    if (executionStatus === 'waiting_multi') {
      const messages = allOutputs.value.get(agentId) || []
      for (let i = messages.length - 1; i >= 0; i--) {
        if (extractAutoReadText(messages[i])) return { message: messages[i] }
      }
    }
    const tip = panelInputTips.value.get(agentId) || ''
    return { text: tip || '等待输入' }
  }

  // 进入等待输入状态时触发对应消息的朗读按钮逻辑（提示音由 notifyInputRequest 独立播放）
  async function handleAutoRead(agentId, executionStatus) {
    if (!isAutoReadEnabled(agentId)) return
    const target = getAutoReadTarget(agentId, executionStatus)
    const panel = panels.value.find(p => p.agentId === agentId)
    const sp = panel ? sessionPanelRefs.get(panel.id) : null
    if (target.message && sp?.speakMessage) {
      // 复用消息列表的朗读逻辑，图标状态自动同步
      sp.speakMessage(target.message)
    } else if (sp?.speakText) {
      sp.speakText(target.text)
    }
  }

  // 通知权限状态
  let notificationPermissionRequested = false

  // 发送系统通知（仅弹窗，不播放提示音）
  function sendSystemNotification(message) {
    // 检查浏览器是否支持 Notification API
    if (!('Notification' in window)) {
      return
    }
    // 如果已经获得权限，直接发送通知
    if (Notification.permission === 'granted') {
      new Notification('Jarvis', {
        body: message,
        icon: '/icons/jarvis-pet.svg'
      })
    }
    // 如果还没有拒绝且尚未请求过权限，请求权限
    else if (Notification.permission !== 'denied' && !notificationPermissionRequested) {
      notificationPermissionRequested = true
      Notification.requestPermission().then(permission => {
        if (permission === 'granted') {
          new Notification('Jarvis', {
            body: message,
            icon: '/icons/jarvis-pet.svg'
          })
        }
      })
    }
  }

  return {
    autoReadSupported,
    notifyInputRequest,
    playChatNotificationSound,
    stopAutoRead,
    handleAutoRead,
    sendSystemNotification,
  }
}
