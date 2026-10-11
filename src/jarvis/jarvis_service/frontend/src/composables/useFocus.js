// 区域焦点导航（几何方向键移动 + 焦点区域推断）组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 阶段3），保持行为完全一致。
// 覆盖焦点管理子域：
// - focusActiveTerminal：聚焦集成终端内的活动终端
// - focusZoneContainer / isFocusableTarget / focusFirstIn：区域容器兜底聚焦与首个可聚焦元素查找
// - getFocusZones：构建可聚焦区域列表（Session Panel → 终端 → 编辑器 → 聊天室）
// - getFocusedZoneKey / getActiveFocusZoneKey：根据真实 DOM 焦点推断当前区域 key
// - getFocusZoneRect / scoreFocusZoneByDirection / moveFocusInDirection：几何方向键导航
//
// 依赖注入（getter 注入）：所有依赖均定义在 useFocus 调用点（useTopology 之后、
// useWorkspacePane 之前）之后，故统一以 getter 函数传入，内部通过 xxx() 二次求值避免 TDZ。
// ref 型依赖（panels/showTerminalPanel/showWorkspacePanel/showChatPanel/activeWindow/
// terminalSessions/activeTerminalId）使用处需 xxx().value 二次求值；
// 普通 Map（sessionPanelRefs）与函数（focusWindow/getActiveWorkspaceView/activatePanel/
// isAnyModalOpen/focusCurrentPanelInput/getCurrentPanel）直接 xxx() 求值即可。
import { nextTick } from 'vue'
export function useFocus({
  panels,
  sessionPanelRefs,
  showTerminalPanel,
  showWorkspacePanel,
  showChatPanel,
  activeWindow,
  focusWindow,
  getActiveWorkspaceView,
  activatePanel,
  isAnyModalOpen,
  focusCurrentPanelInput,
  getCurrentPanel,
  terminalSessions,
  activeTerminalId,
}) {
  // 聚焦集成终端内的活动终端
  function focusActiveTerminal() {
    const session = terminalSessions().value.find(s => s.terminal_id === activeTerminalId().value)
      || terminalSessions().value[0]
    if (session?.terminal) {
      session.terminal.focus()
      return true
    }
    return false
  }

  // 区域容器兜底聚焦：当区域内部没有可聚焦元素时（如空终端/空编辑器），
  // 让焦点落到区域容器上，保证方向键导航有落地反馈、且后续导航起点正确
  function focusZoneContainer(el) {
    if (!el) return
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1')
    if (typeof el.focus === 'function') el.focus({ preventScroll: true })
  }

  // 是否是真正可聚焦的元素（排除 disabled / 不可见）
  function isFocusableTarget(el) {
    if (!el || typeof el.focus !== 'function') return false
    if (el.disabled) return false
    if (el.hasAttribute && el.hasAttribute('disabled')) return false
    // tabindex="-1" 的控件（如区域分割/关闭、标题栏按钮）刻意不参与焦点导航，
    // 聚焦兜底时也应跳过，避免焦点落到这些"不抢焦点"的按钮上
    if (el.getAttribute && el.getAttribute('tabindex') === '-1') return false
    return true
  }

  // 在区域内查找首个可聚焦元素并聚焦；找不到则回退聚焦容器
  function focusFirstIn(el, selector) {
    if (!el) return
    const defaultSel = 'textarea, input, [contenteditable="true"], button:not([disabled]):not([tabindex="-1"]), [tabindex]:not([tabindex="-1"])'
    const list = selector ? el.querySelectorAll(`${selector}:not([disabled])`) : el.querySelectorAll(defaultSel)
    for (const target of list) {
      if (isFocusableTarget(target)) {
        target.focus({ preventScroll: true })
        return
      }
    }
    focusZoneContainer(el)
  }

  // 构建可聚焦区域列表（仅当前可见项），并附上其屏幕矩形用于几何导航
  // 顺序：各 Session Panel → 集成终端 → 编辑器 → 聊天室
  function getFocusZones() {
    const zones = []
    for (const panel of panels().value) {
      if (!panel.agentId) continue
      zones.push({
        key: `session:${panel.id}`,
        kind: 'session',
        focus: () => {
          activatePanel()(panel.id)
          nextTick(() => {
            if (isAnyModalOpen()()) return
            focusCurrentPanelInput()(true)
          })
        },
      })
    }
    if (showTerminalPanel().value) {
      zones.push({
        key: 'terminal',
        kind: 'terminal',
        focus: () => {
          focusWindow()('terminal')
          nextTick(() => {
            if (focusActiveTerminal()) return
            // 无活跃终端时，回退聚焦终端内首个可聚焦控件（如"新建终端"按钮），
            // 避免聚焦到不可交互的容器后被框架重置焦点
            focusFirstIn(document.querySelector('.terminal-panel'))
          })
        },
      })
    }
    if (showWorkspacePanel().value) {
      zones.push({
        key: 'workspace',
        kind: 'workspace',
        focus: () => {
          focusWindow()('workspace')
          nextTick(() => {
            const view = getActiveWorkspaceView()()
            if (view) {
              view.focus()
              return
            }
            // 无编辑器内容时，回退聚焦编辑器内首个可聚焦控件（如活动栏按钮），
            // 避免聚焦到不可交互的容器后被框架重置焦点
            focusFirstIn(document.querySelector('.workspace-panel'))
          })
        },
      })
    }
    if (showChatPanel().value) {
      zones.push({
        key: 'chat',
        kind: 'chat',
        focus: () => {
          focusWindow()('chat')
          nextTick(() => {
            focusFirstIn(document.querySelector('.chat-panel'), '.chat-input')
          })
        },
      })
    }
    return zones
  }

  // 根据真实 DOM 焦点推断当前所处区域 key（比 activeWindow 更可靠：
  // activeWindow 仅在显式调用 focusWindow 时更新，用户点击面板输入框时不会同步）
  function getFocusedZoneKey() {
    const el = document.activeElement
    if (!el) return null
    const termEl = document.querySelector('.terminal-panel')
    if (termEl && termEl.contains(el)) return 'terminal'
    const workspaceEl = document.querySelector('.workspace-panel')
    if (workspaceEl && workspaceEl.contains(el)) return 'workspace'
    const chatEl = document.querySelector('.chat-panel')
    if (chatEl && chatEl.contains(el)) return 'chat'
    for (const panel of panels().value) {
      if (!panel.agentId) continue
      const root = sessionPanelRefs().get(panel.id)?.$el
      if (root && root.contains(el)) return `session:${panel.id}`
    }
    return null
  }

  // 当前所处的焦点区域 key（用于几何导航定位起点）
  function getActiveFocusZoneKey() {
    // 优先依据真实焦点位置
    const focusedKey = getFocusedZoneKey()
    if (focusedKey) return focusedKey
    // 回退：依据显式记录的当前窗口
    if (activeWindow().value === 'terminal' && showTerminalPanel().value) {
      return 'terminal'
    }
    if (activeWindow().value === 'workspace' && showWorkspacePanel().value) {
      return 'workspace'
    }
    if (activeWindow().value === 'chat' && showChatPanel().value) {
      return 'chat'
    }
    const panel = getCurrentPanel()()
    if (panel && panel.agentId) return `session:${panel.id}`
    return null
  }

  // 取焦点区域的屏幕矩形；不可见/无 DOM 时返回 null
  function getFocusZoneRect(zone) {
    if (!zone) return null
    let el = null
    if (zone.kind === 'session') {
      const panelId = zone.key.slice('session:'.length)
      el = sessionPanelRefs().get(panelId)?.$el || null
    } else if (zone.kind === 'terminal') {
      el = document.querySelector('.terminal-panel')
    } else if (zone.kind === 'workspace') {
      el = document.querySelector('.workspace-panel')
    } else if (zone.kind === 'chat') {
      el = document.querySelector('.chat-panel')
    }
    if (!el || typeof el.getBoundingClientRect !== 'function') return null
    const rect = el.getBoundingClientRect()
    if (rect.width <= 0 && rect.height <= 0) return null
    return rect
  }

  // 判断候选区域相对当前区域是否位于给定方向，并返回排序打分（越小越优先）
  // dir: 'left' | 'right' | 'up' | 'down'
  function scoreFocusZoneByDirection(curRect, candRect, dir) {
    const curCenterX = curRect.left + curRect.width / 2
    const curCenterY = curRect.top + curRect.height / 2
    const candCenterX = candRect.left + candRect.width / 2
    const candCenterY = candRect.top + candRect.height / 2

    if (dir === 'left') {
      if (candCenterX >= curCenterX) return null
      const primary = curRect.left - candRect.right
      // 垂直方向中心线位移越小越优先
      const secondary = Math.abs(candCenterY - curCenterY)
      return primary * 1000 + secondary
    }
    if (dir === 'right') {
      if (candCenterX <= curCenterX) return null
      const primary = candRect.left - curRect.right
      const secondary = Math.abs(candCenterY - curCenterY)
      return primary * 1000 + secondary
    }
    if (dir === 'up') {
      if (candCenterY >= curCenterY) return null
      const primary = curRect.top - candRect.bottom
      const secondary = Math.abs(candCenterX - curCenterX)
      return primary * 1000 + secondary
    }
    if (dir === 'down') {
      if (candCenterY <= curCenterY) return null
      const primary = candRect.top - curRect.bottom
      const secondary = Math.abs(candCenterX - curCenterX)
      return primary * 1000 + secondary
    }
    return null
  }

  // 按几何布局在可聚焦区域之间移动：根据当前区域矩形，选择该方向上最贴近的区域
  function moveFocusInDirection(dir) {
    const zones = getFocusZones()
    if (zones.length === 0) return
    const activeKey = getActiveFocusZoneKey()
    const currentZone = zones.find(z => z.key === activeKey)
    const curRect = getFocusZoneRect(currentZone)
    if (!curRect) return

    let bestZone = null
    let bestScore = Infinity
    for (const zone of zones) {
      if (zone.key === activeKey) continue
      const candRect = getFocusZoneRect(zone)
      if (!candRect) continue
      const score = scoreFocusZoneByDirection(curRect, candRect, dir)
      if (score === null) continue
      if (score < bestScore) {
        bestScore = score
        bestZone = zone
      }
    }
    if (bestZone) bestZone.focus()
  }

  return {
    focusActiveTerminal,
    focusZoneContainer,
    isFocusableTarget,
    focusFirstIn,
    getFocusZones,
    getFocusedZoneKey,
    getActiveFocusZoneKey,
    getFocusZoneRect,
    scoreFocusZoneByDirection,
    moveFocusInDirection,
  }
}
