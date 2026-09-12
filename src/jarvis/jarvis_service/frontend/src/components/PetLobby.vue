<template>
  <div class="pet-lobby" ref="stageRef" @click="onStageClick">
    <!-- 地板风格背景 -->
    <div class="pet-lobby-floor"></div>
    <!-- 地板上的 Slogan：做旧、斑驳的沧桑质感 -->
    <div class="pet-lobby-slogan" aria-hidden="true">
      <span class="pet-lobby-slogan-text">独当一面，与众共事</span>
    </div>
    <div class="pet-lobby-glow pet-lobby-glow-a"></div>
    <div class="pet-lobby-glow pet-lobby-glow-b"></div>

    <!-- 节点与连线层：参考大屏「网络拓扑」风格（机箱造型 + 连线），位于地板之上、宠物之下 -->
    <div class="pet-lobby-topology" aria-hidden="true">
      <svg class="pet-lobby-links" :width="stageSize.w" :height="stageSize.h" :viewBox="`0 0 ${stageSize.w} ${stageSize.h}`">
        <defs>
          <linearGradient id="lobby-line" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#20c8ff" stop-opacity="0.9" />
            <stop offset="100%" stop-color="#20c8ff" stop-opacity="0.25" />
          </linearGradient>
          <linearGradient id="lobby-center-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#e8d089" />
            <stop offset="100%" stop-color="#c99a34" />
          </linearGradient>
          <filter id="lobby-glow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="2.4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <!-- 连线：master → 各节点 -->
        <g class="lobby-links-master">
          <line
            v-for="link in nodeLinks"
            :key="link.key"
            :x1="link.x1"
            :y1="link.y1"
            :x2="link.x2"
            :y2="link.y2"
            :stroke="link.offline ? 'rgba(255,93,108,0.35)' : 'url(#lobby-line)'"
            :stroke-width="1.6"
            :stroke-dasharray="link.offline ? '6 5' : ''"
            class="lobby-link"
            :class="{ 'is-flow': !link.offline }"
          />
        </g>

        <!-- 连线：子节点之间（按圆周顺序连成环） -->
        <g class="lobby-links-peer">
          <line
            v-for="pl in peerLinks"
            :key="pl.key"
            :x1="pl.x1"
            :y1="pl.y1"
            :x2="pl.x2"
            :y2="pl.y2"
            :stroke="pl.offline ? 'rgba(255,93,108,0.3)' : 'rgba(32,200,255,0.45)'"
            stroke-width="1.4"
            :stroke-dasharray="pl.offline ? '6 5' : '2 4'"
          />
        </g>

        <!-- 连线：Agent 宠物 → 其所属节点（随宠物移动实时更新） -->
        <g class="lobby-links-agent">
          <line
            v-for="link in agentLinks"
            :key="link.key"
            :x1="link.x1"
            :y1="link.y1"
            :x2="link.x2"
            :y2="link.y2"
            :stroke="link.color"
            stroke-width="1"
            stroke-dasharray="3 3"
            opacity="0.7"
          />
        </g>

        <!-- 节点：服务器机箱造型（master 金色居中，其余按状态着色） -->
        <g
          v-for="n in nodeItems"
          :key="n.node_id"
          class="lobby-node"
          :class="['st-' + n.state, { 'is-center': n.isMaster }]"
        >
          <!-- 机箱主体 -->
          <rect
            :x="n.x - n.rw"
            :y="n.y - n.rh"
            :width="n.rw * 2"
            :height="n.rh * 2"
            rx="6"
            :fill="n.fill"
            :stroke="n.color"
            :stroke-width="n.isMaster ? 1.6 : 1.3"
            class="lobby-node-body"
          />
          <!-- 顶部插槽 -->
          <line
            :x1="n.x - n.rw + 6" :y1="n.y - n.rh + 7"
            :x2="n.x + n.rw - 6" :y2="n.y - n.rh + 7"
            :stroke="n.color" stroke-width="1.4" opacity="0.6"
          />
          <!-- 散热格栅 -->
          <line
            v-for="k in 3" :key="'g' + k"
            :x1="n.x - n.rw + 8" :y1="n.y - n.rh + 6 + k * 4.6"
            :x2="n.x + n.rw - 16" :y2="n.y - n.rh + 6 + k * 4.6"
            :stroke="n.color" stroke-width="1" opacity="0.35"
          />
          <!-- 指示灯 -->
          <circle :cx="n.x + n.rw - 10" :cy="n.y - 2" r="2.4" :fill="n.color" class="lobby-node-led" />
          <circle :cx="n.x + n.rw - 10" :cy="n.y + 5" r="2.4" :fill="n.color" opacity="0.4" />
          <!-- 底部状态条 -->
          <rect
            :x="n.x - n.rw + 6" :y="n.y + n.rh - 8"
            :width="n.rw * 2 - 12" :height="3" rx="1.5"
            :fill="n.color" opacity="0.5"
          />
          <text :x="n.x" :y="n.y + n.rh + 16" text-anchor="middle" class="lobby-node-label">{{ n.short }}</text>
          <text :x="n.x" :y="n.y + n.rh + 29" text-anchor="middle" class="lobby-node-count">{{ n.agentCount }} agent</text>
        </g>
      </svg>
    </div>

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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { normalizeNodeStatus, normalizeAgentStatus } from './topology.js'

