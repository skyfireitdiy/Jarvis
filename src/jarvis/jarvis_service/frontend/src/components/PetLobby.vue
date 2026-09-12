<template>
  <div class="pet-lobby" ref="stageRef" @click="onStageClick">
    <!-- 地板风格背景 -->
    <div class="pet-lobby-floor"></div>
    <div class="pet-lobby-glow pet-lobby-glow-a"></div>
    <div class="pet-lobby-glow pet-lobby-glow-b"></div>

    <!-- 右上角：游走开关 -->
    <button
      class="pet-lobby-roam-toggle"
      :class="{ off: !roaming }"
      :title="roaming ? '点击停止宠物游走' : '点击开启宠物游走'"
      @click.stop="roaming = !roaming"
    >
      <span class="pet-lobby-roam-icon">{{ roaming ? '🔄' : '⏸' }}</span>
      <span class="pet-lobby-roam-label">{{ roaming ? '游走中' : '已静止' }}</span>
    </button>

    <!-- 无 Agent 提示 -->
    <div v-if="petAgents.length === 0" class="pet-lobby-empty">
      <div class="pet-lobby-empty-title">JARVIS</div>
      <p class="pet-lobby-empty-hint">按 <kbd>Ctrl</kbd>+<kbd>P</kbd> 打开命令面板，或从侧边栏创建一个 Agent</p>
    </div>

    <!-- 宠物群 -->
    <div
      v-for="pet in petAgents"
      :key="pet.agentId"
      class="lobby-pet"
      :class="[pet.classes, { dragging: pet.dragging, dimmed: activePetId && activePetId !== pet.agentId }]"
      :style="{ left: pet.x + 'px', top: pet.y + 'px' }"
      @pointerdown="onPetPointerDown(pet, $event)"
      @dblclick="onPetDblClick(pet)"
    >
      <div class="lobby-pet-inner">
        <div class="lobby-pet-body">
          <div class="lobby-pet-head">
            <div class="lobby-pet-ear l"></div>
            <div class="lobby-pet-ear r"></div>
            <div class="lobby-pet-eye l"><div class="lobby-pet-pupil"></div></div>
            <div class="lobby-pet-eye r"><div class="lobby-pet-pupil"></div></div>
            <div class="lobby-pet-mouth"></div>
          </div>
          <div class="lobby-pet-tail"></div>
        </div>
        <div class="lobby-pet-shadow"></div>
      </div>
      <div class="lobby-pet-name">{{ pet.name }}</div>
      <div class="lobby-pet-status" :class="pet.statusClass"></div>

      <!-- 输出气泡 + 输入/确认控件：堆叠在宠物下方 -->
      <div
        class="lobby-pet-stack"
        :class="{ 'stack-above': pet.panelAbove }"
        @pointerdown.stop
        @click.stop
        @dblclick.stop
      >
        <!-- 输出气泡：常驻显示（markdown 渲染）；点击气泡同样激活该 Agent -->
        <div
          v-if="pet.output"
          class="lobby-pet-output"
          v-html="pet.output"
          @click.stop="onPetClick(pet)"
        ></div>

        <!-- 确认控件：需要确认时直接显示（无需点击） -->
        <div v-if="pet.inputMode === 'confirm'" class="lobby-pet-panel">
          <div class="lobby-pet-confirm">
            <div class="lobby-pet-confirm-msg">{{ pet.confirmMessage || '请确认' }}</div>
            <div class="lobby-pet-confirm-actions">
              <button class="lobby-pet-confirm-btn yes" @click="submitConfirm(pet, true)">确认</button>
              <button class="lobby-pet-confirm-btn no" @click="submitConfirm(pet, false)">取消</button>
            </div>
          </div>
        </div>

        <!-- 输入面板：单击展开（多行/单行，按状态自动选择） -->
        <div v-else-if="pet.active" class="lobby-pet-panel">
          <!-- 多行输入 -->
          <div v-if="pet.inputMode === 'multi'" class="lobby-pet-input-row">
            <textarea
              class="lobby-pet-textarea"
              rows="3"
              :data-pet-input="pet.agentId"
              :placeholder="pet.inputTip || '输入内容 (Ctrl+Enter / Ctrl+D 发送)'"
              v-model="pet.inputText"
              @keydown="handlePetKeydown(pet, $event)"
              @input="handlePetInput(pet, $event)"
              @pointerdown.stop="onInputPointerDown(pet)"
            ></textarea>
            <button class="lobby-pet-send" @click="submitPet(pet)" title="发送 (Ctrl+Enter)">➤</button>
          </div>

          <!-- 单行输入 -->
          <div v-else class="lobby-pet-input-row">
            <input
              class="lobby-pet-input"
              :type="pet.isPassword ? 'password' : 'text'"
              :data-pet-input="pet.agentId"
              :placeholder="pet.inputTip || '输入内容 (Enter 发送)'"
              v-model="pet.inputText"
              @keydown="handlePetSingleKeydown(pet, $event)"
              @input="handlePetInput(pet, $event)"
              @pointerdown.stop="onInputPointerDown(pet)"
            />
            <button class="lobby-pet-send" @click="submitPet(pet)" title="发送 (Enter)">➤</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  agents: { type: Array, default: () => [] },
  getStatusClass: { type: Function, default: null },
  getInputState: { type: Function, default: null },
  getLatestOutput: { type: Function, default: null },
  historyNav: { type: Function, default: null },
})

