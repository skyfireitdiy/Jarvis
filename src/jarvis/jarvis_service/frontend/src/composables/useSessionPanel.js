// SessionPanel 浮动面板 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 阶段3），保持行为完全一致。
// 覆盖 SessionPanel 浮动面板子域：
// - 常量：SESSION_PANEL_MIN_WIDTH/SESSION_PANEL_MIN_HEIGHT/SESSION_PANEL_STORAGE_KEY_PREFIX/sessionResizeDirections
// - 状态：sessionPanelRects（panelId -> rect）/sessionPanelInteraction
// - 矩形持久化：getDefaultSessionPanelRect/loadSessionPanelRect/saveSessionPanelRect
// - 样式/边界：getSessionPanelStyle/getSessionPanelBounds/ensureSessionPanelInViewport
// - 拖拽交互：startSessionPanelMove/startSessionPanelResize/onSessionPanelPointerMove/stopSessionPanelInteraction
//
// 依赖注入（直传，均定义在调用点之前）：
// activeWindow/ACTIVE_Z_INDEX/BASE_Z_INDEX/clamp/windowWidth/PANEL_DRAG_ACTIVATION_DISTANCE/focusWindow
import { ref } from 'vue'

export function useSessionPanel({
  activeWindow,
  ACTIVE_Z_INDEX,
  BASE_Z_INDEX,
  clamp,
  windowWidth,
  PANEL_DRAG_ACTIVATION_DISTANCE,
  focusWindow,
}) {
  const SESSION_PANEL_MIN_WIDTH = 400
  const SESSION_PANEL_MIN_HEIGHT = 300
  const SESSION_PANEL_STORAGE_KEY_PREFIX = 'jarvis_session_panel_rect_'
  const sessionResizeDirections = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

  function getDefaultSessionPanelRect(panelId) {
    return {
      top: 80,
      left: Math.max(window.innerWidth - 824, 16),
      width: 600,
      height: 500,
    }
  }

  function loadSessionPanelRect(panelId) {
    const defaultRect = getDefaultSessionPanelRect(panelId)
    const savedValue = localStorage.getItem(SESSION_PANEL_STORAGE_KEY_PREFIX + panelId)
    if (!savedValue) {
      return defaultRect
    }

    try {
      const parsedValue = JSON.parse(savedValue)
      if (
        typeof parsedValue.top !== 'number' ||
        typeof parsedValue.left !== 'number' ||
        typeof parsedValue.width !== 'number' ||
        typeof parsedValue.height !== 'number'
      ) {
        return defaultRect
      }

      return parsedValue
    } catch {
      return defaultRect
    }
  }

  function saveSessionPanelRect(panelId) {
    const rect = sessionPanelRects.value[panelId]
    if (rect) {
      localStorage.setItem(SESSION_PANEL_STORAGE_KEY_PREFIX + panelId, JSON.stringify(rect))
    }
  }

  const sessionPanelRects = ref({})  // panelId -> rect
  const sessionPanelInteraction = ref({
    active: false,
    mode: null,
    direction: null,
    panelId: null,
    startX: 0,
    startY: 0,
    startTop: 0,
    startLeft: 0,
    startWidth: 0,
    startHeight: 0,
  })

  function getSessionPanelStyle(panelId) {
    const rect = sessionPanelRects.value[panelId]
    if (!rect) return {}
    return {
      top: `${rect.top}px`,
      left: `${rect.left}px`,
      width: `${rect.width}px`,
      height: `${rect.height}px`,
      zIndex: activeWindow.value === 'session' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
    }
  }

  function getSessionPanelBounds() {
    const HEADER_HEIGHT = 32
    const MIN_VISIBLE_WIDTH = 100
    return {
      minTop: 0,
      minLeft: 0,
      maxLeft: window.innerWidth - MIN_VISIBLE_WIDTH,
      maxTop: window.innerHeight - HEADER_HEIGHT,
    }
  }

  function ensureSessionPanelInViewport(panelId) {
    const rect = sessionPanelRects.value[panelId]
    if (!rect) return
    const HEADER_HEIGHT = 32
    const MIN_VISIBLE_WIDTH = 100
    const maxWidth = Math.max(window.innerWidth, SESSION_PANEL_MIN_WIDTH)
    const maxHeight = Math.max(window.innerHeight, SESSION_PANEL_MIN_HEIGHT)

    rect.width = clamp(rect.width, SESSION_PANEL_MIN_WIDTH, maxWidth)
    rect.height = clamp(rect.height, SESSION_PANEL_MIN_HEIGHT, maxHeight)

    rect.left = clamp(
      rect.left,
      0,
      window.innerWidth - MIN_VISIBLE_WIDTH
    )
    rect.top = clamp(
      rect.top,
      0,
      window.innerHeight - HEADER_HEIGHT
    )
  }

  function startSessionPanelMove(event, panelId) {
    if (windowWidth.value <= 768) return
    if (event.target.closest('.session-header-actions')) return

    focusWindow('session')

    const rect = sessionPanelRects.value[panelId]
    if (!rect) return

    sessionPanelInteraction.value = {
      active: false,
      mode: 'move',
      direction: null,
      panelId,
      startX: event.clientX,
      startY: event.clientY,
      startTop: rect.top,
      startLeft: rect.left,
      startWidth: rect.width,
      startHeight: rect.height,
    }

    document.addEventListener('mousemove', onSessionPanelPointerMove)
    document.addEventListener('mouseup', stopSessionPanelInteraction)
  }

  function startSessionPanelResize(event, direction, panelId) {
    if (windowWidth.value <= 768) return

    const rect = sessionPanelRects.value[panelId]
    if (!rect) return

    sessionPanelInteraction.value = {
      active: true,
      mode: 'resize',
      direction,
      panelId,
      startX: event.clientX,
      startY: event.clientY,
      startTop: rect.top,
      startLeft: rect.left,
      startWidth: rect.width,
      startHeight: rect.height,
    }

    document.addEventListener('mousemove', onSessionPanelPointerMove)
    document.addEventListener('mouseup', stopSessionPanelInteraction)
    event.preventDefault()
    event.stopPropagation()
  }

  function onSessionPanelPointerMove(event) {
    const interaction = sessionPanelInteraction.value
    const panelId = interaction.panelId
    const rect = sessionPanelRects.value[panelId]
    if (!rect) return

    const deltaX = event.clientX - interaction.startX
    const deltaY = event.clientY - interaction.startY

    if (interaction.mode === 'move' && !interaction.active) {
      const dragDistance = Math.hypot(deltaX, deltaY)
      if (dragDistance < PANEL_DRAG_ACTIVATION_DISTANCE) {
        return
      }

      sessionPanelInteraction.value = {
        ...interaction,
        active: true,
      }
      event.preventDefault()
    }

    if (!sessionPanelInteraction.value.active) return

    if (sessionPanelInteraction.value.mode === 'move') {
      const bounds = getSessionPanelBounds()
      rect.left = clamp(interaction.startLeft + deltaX, bounds.minLeft, bounds.maxLeft)
      rect.top = clamp(interaction.startTop + deltaY, bounds.minTop, bounds.maxTop)
      return
    }

    const direction = sessionPanelInteraction.value.direction || ''
    const startLeft = sessionPanelInteraction.value.startLeft
    const startTop = sessionPanelInteraction.value.startTop
    const startWidth = sessionPanelInteraction.value.startWidth
    const startHeight = sessionPanelInteraction.value.startHeight

    let nextLeft = startLeft
    let nextTop = startTop
    let nextWidth = startWidth
    let nextHeight = startHeight

    if (direction.includes('e')) {
      nextWidth = clamp(startWidth + deltaX, SESSION_PANEL_MIN_WIDTH, Math.max(window.innerWidth - startLeft, SESSION_PANEL_MIN_WIDTH))
    }

    if (direction.includes('s')) {
      nextHeight = clamp(startHeight + deltaY, SESSION_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - startTop, SESSION_PANEL_MIN_HEIGHT))
    }

    if (direction.includes('w')) {
      const desiredLeft = clamp(startLeft + deltaX, 0, startLeft + startWidth - SESSION_PANEL_MIN_WIDTH)
      nextLeft = desiredLeft
      nextWidth = startWidth - (desiredLeft - startLeft)
    }

    if (direction.includes('n')) {
      const desiredTop = clamp(startTop + deltaY, 0, startTop + startHeight - SESSION_PANEL_MIN_HEIGHT)
      nextTop = desiredTop
      nextHeight = startHeight - (desiredTop - startTop)
    }

    if (nextLeft + nextWidth > window.innerWidth) {
      nextWidth = Math.max(SESSION_PANEL_MIN_WIDTH, window.innerWidth - nextLeft)
    }

    if (nextTop + nextHeight > window.innerHeight) {
      nextHeight = Math.max(SESSION_PANEL_MIN_HEIGHT, window.innerHeight - nextTop)
    }

    rect.left = clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0))
    rect.top = clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0))
    rect.width = clamp(nextWidth, SESSION_PANEL_MIN_WIDTH, Math.max(window.innerWidth - rect.left, SESSION_PANEL_MIN_WIDTH))
    rect.height = clamp(nextHeight, SESSION_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - rect.top, SESSION_PANEL_MIN_HEIGHT))
  }

  function stopSessionPanelInteraction() {
    const panelId = sessionPanelInteraction.value.panelId
    sessionPanelInteraction.value = {
      active: false,
      mode: null,
      direction: null,
      panelId: null,
      startX: 0,
      startY: 0,
      startTop: 0,
      startLeft: 0,
      startWidth: 0,
      startHeight: 0,
    }

    document.removeEventListener('mousemove', onSessionPanelPointerMove)
    document.removeEventListener('mouseup', stopSessionPanelInteraction)
    if (panelId) {
      saveSessionPanelRect(panelId)
    }
  }

  return {
    SESSION_PANEL_MIN_WIDTH,
    SESSION_PANEL_MIN_HEIGHT,
    SESSION_PANEL_STORAGE_KEY_PREFIX,
    sessionResizeDirections,
    getDefaultSessionPanelRect,
    loadSessionPanelRect,
    saveSessionPanelRect,
    sessionPanelRects,
    sessionPanelInteraction,
    getSessionPanelStyle,
    getSessionPanelBounds,
    ensureSessionPanelInViewport,
    startSessionPanelMove,
    startSessionPanelResize,
    onSessionPanelPointerMove,
    stopSessionPanelInteraction,
  }
}