const props = defineProps({
  agents: { type: Array, default: () => [] },
  nodes: { type: Array, default: () => [] },
  getStatusClass: { type: Function, default: null },
  getInputState: { type: Function, default: null },
  getLatestOutput: { type: Function, default: null },
  historyNav: { type: Function, default: null },
  getNodeDisplayName: { type: Function, default: null },
})

const emit = defineEmits(['selectAgent', 'sendInput', 'complete', 'openCompletions', 'activePetChange'])

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

// ===== 节点与连线（参考大屏「网络拓扑」风格）=====
// 节点状态配色（与大屏 TopologyOverlay 保持一致）
const NODE_COLORS = { online: '#34d99b', offline: '#ff5d6c', unknown: '#8a9bb0' }
const AGENT_COLORS = { running: '#20c8ff', waiting: '#ffb347', idle: '#8a9bb0', stopped: '#ff5d6c' }

function nodeColor(state) {
  if (state === 'online') return NODE_COLORS.online
  if (state === 'offline') return NODE_COLORS.offline
  return NODE_COLORS.unknown
}
function agentColor(state) {
  return AGENT_COLORS[state] || AGENT_COLORS.idle
}

// 节点在大厅中的坐标：master 居中，其余节点均匀分布在圆周上
const nodeLayout = computed(() => {
  const list = Array.isArray(props.nodes) ? props.nodes : []
  const w = stageSize.value.w
  const h = stageSize.value.h
  const cx = w / 2
  const cy = h / 2
  // 圆周半径：随舞台尺寸自适应，留出边距
  const radius = Math.max(Math.min(w, h) * 0.32, 120)
  const result = new Map()
  const master = list.find(n => n && n.node_id === 'master')
  if (master) {
    result.set('master', { node_id: 'master', x: cx, y: cy })
  }
  const others = list.filter(n => n && n.node_id && n.node_id !== 'master')
  const count = others.length
  others.forEach((n, i) => {
    // 从正上方开始，顺时针均匀分布
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(count, 1)
    result.set(n.node_id, {
      node_id: n.node_id,
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    })
  })
  return result
})

// 节点列表（带坐标、状态、配色、机箱尺寸），供模板渲染
const nodeItems = computed(() => {
  const list = Array.isArray(props.nodes) ? props.nodes : []
  const agentList = Array.isArray(props.agents) ? props.agents : []
  return list
    .filter(n => n && n.node_id && nodeLayout.value.has(n.node_id))
    .map(n => {
      const pos = nodeLayout.value.get(n.node_id)
      const state = normalizeNodeStatus(n.status)
      const isMaster = n.node_id === 'master'
      const color = isMaster && state !== 'offline' && state !== 'unknown'
        ? '#ffd75e'
        : nodeColor(state)
      const name = props.getNodeDisplayName
        ? props.getNodeDisplayName(n.node_id)
        : (isMaster ? 'master' : n.node_id)
      const short = (() => {
        const s = String(name || '')
        if (s === 'master') return 'master'
        return s.length > 10 ? s.slice(0, 9) + '…' : s
      })()
      // 该节点上的 agent 数（不含已停止）
      const agentCount = agentList.filter(a => {
        const nid = String(a?.node_id || '').trim() || 'master'
        return nid === n.node_id && a.status !== 'stopped'
      }).length
      // 机箱尺寸：master 略大
      const rw = isMaster ? 38 : 30
      const rh = isMaster ? 33 : 26
      return {
        node_id: n.node_id,
        x: pos.x,
        y: pos.y,
        state,
        color,
        isMaster,
        short,
        agentCount,
        rw,
        rh,
        fill: state === 'offline'
          ? 'rgba(255,93,108,0.10)'
          : (isMaster ? 'url(#lobby-center-fill)' : 'rgba(8,18,30,0.7)'),
      }
    })
})