const emit = defineEmits(['selectAgent', 'sendInput', 'complete', 'openCompletions'])

// 宠物尺寸常量（与 CSS 中的 .lobby-pet 宽高保持一致）
const PET_W = 72
const PET_H = 82
const PET_SPEED = 0.55 // 像素/帧，约 33px/秒
const MIN_DIST = 96 // 宠物之间最小间距，用于斥力避让
const EDGE_PAD = 12
const PANEL_H = 150 // 交互面板高度（粗略值，用于判断面板朝上/朝下）

const stageRef = ref(null)
const stageSize = ref({ w: 0, h: 0 })
const petAgents = ref([])
const activePetId = ref(null)
const roaming = ref(true) // 是否允许宠物自由游走

let rafId = null
let resizeObserver = null

function randBetween(min, max) {
  return min + Math.random() * (max - min)
}

function clampPos(x, y) {
  const maxX = Math.max(stageSize.value.w - PET_W - EDGE_PAD, EDGE_PAD)
  const maxY = Math.max(stageSize.value.h - PET_H - EDGE_PAD, EDGE_PAD)
  return {
    x: Math.min(Math.max(x, EDGE_PAD), maxX),
    y: Math.min(Math.max(y, EDGE_PAD), maxY),
  }
}

function pickTarget() {
  const maxX = Math.max(stageSize.value.w - PET_W - EDGE_PAD, EDGE_PAD)
  const maxY = Math.max(stageSize.value.h - PET_H - EDGE_PAD, EDGE_PAD)
  return {
    x: randBetween(EDGE_PAD, maxX),
    y: randBetween(EDGE_PAD, maxY),
  }
}

// 刷新某只宠物的输入态与最新输出
function refreshPetData(pet) {
  if (!pet) return
  const state = props.getInputState ? props.getInputState(pet.agentId) : null
  if (state) {
    pet.inputMode = state.mode
    pet.inputTip = state.tip
    pet.isPassword = state.isPassword
    pet.confirmMessage = state.confirmMessage
    pet.confirmDefault = state.confirmDefault
    // 首次进入或 preset 变化时填充输入框
    if (state.preset && !pet.inputText) {
      pet.inputText = state.preset
    }
  }
  const latest = props.getLatestOutput ? props.getLatestOutput(pet.agentId) : null
  pet.output = latest ? latest.html : ''
  // 堆叠容器（输出/输入/确认）默认在宠物下方；下方空间不足时改为上方
  pet.panelAbove = pet.y + PET_H + PANEL_H > stageSize.value.h
}

