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
          @contextmenu.prevent.stop="onNodeContextMenu(n, $event)"
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

    <!-- 右上角：游走开关 + 精灵显示模式开关 -->
    <div class="pet-lobby-toggles">
      <button
        class="pet-lobby-roam-toggle"
        :class="{ off: !roaming }"
        :title="roaming ? '点击停止宠物游走' : '点击开启宠物游走'"
        @click.stop="roaming = !roaming"
      >
        <span class="pet-lobby-roam-icon">{{ roaming ? '🔄' : '⏸' }}</span>
        <span class="pet-lobby-roam-label">{{ roaming ? '游走中' : '已静止' }}</span>
      </button>

      <!-- 精灵显示模式开关（全部 / 仅隐藏输出 / 隐藏全部） -->
      <button
        class="pet-lobby-display-toggle"
        :class="{ off: displayMode !== 'all' }"
        :title="displayModeMeta.title"
        @click.stop="cycleDisplayMode()"
      >
        <span class="pet-lobby-display-icon">{{ displayModeMeta.icon }}</span>
        <span class="pet-lobby-display-label">{{ displayModeMeta.label }}</span>
      </button>
    </div>

    <!-- 无 Agent 提示 -->
    <div v-if="petAgents.length === 0" class="pet-lobby-empty">
      <div class="pet-lobby-empty-title">JARVIS</div>
      <p class="pet-lobby-empty-hint">按 <kbd>Ctrl</kbd>+<kbd>P</kbd> 打开命令面板，或从侧边栏创建一个 Agent</p>
    </div>

    <!-- 宠物群 -->
    <div
      v-for="pet in petAgents"
      v-show="showPets"
      :key="pet.agentId"
      class="lobby-pet"
      :class="[pet.classes, { dragging: pet.dragging, dimmed: activePetId && activePetId !== pet.agentId, 'is-code-agent': pet.agentType === 'code_agent' }]"
      :style="{ left: pet.x + 'px', top: pet.y + 'px' }"
      @pointerdown="onPetPointerDown(pet, $event)"
      @dblclick="onPetDblClick(pet)"
      @contextmenu.prevent.stop="onPetContextMenu(pet, $event)"
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
      <div class="lobby-pet-name"><span class="lobby-pet-type">{{ pet.agentType === 'code_agent' ? '💻' : '🤖' }}</span>{{ pet.name }}</div>
      <div class="lobby-pet-status" :class="pet.statusClass"></div>

      <!-- 输出气泡 + 输入/确认控件：堆叠在宠物下方 -->
      <div
        v-show="showOutput || pet.active || pet.inputMode === 'confirm'"
        class="lobby-pet-stack"
        :class="{ 'stack-above': pet.panelAbove }"
        :style="{ left: pet.stackLeft + 'px', width: pet.stackWidth + 'px', maxHeight: pet.stackMaxH + 'px' }"
        @pointerdown.stop
        @click.stop
        @dblclick.stop
      >
        <!-- 输出气泡：常驻显示（markdown 渲染）；点击气泡同样激活该 Agent -->
        <div v-if="pet.output && !isOutputHidden(pet.agentId)" class="lobby-pet-output-wrap">
          <div
            class="lobby-pet-output"
            :data-pet-output="pet.agentId"
            v-html="pet.output"
            @click.stop="onPetClick(pet)"
            @scroll="onOutputScroll(pet, $event)"
          ></div>
          <button
            class="lobby-pet-copy"
            :class="{ copied: pet.copied }"
            :title="pet.copied ? '已复制' : '复制输出'"
            @click.stop="copyPetOutput(pet)"
          >{{ pet.copied ? '✓' : '⧉' }}</button>
        </div>

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

    <!-- 右键菜单：宠物（对当前 Agent 的操作）/ 节点（节点操作） -->
    <div
      v-if="contextMenu.visible"
      class="lobby-context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @pointerdown.stop
      @click.stop
      @contextmenu.prevent.stop
    >
      <div class="lobby-context-title">{{ contextMenu.name }}</div>
      <div class="lobby-context-items">
        <button
          v-for="act in contextMenuActions"
          :key="act.id"
          class="lobby-context-item"
          :disabled="act.enabled === false"
          @click="onContextAction(act)"
        >
          <span class="lobby-context-icon">{{ act.icon }}</span>
          <span class="lobby-context-label">{{ act.label }}</span>
        </button>
      </div>
    </div>

    <!-- 节点重命名弹层：确定后同步到设置中的节点名称映射 -->
    <div
      v-if="renameDialog.visible"
      class="lobby-rename-mask"
      @pointerdown.stop
      @click.stop="closeRenameDialog"
    >
      <div class="lobby-rename-dialog" @click.stop>
        <div class="lobby-rename-title">重命名节点</div>
        <div class="lobby-rename-sub">{{ renameDialog.nodeId }}</div>
        <input
          ref="renameInputRef"
          class="lobby-rename-input"
          type="text"
          placeholder="输入显示名称（留空恢复为节点 ID）"
          v-model="renameDialog.value"
          @keydown.enter.prevent="confirmRename"
          @keydown.esc.prevent="closeRenameDialog"
        />
        <div class="lobby-rename-actions">
          <button class="lobby-rename-btn cancel" @click="closeRenameDialog">取消</button>
          <button class="lobby-rename-btn ok" @click="confirmRename">确定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { normalizeNodeStatus, normalizeAgentStatus } from './topology.js'