// 节点间连线：master → 其余节点
const nodeLinks = computed(() => {
  const links = []
  const master = nodeLayout.value.get('master')
  if (!master) return links
  const stateById = new Map(nodeItems.value.map(n => [n.node_id, n.state]))
  for (const [id, pos] of nodeLayout.value) {
    if (id === 'master') continue
    links.push({
      key: `node-${id}`,
      x1: master.x,
      y1: master.y,
      x2: pos.x,
      y2: pos.y,
      offline: stateById.get(id) === 'offline',
    })
  }
  return links
})

// 节点间连线：按圆周顺序把相邻子节点连成环（子节点 ↔ 子节点）
const peerLinks = computed(() => {
  const pts = nodeItems.value.filter(n => !n.isMaster)
  if (pts.length < 2) return []
  return pts.map((n, i) => {
    const next = pts[(i + 1) % pts.length]
    return {
      key: `${n.node_id}-${next.node_id}`,
      x1: n.x,
      y1: n.y,
      x2: next.x,
      y2: next.y,
      offline: n.state === 'offline' || next.state === 'offline',
    }
  })
})

// Agent 与所属节点的连线：宠物中心 → 节点坐标（颜色取 agent 状态色）
const agentLinks = computed(() => {
  const links = []
  for (const pet of petAgents.value) {
    const agent = (props.agents || []).find(a => a.agent_id === pet.agentId)
    const nodeId = String(agent?.node_id || '').trim() || 'master'
    const pos = nodeLayout.value.get(nodeId)
    if (!pos) continue
    const state = normalizeAgentStatus(props.getStatusClass ? props.getStatusClass(agent) : '')
    links.push({
      key: `agent-${pet.agentId}`,
      x1: pet.x + PET_W / 2,
      y1: pet.y + PET_H / 2,
      x2: pos.x,
      y2: pos.y,
      color: agentColor(state),
    })
  }
  return links
})

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
  // 触摸/笔：阻止浏览器接管手势（滚动、缩放），否则 pointermove 会被 pointercancel 打断
  if (event.pointerType && event.pointerType !== 'mouse') {
    event.preventDefault()
  }
  const rect = stage.getBoundingClientRect()
  dragState = {
    pet,
    startX: event.clientX,
    startY: event.clientY,
    offsetX: event.clientX - rect.left - pet.x,
    offsetY: event.clientY - rect.top - pet.y,
    moved: false,
    rect,
    pointerId: event.pointerId,
    target: event.currentTarget,
  }
  // 捕获指针：手指移出宠物元素后仍能持续收到 pointermove，移动端拖动更顺畅
  if (event.pointerId !== undefined && event.currentTarget && event.currentTarget.setPointerCapture) {
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch (e) {
      /* 忽略不支持捕获的场景 */
    }
  }
  window.addEventListener('pointermove', onPetPointerMove)
  window.addEventListener('pointerup', onPetPointerUp)
  window.addEventListener('pointercancel', onPetPointerCancel)
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
  // 触摸拖动时阻止页面滚动
  if (event.cancelable && event.pointerType && event.pointerType !== 'mouse') {
    event.preventDefault()
  }
}

function releasePointerCapture() {
  if (!dragState) return
  const { pointerId, target } = dragState
  if (pointerId !== undefined && target && target.releasePointerCapture) {
    try {
      target.releasePointerCapture(pointerId)
    } catch (e) {
      /* 已释放或未捕获时忽略 */
    }
  }
}