// 依据 agents 同步宠物实例：新增的补位，消失的移除，已有的保留位置
function syncPets() {
  const list = Array.isArray(props.agents) ? props.agents : []
  const existing = new Map(petAgents.value.map(p => [p.agentId, p]))
  const next = []
  for (const agent of list) {
    const agentId = agent.agent_id
    if (!agentId) continue
    // 已停止的 Agent 不显示宠物
    if (agent.status === 'stopped') continue
    let pet = existing.get(agentId)
    if (!pet) {
      const start = pickTarget()
      pet = {
        agentId,
        name: agent.name || agent.agent_id,
        x: start.x,
        y: start.y,
        target: pickTarget(),
        faceLeft: false,
        statusClass: '',
        classes: '',
        active: false,
        typing: false,
        dragging: false,
        inputMode: 'multi',
        inputText: '',
        inputTip: '',
        isPassword: false,
        confirmMessage: '',
        confirmDefault: true,
        output: '',
        panelAbove: false,
      }
    } else {
      pet.name = agent.name || agent.agent_id
    }
    const statusClass = props.getStatusClass ? props.getStatusClass(agent) : ''
    pet.statusClass = statusClass
    pet.classes = `status-${statusClass}${pet.faceLeft ? ' face-left' : ''}`
    refreshPetData(pet)
    next.push(pet)
  }
  petAgents.value = next
  // 若当前展开的宠物已消失，重置 activePetId
  if (activePetId.value && !next.some(p => p.agentId === activePetId.value)) {
    activePetId.value = null
  }
}

// 单帧：所有宠物向各自目标点移动，并做斥力避让
function step() {
  const pets = petAgents.value
  const n = pets.length
  // 计算两两斥力偏移
  const pushX = new Array(n).fill(0)
  const pushY = new Array(n).fill(0)
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const dx = pets[j].x - pets[i].x
      const dy = pets[j].y - pets[i].y
      const dist = Math.hypot(dx, dy) || 0.001
      if (dist < MIN_DIST) {
        const force = (MIN_DIST - dist) / MIN_DIST
        const ux = dx / dist
        const uy = dy / dist
        pushX[i] -= ux * force * 2.2
        pushY[i] -= uy * force * 2.2
        pushX[j] += ux * force * 2.2
        pushY[j] += uy * force * 2.2
      }
    }
  }

  for (let i = 0; i < n; i++) {
    const pet = pets[i]
    // 正在输入、展开交互面板或拖动中的宠物不移动
    if (pet.active || pet.typing || pet.dragging) continue
    if (!roaming.value) continue
    const dx = pet.target.x - pet.x
    const dy = pet.target.y - pet.y
    const dist = Math.hypot(dx, dy)
    if (dist < 6) {
      pet.target = pickTarget()
    } else {
      pet.x += (dx / dist) * PET_SPEED + pushX[i]
      pet.y += (dy / dist) * PET_SPEED + pushY[i]
    }
    const clamped = clampPos(pet.x, pet.y)
    pet.x = clamped.x
    pet.y = clamped.y
    const faceLeft = dx < -1
    if (faceLeft !== pet.faceLeft) {
      pet.faceLeft = faceLeft
      pet.classes = `status-${pet.statusClass}${faceLeft ? ' face-left' : ''}`
    }
  }

  rafId = requestAnimationFrame(step)
}

function measureStage() {
  const el = stageRef.value
  if (!el) return
  stageSize.value = { w: el.clientWidth, h: el.clientHeight }
}

// 点击大厅空白处：取消所有宠物的选中/展开状态，让它们恢复飘动
function onStageClick(event) {
  // 仅当点击目标是舞台本身（空白区域）时才处理；宠物及其面板已 stop 冒泡
  if (event.target !== stageRef.value) return
  for (const pet of petAgents.value) {
    if (pet.active) closePanel(pet)
  }
}

// 拖动状态
const DRAG_THRESHOLD = 4 // 超过该位移视为拖动而非点击
let dragState = null // { pet, startX, startY, offsetX, offsetY, moved }

function onPetPointerDown(pet, event) {
  // 仅响应鼠标左键 / 触摸 / 笔
  if (event.button !== undefined && event.button !== 0) return
  const stage = stageRef.value
  if (!stage) return
  const rect = stage.getBoundingClientRect()
  dragState = {
    pet,
    startX: event.clientX,
    startY: event.clientY,
    offsetX: event.clientX - rect.left - pet.x,
    offsetY: event.clientY - rect.top - pet.y,
    moved: false,
    rect,
  }
  window.addEventListener('pointermove', onPetPointerMove)
  window.addEventListener('pointerup', onPetPointerUp)
}