const props = defineProps({
  agents: { type: Array, default: () => [] },
  nodes: { type: Array, default: () => [] },
  getStatusClass: { type: Function, default: null },
  getInputState: { type: Function, default: null },
  getLatestOutput: { type: Function, default: null },
  historyNav: { type: Function, default: null },
  getNodeDisplayName: { type: Function, default: null },
  // 右键菜单动作（复用命令面板「当前 Agent」组），由父组件按当前 Agent 计算后传入
  contextActions: { type: Array, default: () => [] },
  // 节点右键菜单动作，由父组件传入（便于后续扩展更多节点功能）
  nodeActions: { type: Array, default: () => [] },
})

const emit = defineEmits(['selectAgent', 'sendInput', 'complete', 'openCompletions', 'activePetChange', 'createAgentOnNode', 'contextAgent', 'contextRun', 'nodeContextRun', 'renameNode'])

// 宠物尺寸常量（与 CSS 中的 .lobby-pet 宽高保持一致）
const PET_W = 72
const PET_H = 82
const PET_SPEED = 0.55 // 像素/帧，约 33px/秒
const MIN_DIST = 96 // 宠物之间最小间距，用于斥力避让
const EDGE_PAD = 12
const PANEL_H = 150 // 交互面板高度（粗略值，用于判断面板朝上/朝下）
const STACK_GAP = 4 // 堆叠容器与宠物本体的间距（与 CSS 的 calc(100% + 4px) 一致）

const stageRef = ref(null)
const stageSize = ref({ w: 0, h: 0 })
const petAgents = ref([])
const activePetId = ref(null)
const roaming = ref(true) // 是否允许宠物自由游走