function onPetPointerUp() {
  window.removeEventListener('pointermove', onPetPointerMove)
  window.removeEventListener('pointerup', onPetPointerUp)
  window.removeEventListener('pointercancel', onPetPointerCancel)
  if (!dragState) return
  const { pet, moved } = dragState
  releasePointerCapture()
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

// 指针被浏览器取消（如触摸被系统手势抢占）时，安全复位，避免 dragState 悬挂
function onPetPointerCancel() {
  window.removeEventListener('pointermove', onPetPointerMove)
  window.removeEventListener('pointerup', onPetPointerUp)
  window.removeEventListener('pointercancel', onPetPointerCancel)
  if (!dragState) return
  const { pet } = dragState
  releasePointerCapture()
  dragState = null
  if (pet.dragging) {
    pet.dragging = false
    pet.target = pickTarget()
  }
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

// 选中的宠物变化时通知父组件（用于「当前 Agent」相关菜单）
// immediate: 组件挂载时同步一次（清空父组件中可能残留的旧选中态）
watch(activePetId, (id) => {
  emit('activePetChange', id || null)
}, { immediate: true })

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

/* 节点与连线层：位于地板之上、宠物之下，不拦截交互 */
.pet-lobby-topology {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  /* 主角是 Agent：整体弱化节点与连线，避免喧宾夺主 */
  opacity: 0.4;
}

.pet-lobby-links {
  position: absolute;
  left: 0;
  top: 0;
  overflow: visible;
}

.lobby-link {
  stroke-linecap: round;
}

.lobby-link.is-flow {
  stroke-dasharray: 8 6;
  animation: lobby-flow 1.2s linear infinite;
}

@keyframes lobby-flow {
  to { stroke-dashoffset: -14; }
}

/* 节点：服务器机箱造型（参考大屏拓扑，但整体弱化以突出 Agent） */
.lobby-node-body {
  transition: filter 0.15s ease;
}

.lobby-node-led {
  filter: drop-shadow(0 0 2px currentColor);
  animation: lobby-led-blink 2.2s ease-in-out infinite;
}

@keyframes lobby-led-blink {
  0%, 100% { opacity: 0.7; }
  50% { opacity: 0.25; }
}

.lobby-node-label {
  font-size: 11px;
  fill: rgba(180, 220, 240, 0.55);
  pointer-events: none;
}

.lobby-node-count {
  font-size: 10px;
  fill: rgba(150, 190, 210, 0.45);
  pointer-events: none;
}

.lobby-node.is-center .lobby-node-label {
  fill: rgba(255, 232, 154, 0.7);
}

.lobby-node.is-center .lobby-node-count {
  fill: rgba(255, 232, 154, 0.6);
  opacity: 0.9;
}

/* 地板上的 Slogan：刻在地面、经年磨损的沧桑质感 */
.pet-lobby-slogan {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%) perspective(600px) rotateX(52deg);
  transform-origin: center center;
  pointer-events: none;
  user-select: none;
  z-index: 1;
  opacity: 0.5;
}

.pet-lobby-slogan-text {
  display: block;
  font-size: clamp(28px, 5.2vw, 72px);
  font-weight: 800;
  letter-spacing: 0.22em;
  white-space: nowrap;
  /* 文字本体：低对比的灰蓝，像被岁月磨淡的刻痕 */
  color: rgba(120, 160, 190, 0.32);
  /* 上方高光 + 下方阴影，营造凹陷雕刻感 */
  text-shadow:
    0 1px 0 rgba(0, 0, 0, 0.55),
    0 -1px 1px rgba(150, 200, 230, 0.12),
    0 0 18px rgba(32, 200, 255, 0.08);
  /* 用噪点/划痕遮罩制造斑驳脱落 */
  -webkit-mask-image:
    repeating-linear-gradient(96deg, #000 0 3px, rgba(0,0,0,0.35) 3px 5px, #000 5px 11px),
    radial-gradient(ellipse 140% 90% at 42% 46%, #000 30%, rgba(0,0,0,0.25) 62%, transparent 88%);
  -webkit-mask-composite: source-in;
  mask-image:
    repeating-linear-gradient(96deg, #000 0 3px, rgba(0,0,0,0.35) 3px 5px, #000 5px 11px),
    radial-gradient(ellipse 140% 90% at 42% 46%, #000 30%, rgba(0,0,0,0.25) 62%, transparent 88%);
  mask-composite: intersect;
  animation: lobbySloganWeather 9s ease-in-out infinite alternate;
}

/* 沧桑感：明暗与磨损缓慢呼吸，仿佛光影掠过旧地砖 */
@keyframes lobbySloganWeather {
  from {
    opacity: 0.72;
    text-shadow:
      0 1px 0 rgba(0, 0, 0, 0.55),
      0 -1px 1px rgba(150, 200, 230, 0.12),
      0 0 18px rgba(32, 200, 255, 0.08);
  }
  to {
    opacity: 1;
    text-shadow:
      0 1px 0 rgba(0, 0, 0, 0.7),
      0 -1px 1px rgba(150, 200, 230, 0.2),
      0 0 26px rgba(32, 200, 255, 0.14);
  }
}

/* 叠加一层极淡的划痕/污渍纹理，强化做旧痕迹 */
.pet-lobby-slogan::after {
  content: '';
  position: absolute;
  inset: -10% -6%;
  background:
    repeating-linear-gradient(78deg, transparent 0 6px, rgba(0, 0, 0, 0.18) 6px 7px, transparent 7px 15px),
    repeating-linear-gradient(-64deg, transparent 0 9px, rgba(180, 210, 230, 0.06) 9px 10px, transparent 10px 22px);
  mix-blend-mode: overlay;
  pointer-events: none;
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
  /* 移动端：禁用浏览器默认触摸手势（滚动/缩放），否则拖动会被系统手势打断 */
  touch-action: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
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

/* ===== 按状态区分宠物形象 ===== */

/* 运行中：蓝色、尾巴轻摇、常态呼吸 */
.lobby-pet.status-running .lobby-pet-head {
  background: linear-gradient(160deg, #2ee6ff 0%, #1a9fd6 55%, #0e6f9e 100%);
}

/* 等待多行输入：琥珀色、耳朵竖起、眼睛睁大、光晕脉冲 */
.lobby-pet.status-waiting_multi .lobby-pet-head {
  background: linear-gradient(160deg, #ffd479 0%, #f2a52c 55%, #b76a0a 100%);
  box-shadow: 0 0 14px rgba(255, 171, 61, 0.7), inset 0 -3px 6px rgba(0, 0, 0, 0.25),
    inset 0 2px 4px rgba(255, 255, 255, 0.22);
  animation: lobbyPetWaitGlow 1.6s ease-in-out infinite;
}
.lobby-pet.status-waiting_multi .lobby-pet-ear {
  border-bottom-color: #f2a52c;
  filter: drop-shadow(0 0 4px rgba(255, 171, 61, 0.7));
}
.lobby-pet.status-waiting_multi .lobby-pet-ear.l { transform: rotate(-4deg); }
.lobby-pet.status-waiting_multi .lobby-pet-ear.r { transform: rotate(4deg); }
.lobby-pet.status-waiting_multi .lobby-pet-eye {
  width: 8px;
  height: 9px;
  animation: none;
}
.lobby-pet.status-waiting_multi .lobby-pet-tail {
  border-color: #f2a52c transparent transparent transparent;
  filter: drop-shadow(0 0 4px rgba(255, 171, 61, 0.6));
  animation-duration: 0.9s;
}
.lobby-pet.status-waiting_multi .lobby-pet-mouth {
  width: 8px;
  height: 7px;
  border: 1.5px solid rgba(6, 19, 31, 0.75);
  border-radius: 50%;
}

/* 等待确认（单行/确认）：橙红、耳朵笔直、眼睛圆睁、脉冲更急促 */
.lobby-pet.status-waiting_single .lobby-pet-head,
.lobby-pet.status-waiting_confirm .lobby-pet-head {
  background: linear-gradient(160deg, #ff9d6b 0%, #f2603a 55%, #a82f14 100%);
  box-shadow: 0 0 16px rgba(255, 110, 70, 0.75), inset 0 -3px 6px rgba(0, 0, 0, 0.25),
    inset 0 2px 4px rgba(255, 255, 255, 0.22);
  animation: lobbyPetWaitGlow 1s ease-in-out infinite;
}
.lobby-pet.status-waiting_single .lobby-pet-ear,
.lobby-pet.status-waiting_confirm .lobby-pet-ear {
  border-bottom-color: #f2603a;
  filter: drop-shadow(0 0 4px rgba(255, 110, 70, 0.75));
}
.lobby-pet.status-waiting_single .lobby-pet-ear.l,
.lobby-pet.status-waiting_confirm .lobby-pet-ear.l { transform: rotate(0deg); }
.lobby-pet.status-waiting_single .lobby-pet-ear.r,
.lobby-pet.status-waiting_confirm .lobby-pet-ear.r { transform: rotate(0deg); }
.lobby-pet.status-waiting_single .lobby-pet-eye,
.lobby-pet.status-waiting_confirm .lobby-pet-eye {
  width: 9px;
  height: 10px;
  animation: none;
}
.lobby-pet.status-waiting_single .lobby-pet-pupil,
.lobby-pet.status-waiting_confirm .lobby-pet-pupil {
  width: 4px;
  height: 4px;
}
.lobby-pet.status-waiting_single .lobby-pet-tail,
.lobby-pet.status-waiting_confirm .lobby-pet-tail {
  border-color: #f2603a transparent transparent transparent;
  filter: drop-shadow(0 0 4px rgba(255, 110, 70, 0.65));
  animation-duration: 0.7s;
}
.lobby-pet.status-waiting_single .lobby-pet-mouth,
.lobby-pet.status-waiting_confirm .lobby-pet-mouth {
  width: 9px;
  height: 8px;
  border: 1.5px solid rgba(6, 19, 31, 0.8);
  border-radius: 50%;
}

/* 已停止：灰蓝、眼睛闭合、尾巴静止（通常不显示，保留兜底） */
.lobby-pet.status-stopped .lobby-pet-head {
  background: linear-gradient(160deg, #8fa4b5 0%, #6b8299 55%, #47596b 100%);
  box-shadow: 0 0 6px rgba(120, 150, 175, 0.3), inset 0 -3px 6px rgba(0, 0, 0, 0.3);
}
.lobby-pet.status-stopped .lobby-pet-ear {
  border-bottom-color: #6b8299;
  filter: none;
}
.lobby-pet.status-stopped .lobby-pet-eye {
  height: 2px;
  border-radius: 2px;
  background: #06131f;
  animation: none;
}
.lobby-pet.status-stopped .lobby-pet-pupil { display: none; }
.lobby-pet.status-stopped .lobby-pet-tail {
  border-color: #6b8299 transparent transparent transparent;
  filter: none;
  animation: none;
}
.lobby-pet.status-stopped .lobby-pet-body { animation: none; }

@keyframes lobbyPetWaitGlow {
  0%, 100% { filter: brightness(1); }
  50% { filter: brightness(1.25); }
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
  /* 面板内允许纵向触摸滚动（宠物本体已设 touch-action:none，需在此恢复） */
  touch-action: pan-y;
}

/* 输出气泡（markdown） */
.lobby-pet-output {
  width: 100%;
  box-sizing: border-box;
  min-height: 120px;
  max-height: 60vh;
  overflow-y: auto;
  touch-action: pan-y;
  font-size: 13px;
  line-height: 1.6;
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
  font-size: 11px;
}
.lobby-pet-output :deep(code) { font-family: 'Consolas', monospace; }
.lobby-pet-output :deep(ul), .lobby-pet-output :deep(ol) { margin: 6px 0; padding-left: 20px; }
.lobby-pet-output :deep(a) { color: #7ee7ff; }
.lobby-pet-output :deep(h1), .lobby-pet-output :deep(h2), .lobby-pet-output :deep(h3) { margin: 6px 0; font-size: 13px; }

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
  /* 输入框内恢复触摸选择/滚动（宠物本体已设 touch-action:none） */
  touch-action: auto;
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