function onPetPointerMove(event) {
  if (!dragState) return
  const { pet } = dragState
  const dx = event.clientX - dragState.startX
  const dy = event.clientY - dragState.startY
  if (!dragState.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
  dragState.moved = true
  pet.dragging = true
  // 拖动时取消待执行的单击
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  const rect = dragState.rect
  const nx = event.clientX - rect.left - dragState.offsetX
  const ny = event.clientY - rect.top - dragState.offsetY
  const clamped = clampPos(nx, ny)
  pet.x = clamped.x
  pet.y = clamped.y
  pet.target = { x: clamped.x, y: clamped.y }
}

function onPetPointerUp() {
  window.removeEventListener('pointermove', onPetPointerMove)
  window.removeEventListener('pointerup', onPetPointerUp)
  if (!dragState) return
  const { pet, moved } = dragState
  dragState = null
  if (pet.dragging) {
    pet.dragging = false
    // 松开后从当前位置继续飘动
    pet.target = pickTarget()
    return
  }
  // 未发生拖动：视为单击
  if (!moved) onPetClick(pet)
}

// 单击：延时判定，避免与双击冲突（双击时取消单击动作）
let clickTimer = null
function onPetClick(pet) {
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  clickTimer = setTimeout(() => {
    clickTimer = null
    if (pet.active) {
      closePanel(pet)
    } else {
      openPanel(pet)
    }
  }, 250)
}

// 双击：进入该 Agent 的详细视图（取消待执行的单击）
function onPetDblClick(pet) {
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  closePanel(pet)
  emit('selectAgent', pet.agentId)
}

function openPanel(pet) {
  // 同一时刻只展开一只
  if (activePetId.value && activePetId.value !== pet.agentId) {
    const prev = petAgents.value.find(p => p.agentId === activePetId.value)
    if (prev) closePanel(prev)
  }
  activePetId.value = pet.agentId
  pet.active = true
  pet.typing = false
  refreshPetData(pet)
}

function closePanel(pet) {
  if (!pet) return
  pet.active = false
  pet.typing = false
  pet.inputText = ''
  if (activePetId.value === pet.agentId) activePetId.value = null
}

function onInputPointerDown(pet) {
  pet.typing = true
}

// 多行输入框快捷键，与 Agent Panel 保持一致：
// Ctrl+Enter / Ctrl+D 发送；Enter 换行；上下箭头在首/末行时翻阅历史；Ctrl+C 空输入时发送完成信号
function handlePetKeydown(pet, event) {
  if (event.key === '@') {
    event.preventDefault()
    emit('openCompletions', pet.agentId, event.target.selectionStart)
    return
  }
  if (event.ctrlKey && (event.key === 'Enter' || event.key.toLowerCase() === 'd')) {
    event.preventDefault()
    submitPet(pet)
    return
  }
  if (event.key === 'ArrowUp' && !event.ctrlKey && !event.altKey && !event.metaKey) {
    const textarea = event.target
    if (isCursorAtFirstLine(textarea)) {
      event.preventDefault()
      if (props.historyNav) {
        const val = props.historyNav(pet.agentId, 'up', pet.inputText || '')
        if (typeof val === 'string') pet.inputText = val
      }
    }
    return
  }
  if (event.key === 'ArrowDown' && !event.ctrlKey && !event.altKey && !event.metaKey) {
    const textarea = event.target
    if (isCursorAtLastLine(textarea)) {
      event.preventDefault()
      if (props.historyNav) {
        const val = props.historyNav(pet.agentId, 'down', pet.inputText || '')
        if (typeof val === 'string') pet.inputText = val
      }
    }
    return
  }
  if (event.ctrlKey && event.key === 'c') {
    const hasText = (pet.inputText || '').trim().length > 0
    // 仅当没有选中文本且输入为空时，才拦截 Ctrl+C 发送完成信号
    const hasSelection = event.target.selectionStart !== event.target.selectionEnd
    if (!hasText && !hasSelection && pet.inputMode === 'multi') {
      event.preventDefault()
      emit('complete', pet.agentId)
    }
  }
}

// 单行输入框快捷键：Enter 发送；@ 打开补全
function handlePetSingleKeydown(pet, event) {
  if (event.key === '@') {
    event.preventDefault()
    emit('openCompletions', pet.agentId, event.target.selectionStart)
    return
  }
  if (event.key === 'Enter' && !event.ctrlKey && !event.altKey && !event.metaKey) {
    event.preventDefault()
    submitPet(pet)
  }
}

// 输入变化：检测是否刚输入 @（含中文输入法），触发补全
function handlePetInput(pet, event) {
  const target = event.target
  const cursorPosition = target.selectionStart
  const textBeforeCursor = target.value.substring(0, cursorPosition)
  if (textBeforeCursor.endsWith('@')) {
    emit('openCompletions', pet.agentId, cursorPosition - 1)
  }
}

function isCursorAtFirstLine(textarea) {
  const pos = textarea.selectionStart
  return !textarea.value.substring(0, pos).includes('\n')
}

function isCursorAtLastLine(textarea) {
  const pos = textarea.selectionEnd
  return !textarea.value.substring(pos).includes('\n')
}

function submitPet(pet) {
  const text = pet.inputMode === 'single' ? pet.inputText : pet.inputText.trim()
  if (pet.inputMode !== 'single' && !text) return
  emit('sendInput', pet.agentId, text, pet.inputMode)
  pet.inputText = ''
  pet.typing = false
  refreshPetData(pet)
}

function submitConfirm(pet, confirmed) {
  emit('sendInput', pet.agentId, confirmed ? 'y' : 'n', 'confirm')
  refreshPetData(pet)
}

// 定时刷新：状态灯、输出气泡、输入态（输出/确认常驻显示，需对所有宠物刷新）
let refreshTimer = null
function refreshLoop() {
  for (const pet of petAgents.value) {
    const agent = (props.agents || []).find(a => a.agent_id === pet.agentId)
    if (agent && props.getStatusClass) {
      const statusClass = props.getStatusClass(agent)
      if (statusClass !== pet.statusClass) {
        pet.statusClass = statusClass
        pet.classes = `status-${statusClass}${pet.faceLeft ? ' face-left' : ''}`
      }
    }
    // 正在输入时不覆盖输入框内容，但仍刷新输出/确认态
    if (!pet.typing) {
      refreshPetData(pet)
    }
  }
}

onMounted(() => {
  measureStage()
  syncPets()
  rafId = requestAnimationFrame(step)
  refreshTimer = setInterval(refreshLoop, 800)
  if (typeof ResizeObserver !== 'undefined' && stageRef.value) {
    resizeObserver = new ResizeObserver(() => measureStage())
    resizeObserver.observe(stageRef.value)
  }
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = null
  window.removeEventListener('pointermove', onPetPointerMove)
  window.removeEventListener('pointerup', onPetPointerUp)
  dragState = null
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})

// agents 变化时同步宠物实例
watch(() => props.agents, () => syncPets(), { deep: false })

// 供父组件写回补全文本：把 @ 及后续搜索词替换为补全值，并同步 DOM 光标
function insertCompletionText(agentId, text, cursorPos, hasAtSymbol) {
  const pet = petAgents.value.find(p => p.agentId === agentId)
  if (!pet) return
  const value = pet.inputText || ''
  let start
  let end
  if (hasAtSymbol && typeof cursorPos === 'number' && cursorPos >= 0 && cursorPos <= value.length) {
    // cursorPos 指向 @ 符号所在位置：替换掉该 @
    start = cursorPos
    end = cursorPos + 1
  } else {
    // 无 @ 可删：在记录的光标处插入，未记录时追加到末尾
    start = (typeof cursorPos === 'number' && cursorPos >= 0 && cursorPos <= value.length) ? cursorPos : value.length
    end = start
  }
  const inserted = `'${text}'`
  const next = value.substring(0, start) + inserted + value.substring(end)
  pet.inputText = next
  pet.typing = true
  const newPos = start + inserted.length
  requestAnimationFrame(() => {
    const el = stageRef.value && stageRef.value.querySelector(`[data-pet-input="${agentId}"]`)
    if (el) {
      el.value = next
      try { el.setSelectionRange(newPos, newPos) } catch (e) { /* ignore */ }
      el.focus()
    }
  })
}

defineExpose({ insertCompletionText })
</script>

<style scoped>
.pet-lobby {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: var(--tile-radius, 12px);
}

/* 地板风格背景：透视网格 */
.pet-lobby-floor {
  position: absolute;
  inset: -20%;
  background-image:
    linear-gradient(rgba(32, 200, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(32, 200, 255, 0.08) 1px, transparent 1px);
  background-size: 56px 56px, 56px 56px;
  mask-image: radial-gradient(circle at 50% 55%, #000 0%, transparent 78%);
  -webkit-mask-image: radial-gradient(circle at 50% 55%, #000 0%, transparent 78%);
  animation: lobbyFloorDrift 40s linear infinite;
  pointer-events: none;
}

@keyframes lobbyFloorDrift {
  from { background-position: 0 0, 0 0; }
  to { background-position: 56px 56px, 56px 56px; }
}

.pet-lobby-glow {
  position: absolute;
  width: 50vmax;
  height: 50vmax;
  border-radius: 50%;
  filter: blur(48px);
  opacity: 0.4;
  pointer-events: none;
}
.pet-lobby-glow-a {
  top: -20%;
  left: -12%;
  background: radial-gradient(circle, rgba(32, 200, 255, 0.22) 0%, transparent 62%);
}
.pet-lobby-glow-b {
  bottom: -24%;
  right: -14%;
  background: radial-gradient(circle, rgba(54, 255, 124, 0.16) 0%, transparent 62%);
}

.pet-lobby-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  padding: 0 24px;
}
.pet-lobby-empty-title {
  font-size: 34px;
  letter-spacing: 0.32em;
  font-weight: 700;
  color: var(--color-text-primary, #e6f6ff);
  text-shadow: 0 0 22px rgba(32, 200, 255, 0.55);
}
.pet-lobby-empty-hint {
  font-size: 13px;
  color: var(--color-text-secondary, #8aa8bd);
  margin: 0;
}

/* ===== 游走开关 ===== */
.pet-lobby-roam-toggle {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 40;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  color: #d6f2ff;
  background: rgba(10, 24, 38, 0.86);
  border: 1px solid rgba(32, 200, 255, 0.4);
  border-radius: 999px;
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}
.pet-lobby-roam-toggle:hover {
  background: rgba(16, 40, 60, 0.95);
  border-color: rgba(32, 200, 255, 0.75);
}
.pet-lobby-roam-toggle.off {
  color: #9fb4c4;
  border-color: rgba(120, 140, 160, 0.45);
}
.pet-lobby-roam-icon {
  font-size: 13px;
  line-height: 1;
}

/* ===== 迷你宠物 ===== */
.lobby-pet {
  position: absolute;
  width: 72px;
  height: 82px;
  cursor: pointer;
  user-select: none;
  pointer-events: auto;
  transition: filter 0.25s ease, opacity 0.25s ease;
  /* 每个宠物建立独立 stacking context，使「本体 + 输出/输入框」作为整体参与层级比较，
     避免 A 的窗口覆盖 B 的宠物、B 的窗口又覆盖 A 的宠物的交叉覆盖 */
  z-index: 1;
}
.lobby-pet:hover {
  filter: brightness(1.15);
}
.lobby-pet.active {
  z-index: 20;
}
/* 有宠物被激活时，其余宠物及其输出/输入框变暗，突出当前交互对象 */
.lobby-pet.dimmed {
  opacity: 0.38;
  filter: brightness(0.55) saturate(0.6);
}
.lobby-pet.dimmed:hover {
  opacity: 0.7;
  filter: brightness(0.9) saturate(0.8);
}
.lobby-pet.dragging {
  cursor: grabbing;
  z-index: 20;
  filter: brightness(1.2);
}

.lobby-pet-inner {
  position: relative;
  width: 100%;
  height: 100%;
}

.lobby-pet-body {
  position: absolute;
  left: 50%;
  bottom: 12px;
  width: 52px;
  height: 46px;
  transform: translateX(-50%);
  animation: lobbyPetBob 2.6s ease-in-out infinite;
}

@keyframes lobbyPetBob {
  0%, 100% { transform: translateX(-50%) translateY(0); }
  50% { transform: translateX(-50%) translateY(-3px); }
}

.lobby-pet-head {
  position: absolute;
  left: 50%;
  top: 0;
  width: 42px;
  height: 37px;
  transform: translateX(-50%);
  background: linear-gradient(160deg, #2ee6ff 0%, #1a9fd6 55%, #0e6f9e 100%);
  border-radius: 50% 50% 46% 46%;
  box-shadow: 0 0 10px rgba(32, 200, 255, 0.45), inset 0 -3px 6px rgba(0, 0, 0, 0.25),
    inset 0 2px 4px rgba(255, 255, 255, 0.18);
}

.lobby-pet-ear {
  position: absolute;
  top: -8px;
  width: 0;
  height: 0;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-bottom: 12px solid #23b9e8;
  filter: drop-shadow(0 0 3px rgba(32, 200, 255, 0.5));
}
.lobby-pet-ear.l { left: 2px; transform: rotate(-18deg); }
.lobby-pet-ear.r { right: 2px; transform: rotate(18deg); }

.lobby-pet-eye {
  position: absolute;
  top: 14px;
  width: 7px;
  height: 8px;
  border-radius: 50%;
  background: #06131f;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.75);
  animation: lobbyPetBlink 4.2s infinite;
}
.lobby-pet-eye.l { left: 10px; }
.lobby-pet-eye.r { right: 10px; }

.lobby-pet-pupil {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: rgba(234, 252, 255, 0.9);
  transform: translate(-50%, -50%);
}

@keyframes lobbyPetBlink {
  0%, 92%, 100% { transform: scaleY(1); }
  95% { transform: scaleY(0.1); }
}

.lobby-pet-mouth {
  position: absolute;
  left: 50%;
  top: 27px;
  width: 10px;
  height: 5px;
  transform: translateX(-50%);
  border-bottom: 1.5px solid rgba(6, 19, 31, 0.75);
  border-radius: 0 0 4px 4px;
}

.lobby-pet-tail {
  position: absolute;
  right: -8px;
  bottom: 6px;
  width: 19px;
  height: 19px;
  border: 2px solid #23b9e8;
  border-color: #23b9e8 transparent transparent transparent;
  border-radius: 50%;
  transform-origin: 0% 100%;
  animation: lobbyPetTail 1.6s ease-in-out infinite;
  filter: drop-shadow(0 0 3px rgba(32, 200, 255, 0.45));
}

@keyframes lobbyPetTail {
  0%, 100% { transform: rotate(0deg); }
  50% { transform: rotate(-16deg); }
}

.lobby-pet-shadow {
  position: absolute;
  left: 50%;
  bottom: 8px;
  width: 44px;
  height: 8px;
  transform: translateX(-50%);
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.35);
  filter: blur(2px);
  pointer-events: none;
}

/* 朝向翻转 */
.lobby-pet.face-left .lobby-pet-body {
  transform: translateX(-50%) scaleX(-1);
}

.lobby-pet-name {
  position: absolute;
  left: 50%;
  bottom: -4px;
  transform: translateX(-50%);
  max-width: 88px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  color: rgba(180, 220, 245, 0.85);
  text-shadow: 0 0 6px rgba(0, 0, 0, 0.6);
  pointer-events: none;
}

/* 状态灯 */
.lobby-pet-status {
  position: absolute;
  right: 4px;
  top: 4px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #6b8299;
  box-shadow: 0 0 6px rgba(0, 0, 0, 0.5);
}
.lobby-pet-status.running { background: #36ff7c; box-shadow: 0 0 8px rgba(54, 255, 124, 0.8); }
.lobby-pet-status.waiting_multi,
.lobby-pet-status.waiting_confirm,
.lobby-pet-status.waiting_single { background: #ffab3d; box-shadow: 0 0 8px rgba(255, 171, 61, 0.9); animation: lobbyStatusPulse 1.4s ease-in-out infinite; }
.lobby-pet-status.stopped { background: #6b8299; }

@keyframes lobbyStatusPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ===== 输出气泡 + 输入/确认控件堆叠容器 ===== */
.lobby-pet-stack {
  position: absolute;
  left: 50%;
  top: calc(100% + 4px);
  transform: translateX(-50%);
  width: min(560px, 62vw);
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: default;
  z-index: 6;
}
.lobby-pet-stack.stack-above {
  top: auto;
  bottom: calc(100% + 4px);
  flex-direction: column-reverse;
}

.lobby-pet-panel {
  width: 100%;
  background: rgba(10, 24, 38, 0.96);
  border: 1px solid rgba(32, 200, 255, 0.35);
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55), 0 0 16px rgba(32, 200, 255, 0.18);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: default;
}

/* 输出气泡（markdown） */
.lobby-pet-output {
  width: 100%;
  box-sizing: border-box;
  min-height: 120px;
  max-height: 60vh;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.65;
  color: #dff1fb;
  background: rgba(10, 24, 38, 0.94);
  border: 1px solid rgba(32, 200, 255, 0.28);
  border-radius: 10px;
  padding: 10px 12px;
  word-break: break-word;
  box-shadow: 0 8px 26px rgba(0, 0, 0, 0.5);
}
.lobby-pet-output :deep(p) { margin: 0 0 6px; }
.lobby-pet-output :deep(p:last-child) { margin-bottom: 0; }
.lobby-pet-output :deep(pre) {
  margin: 6px 0;
  padding: 8px;
  background: rgba(0, 0, 0, 0.45);
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
}
.lobby-pet-output :deep(code) { font-family: 'Consolas', monospace; }
.lobby-pet-output :deep(ul), .lobby-pet-output :deep(ol) { margin: 6px 0; padding-left: 20px; }
.lobby-pet-output :deep(a) { color: #7ee7ff; }
.lobby-pet-output :deep(h1), .lobby-pet-output :deep(h2), .lobby-pet-output :deep(h3) { margin: 6px 0; font-size: 14px; }

/* 输入行 */
.lobby-pet-input-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
.lobby-pet-textarea,
.lobby-pet-input {
  flex: 1;
  min-width: 0;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(32, 200, 255, 0.3);
  border-radius: 6px;
  color: #e6f6ff;
  font-size: 12px;
  font-family: inherit;
  padding: 5px 7px;
  resize: none;
  outline: none;
}
.lobby-pet-textarea:focus,
.lobby-pet-input:focus {
  border-color: rgba(32, 200, 255, 0.7);
  box-shadow: 0 0 8px rgba(32, 200, 255, 0.25);
}
.lobby-pet-send {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  border-radius: 6px;
  border: 1px solid rgba(32, 200, 255, 0.4);
  background: rgba(32, 200, 255, 0.15);
  color: #7ee7ff;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}
.lobby-pet-send:hover { background: rgba(32, 200, 255, 0.3); }

/* 确认气泡 */
.lobby-pet-confirm {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.lobby-pet-confirm-msg {
  font-size: 12px;
  color: #ffd79a;
  background: rgba(255, 171, 61, 0.12);
  border-radius: 6px;
  padding: 6px 8px;
}
.lobby-pet-confirm-actions {
  display: flex;
  gap: 6px;
}
.lobby-pet-confirm-btn {
  flex: 1;
  padding: 5px 0;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 12px;
}
.lobby-pet-confirm-btn.yes {
  background: rgba(54, 255, 124, 0.18);
  border-color: rgba(54, 255, 124, 0.5);
  color: #a6ffcb;
}
.lobby-pet-confirm-btn.no {
  background: rgba(255, 90, 90, 0.15);
  border-color: rgba(255, 90, 90, 0.45);
  color: #ffb3b3;
}
</style>