// 精灵显示模式：all=全部显示 / no-output=仅隐藏输出 / hidden=隐藏输出与精灵
// 用于精灵过多时降低资源消耗、保持界面整洁；持久化到 localStorage
const DISPLAY_MODE_KEY = 'jarvis.petLobby.displayMode'
const DISPLAY_MODES = ['all', 'no-output', 'hidden']
function loadDisplayMode() {
  try {
    const saved = localStorage.getItem(DISPLAY_MODE_KEY)
    if (DISPLAY_MODES.includes(saved)) return saved
  } catch (e) {
    /* localStorage 不可用时回退默认值 */
  }
  return 'all'
}
const displayMode = ref(loadDisplayMode())
const showPets = computed(() => displayMode.value !== 'hidden')
const showOutput = computed(() => displayMode.value === 'all')
watch(displayMode, (mode) => {
  try {
    localStorage.setItem(DISPLAY_MODE_KEY, mode)
  } catch (e) {
    /* 忽略写入失败（隐私模式等） */
  }
})
// 循环切换：全部 → 仅隐藏输出 → 隐藏全部 → 全部
function cycleDisplayMode() {
  const idx = DISPLAY_MODES.indexOf(displayMode.value)
  displayMode.value = DISPLAY_MODES[(idx + 1) % DISPLAY_MODES.length]
}
const displayModeMeta = computed(() => {
  if (displayMode.value === 'no-output') return { icon: '💬', label: '仅隐藏输出', title: '当前：仅隐藏输出气泡，点击切换为隐藏全部精灵' }
  if (displayMode.value === 'hidden') return { icon: '🙈', label: '隐藏全部', title: '当前：已隐藏输出与精灵，点击切换为全部显示' }
  return { icon: '👁', label: '全部显示', title: '当前：显示全部，点击切换为仅隐藏输出' }
})

// 单个 Agent 的输出显隐：与全局 displayMode 叠加，独立控制并持久化
const HIDDEN_OUTPUTS_KEY = 'jarvis.petLobby.hiddenOutputs'
function loadHiddenOutputs() {
  try {
    const raw = localStorage.getItem(HIDDEN_OUTPUTS_KEY)
    const arr = raw ? JSON.parse(raw) : []
    if (Array.isArray(arr)) return new Set(arr.filter(id => typeof id === 'string'))
  } catch (e) {
    /* localStorage 不可用或数据损坏时回退空集 */
  }
  return new Set()
}
const hiddenOutputIds = ref(loadHiddenOutputs())
// 曾经出现过的 agentId：用于判断哪些持久化项对应的 Agent 已被删除
const seenAgentIds = new Set()
function saveHiddenOutputs() {
  try {
    localStorage.setItem(HIDDEN_OUTPUTS_KEY, JSON.stringify([...hiddenOutputIds.value]))
  } catch (e) {
    /* 忽略写入失败（隐私模式等） */
  }
}
// 某 Agent 的输出是否被单独隐藏
function isOutputHidden(agentId) {
  return hiddenOutputIds.value.has(agentId)
}
// 切换某 Agent 的输出显隐（供命令面板/右键菜单调用）
function toggleAgentOutput(agentId) {
  if (!agentId) return
  const next = new Set(hiddenOutputIds.value)
  if (next.has(agentId)) next.delete(agentId)
  else next.add(agentId)
  hiddenOutputIds.value = next
  saveHiddenOutputs()
}

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

// Agent 与所属节点的连线：宠物中心 → 节点坐标（颜色取 agent 状态色）
const agentLinks = computed(() => {
  const links = []
  // 精灵隐藏时不绘制 agent→节点连线
  if (!showPets.value) return links
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

// 复制某只宠物的输出内容（取渲染后的纯文本）
async function copyPetOutput(pet) {
  if (!pet || !pet.output) return
  const holder = document.createElement('div')
  holder.innerHTML = pet.output
  const text = (holder.textContent || '').trim()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch (err) {
    try {
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.opacity = '0'
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
    } catch (fallbackErr) {
      console.error('[PET-COPY] 复制失败:', fallbackErr)
      return
    }
  }
  pet.copied = true
  if (pet.copyTimer) clearTimeout(pet.copyTimer)
  pet.copyTimer = setTimeout(() => { pet.copied = false }, 1200)
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
  const nextOutput = latest ? latest.html : ''
  const outputChanged = nextOutput !== pet.output
  pet.output = nextOutput
  layoutPetStack(pet)
  // 流式输出：内容更新后若用户未上滚，自动滚到底部
  if (outputChanged && pet.outputAutoScroll) {
    scrollOutputToBottom(pet.agentId)
  }
}

// 输出滚动到底部（等待 DOM 更新后执行）
function scrollOutputToBottom(agentId) {
  nextTick(() => {
    const el = stageRef.value && stageRef.value.querySelector(`[data-pet-output="${agentId}"]`)
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 用户手动滚动输出框：接近底部时恢复自动滚动，否则暂停（避免打断用户查看历史）
function onOutputScroll(pet, event) {
  const el = event.target
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24
  pet.outputAutoScroll = atBottom
}

// 计算堆叠容器（输出/输入/确认）的位置与尺寸，确保始终落在舞台可视范围内
// 水平：以宠物中心对齐，并夹取到舞台左右边界内
// 垂直：优先放下方，下方空间不足则放上方，并限制最大高度避免溢出
function layoutPetStack(pet) {
  if (!pet) return
  const w = stageSize.value.w
  const h = stageSize.value.h
  if (!w || !h) return
  // 宽度与 CSS 的 min(560px, 62vw) 对齐，且不超出舞台可用宽度
  const width = Math.max(160, Math.min(560, w * 0.62, w - EDGE_PAD * 2))
  pet.stackWidth = width
  // 水平：理想居中于宠物，夹取到 [EDGE_PAD, w - width - EDGE_PAD]
  const cx = pet.x + PET_W / 2
  const idealLeft = cx - width / 2
  const clampedLeft = Math.min(Math.max(idealLeft, EDGE_PAD), Math.max(w - width - EDGE_PAD, EDGE_PAD))
  // left 相对宠物左上角（stack 为 absolute，父级是宠物）
  pet.stackLeft = clampedLeft - pet.x
  // 垂直：下方 / 上方可用空间
  const belowSpace = h - (pet.y + PET_H + STACK_GAP)
  const aboveSpace = pet.y - STACK_GAP
  const useAbove = belowSpace < PANEL_H && aboveSpace > belowSpace
  pet.panelAbove = useAbove
  const avail = Math.max(useAbove ? aboveSpace : belowSpace, 120)
  pet.stackMaxH = Math.min(avail, h - EDGE_PAD * 2)
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
        agentType: agent.agent_type || 'agent',
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
        stackLeft: 0,
        stackWidth: 0,
        stackMaxH: 0,
        outputAutoScroll: true,
        copied: false,
        copyTimer: null,
      }
    } else {
      pet.name = agent.name || agent.agent_id
      pet.agentType = agent.agent_type || 'agent'
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
  // 清理已被删除 Agent 的输出隐藏持久化数据（stopped 仍存在，不清理）
  // 仅在拿到过非空 agent 列表后才清理，避免初始加载（列表暂为空）时误删
  if (list.length > 0) {
    for (const a of list) {
      if (a && a.agent_id) seenAgentIds.add(a.agent_id)
    }
    let hiddenChanged = false
    const pruned = new Set()
    for (const id of hiddenOutputIds.value) {
      if (seenAgentIds.has(id)) pruned.add(id)
      else hiddenChanged = true
    }
    if (hiddenChanged) {
      hiddenOutputIds.value = pruned
      saveHiddenOutputs()
    }
  }
}

// 单帧：所有宠物向各自目标点移动，并做斥力避让
function step() {
  const pets = petAgents.value
  // 精灵隐藏时不渲染也不移动，直接跳过全部计算，降低资源消耗
  if (!showPets.value) {
    rafId = requestAnimationFrame(step)
    return
  }
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
  // 舞台尺寸变化后重算堆叠容器位置，避免输入/输出框溢出可视范围
  for (const pet of petAgents.value) layoutPetStack(pet)
}

// 点击大厅空白处：取消所有宠物的选中/展开状态，让它们恢复飘动
function onStageClick(event) {
  // 点击任意处都先关闭右键菜单
  closeContextMenu()
  // 仅当点击目标是舞台本身（空白区域）时才处理；宠物及其面板已 stop 冒泡
  if (event.target !== stageRef.value) return
  for (const pet of petAgents.value) {
    if (pet.active) closePanel(pet)
  }
}

// ===== 右键菜单（宠物 / 节点共用） =====
// 菜单状态：坐标相对舞台左上角；kind 区分来源；name 用于标题
const contextMenu = ref({ visible: false, x: 0, y: 0, kind: 'pet', agentId: null, nodeId: null, name: '' })

// 节点菜单内置动作：在节点上创建 Agent（后续可在此追加更多节点功能）
const NODE_MENU_ACTIONS = [
  { id: 'node-create-agent', icon: '➕', label: '创建 Agent' },
  { id: 'node-open-terminal', icon: '⌨️', label: '打开终端' },
  { id: 'node-rename', icon: '✏️', label: '重命名' },
]
const nodeMenuActions = computed(() => {
  const extra = props.nodeActions || []
  return [...NODE_MENU_ACTIONS, ...extra]
})

// 当前菜单项：按 kind 取对应来源
const contextMenuActions = computed(() =>
  contextMenu.value.kind === 'node' ? nodeMenuActions.value : (props.contextActions || [])
)

function closeContextMenu() {
  if (contextMenu.value.visible) contextMenu.value.visible = false
}

// 估算菜单尺寸并做边界钳制，避免超出舞台（两列布局，宽度与 CSS min-width 对齐）
function placeContextMenu(event, itemCount) {
  const stage = stageRef.value
  if (!stage) return null
  const rect = stage.getBoundingClientRect()
  const MENU_W = 320
  const rows = Math.max(1, Math.ceil(itemCount / 2))
  const MENU_H = Math.min(44 + rows * 33, rect.height * 0.6)
  let x = event.clientX - rect.left
  let y = event.clientY - rect.top
  if (x + MENU_W > rect.width) x = Math.max(rect.width - MENU_W, 0)
  if (y + MENU_H > rect.height) y = Math.max(rect.height - MENU_H, 0)
  return { x, y }
}

// 在宠物上右键：通知父组件切换当前 Agent 并准备动作，再就地弹出菜单
function onPetContextMenu(pet, event) {
  if (!pet) return
  // 取消待执行的单击判定：避免右键后 250ms 误触发 onPetClick 而改变选中状态
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  // 先请求父组件把「当前 Agent」切到该宠物（决定菜单动作与可用性）
  emit('contextAgent', pet.agentId)
  const pos = placeContextMenu(event, (props.contextActions || []).length)
  if (!pos) return
  contextMenu.value = {
    visible: true,
    x: pos.x,
    y: pos.y,
    kind: 'pet',
    agentId: pet.agentId,
    nodeId: null,
    name: pet.name || pet.agentId,
  }
}

// 在节点上右键：弹出节点操作菜单
function onNodeContextMenu(node, event) {
  if (!node) return
  const pos = placeContextMenu(event, nodeMenuActions.value.length)
  if (!pos) return
  contextMenu.value = {
    visible: true,
    x: pos.x,
    y: pos.y,
    kind: 'node',
    agentId: null,
    nodeId: node.node_id,
    name: node.short || node.node_id,
  }
}

// ===== 节点重命名弹层 =====
// 确定后 emit('renameNode', { nodeId, name })，由父组件写入设置中的节点名称映射
const renameDialog = ref({ visible: false, nodeId: '', value: '' })
const renameInputRef = ref(null)

function openRenameDialog(nodeId, currentName) {
  if (!nodeId) return
  renameDialog.value = {
    visible: true,
    nodeId,
    value: currentName && currentName !== nodeId ? currentName : '',
  }
  nextTick(() => {
    const el = renameInputRef.value
    if (el) {
      el.focus()
      el.select()
    }
  })
}

function closeRenameDialog() {
  if (renameDialog.value.visible) renameDialog.value.visible = false
}

function confirmRename() {
  const nodeId = renameDialog.value.nodeId
  const name = String(renameDialog.value.value || '').trim()
  if (nodeId) emit('renameNode', { nodeId, name })
  closeRenameDialog()
}

// 点击菜单项：按菜单来源分派给父组件执行，然后关闭菜单
function onContextAction(act) {
  if (!act || act.enabled === false) return
  if (contextMenu.value.kind === 'node') {
    if (act.id === 'node-rename') {
      // 重命名在大厅内弹输入框，不走父组件的节点动作分发
      openRenameDialog(contextMenu.value.nodeId, contextMenu.value.name)
    } else {
      emit('nodeContextRun', { action: act, nodeId: contextMenu.value.nodeId })
    }
  } else {
    emit('contextRun', act)
  }
  closeContextMenu()
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
  // 拖动过程中同步重算堆叠容器位置，保证输入/输出框始终在可视范围内
  layoutPetStack(pet)
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
// 语义为「总是选中并展开」；取消选中只通过点击舞台空白处（onStageClick）
let clickTimer = null
function onPetClick(pet) {
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  clickTimer = setTimeout(() => {
    clickTimer = null
    if (activePetId.value === pet.agentId && pet.active) return
    openPanel(pet)
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
  // 精灵隐藏时无需刷新任何宠物数据
  if (!showPets.value) return
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
      // 仅隐藏输出/隐藏全部时，跳过较重的输出（markdown）刷新；
      // 但已激活（展开交互面板）的宠物仍需刷新，保证其输出面板实时更新
      if (showOutput.value || pet.active) {
        refreshPetData(pet)
      } else {
        layoutPetStack(pet)
      }
    }
  }
}

onMounted(() => {
  measureStage()
  syncPets()
  rafId = requestAnimationFrame(step)
  refreshTimer = setInterval(refreshLoop, 800)
  window.addEventListener('keydown', onGlobalKeydown)
  window.addEventListener('resize', closeContextMenu)
  window.addEventListener('blur', closeContextMenu)
  if (typeof ResizeObserver !== 'undefined' && stageRef.value) {
    resizeObserver = new ResizeObserver(() => measureStage())
    resizeObserver.observe(stageRef.value)
  }
})

// 全局按键：Esc 关闭右键菜单与重命名弹层
function onGlobalKeydown(e) {
  if (e.key === 'Escape') {
    closeContextMenu()
    closeRenameDialog()
  }
}

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = null
  window.removeEventListener('pointermove', onPetPointerMove)
  window.removeEventListener('pointerup', onPetPointerUp)
  window.removeEventListener('keydown', onGlobalKeydown)
  window.removeEventListener('resize', closeContextMenu)
  window.removeEventListener('blur', closeContextMenu)
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

defineExpose({ insertCompletionText, toggleAgentOutput, isOutputHidden })
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
.lobby-node {
  /* 容器层整体 pointer-events: none（不拦截宠物交互），此处单独恢复节点可点击 */
  pointer-events: auto;
  cursor: pointer;
  /* 禁用双击时的默认选中高亮 */
  user-select: none;
  -webkit-user-select: none;
}
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

/* ===== 右上角开关组（游走 + 精灵显示模式） ===== */
.pet-lobby-toggles {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 8px;
}
.pet-lobby-roam-toggle,
.pet-lobby-display-toggle {
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
.pet-lobby-roam-toggle:hover,
.pet-lobby-display-toggle:hover {
  background: rgba(16, 40, 60, 0.95);
  border-color: rgba(32, 200, 255, 0.75);
}
.pet-lobby-roam-toggle.off,
.pet-lobby-display-toggle.off {
  color: #9fb4c4;
  border-color: rgba(120, 140, 160, 0.45);
}
.pet-lobby-roam-icon,
.pet-lobby-display-icon {
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

/* 类型图标：CodeAgent 💻 / 普通 Agent 🤖，与侧边栏列表保持一致 */
.lobby-pet-type {
  margin-right: 3px;
  font-size: 10px;
  line-height: 1;
  opacity: 0.9;
}

/* CodeAgent 的轻量区分：名字偏青绿 + 头顶一圈淡光环（不喧宾夺主） */
.lobby-pet.is-code-agent .lobby-pet-name {
  color: rgba(150, 240, 220, 0.92);
}
.lobby-pet.is-code-agent .lobby-pet-head {
  box-shadow: 0 0 10px rgba(46, 230, 200, 0.5), inset 0 -3px 6px rgba(0, 0, 0, 0.25),
    inset 0 2px 4px rgba(255, 255, 255, 0.18);
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
/* left / width / max-height 由 JS（layoutPetStack）动态计算，确保始终落在舞台可视范围内 */
.lobby-pet-stack {
  position: absolute;
  top: calc(100% + 4px);
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: default;
  z-index: 6;
  overflow-y: auto;
  overflow-x: hidden;
  touch-action: pan-y;
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
.lobby-pet-output-wrap {
  position: relative;
  width: 100%;
}
.lobby-pet-copy {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  font-size: 12px;
  line-height: 1;
  color: #9fd8ef;
  background: rgba(10, 24, 38, 0.85);
  border: 1px solid rgba(32, 200, 255, 0.35);
  border-radius: 6px;
  cursor: pointer;
  opacity: 0.35;
  transition: opacity 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.lobby-pet-output-wrap:hover .lobby-pet-copy {
  opacity: 1;
}
.lobby-pet-copy:hover {
  color: #dff1fb;
  border-color: rgba(32, 200, 255, 0.7);
}
.lobby-pet-copy.copied {
  opacity: 1;
  color: #34d99b;
  border-color: rgba(52, 217, 155, 0.7);
}
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
  padding: 10px 32px 10px 12px;
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
/* Agent 右键菜单：对当前 Agent 的操作 */
.lobby-context-menu {
  position: absolute;
  z-index: 60;
  min-width: 300px;
  max-width: 380px;
  max-height: 60vh;
  overflow-y: auto;
  padding: 4px;
  border-radius: 10px;
  background: rgba(12, 22, 34, 0.96);
  border: 1px solid rgba(32, 200, 255, 0.35);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.lobby-context-title {
  padding: 6px 10px 8px;
  font-size: 12px;
  font-weight: 600;
  color: #9fe4ff;
  border-bottom: 1px solid rgba(32, 200, 255, 0.18);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 菜单项两列排布，避免一列过长 */
.lobby-context-items {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px;
}
.lobby-context-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: #d7e8f5;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.lobby-context-item:hover:not(:disabled) {
  background: rgba(32, 200, 255, 0.16);
}
.lobby-context-item:disabled {
  opacity: 0.4;
  cursor: default;
}
.lobby-context-icon {
  width: 18px;
  text-align: center;
}
.lobby-context-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 节点重命名弹层 */
.lobby-rename-mask {
  position: absolute;
  inset: 0;
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(4, 10, 18, 0.55);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}
.lobby-rename-dialog {
  width: min(360px, 86vw);
  padding: 16px;
  border-radius: 12px;
  background: rgba(12, 22, 34, 0.98);
  border: 1px solid rgba(32, 200, 255, 0.35);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55);
}
.lobby-rename-title {
  font-size: 14px;
  font-weight: 600;
  color: #9fe4ff;
}
.lobby-rename-sub {
  margin-top: 4px;
  font-size: 12px;
  color: #7f93a6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.lobby-rename-input {
  width: 100%;
  margin-top: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(32, 200, 255, 0.3);
  background: rgba(6, 14, 24, 0.9);
  color: #d7e8f5;
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.lobby-rename-input:focus {
  border-color: rgba(32, 200, 255, 0.7);
}
.lobby-rename-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.lobby-rename-btn {
  padding: 6px 16px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 13px;
  cursor: pointer;
}
.lobby-rename-btn.cancel {
  background: transparent;
  border-color: rgba(255, 255, 255, 0.18);
  color: #b6c6d4;
}
.lobby-rename-btn.cancel:hover {
  background: rgba(255, 255, 255, 0.08);
}
.lobby-rename-btn.ok {
  background: rgba(32, 200, 255, 0.9);
  color: #04121c;
  font-weight: 600;
}
.lobby-rename-btn.ok:hover {
  background: rgba(32, 200, 255, 1);
}

</style>
