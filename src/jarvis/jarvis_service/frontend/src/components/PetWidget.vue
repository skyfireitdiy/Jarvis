<template>
  <!-- 宠物挂件：浮动于页面，可拖拽并记忆位置 -->
  <Teleport to="body">
    <div
      v-show="petVisible"
      class="pet-float"
      :class="petClasses"
      :style="{ left: petPos.x + 'px', top: petPos.y + 'px' }"
      aria-hidden="true"
      @contextmenu.prevent
    >
      <div class="pet-inner">
        <div class="pet-glow"></div>
        <div class="pet-rune-ring" aria-hidden="true">
          <div class="pet-rune-orbit">
            <span
              v-for="(b, i) in petRuneBits"
              :key="i"
              class="pet-rune-bit"
              :style="petRuneBitStyle(i)"
            ><span class="pet-rune-glyph">{{ b }}</span></span>
          </div>
          <div class="pet-rune-core"></div>
        </div>
        <div class="pet-bubble">{{ petBubbleText }}</div>
        <div class="pet-body">
          <div class="pet-head" :style="petHeadStyle">
            <div class="pet-ear l"></div>
            <div class="pet-ear r"></div>
            <div class="pet-eye l"><div class="pet-pupil" :style="petPupilStyle"></div></div>
            <div class="pet-eye r"><div class="pet-pupil" :style="petPupilStyle"></div></div>
            <div class="pet-mouth"></div>
          </div>
          <div class="pet-tail"></div>
        </div>
        <div class="pet-shadow"></div>
        <div class="pet-spark s1"></div>
        <div class="pet-spark s2"></div>
        <div class="pet-spark s3"></div>
        <div class="pet-orbit orbit-a" aria-hidden="true">
          <div class="pet-orbit-track">
            <span class="pet-orbit-mote"></span>
            <span class="pet-orbit-mote"></span>
            <span class="pet-orbit-mote"></span>
          </div>
        </div>
        <div class="pet-orbit orbit-b" aria-hidden="true">
          <div class="pet-orbit-track">
            <span class="pet-orbit-rune">✦</span>
            <span class="pet-orbit-rune">✧</span>
            <span class="pet-orbit-rune">✶</span>
          </div>
        </div>
        <div class="pet-zzz z1">z</div>
        <div class="pet-zzz z2">z</div>
        <div class="pet-zzz z3">Z</div>
        <div
          v-if="petBadgeText"
          class="pet-badge"
          :class="{ 'is-alert': petWaitingAgents.length > 0, 'is-clickable': petWaitingAgents.length > 0 }"
          :title="petWaitingAgents.length > 0 ? (petWaitingAgents.length + ' 个 Agent 等待输入，点击跳转到下一个') : (petRunningCount + ' 个 Agent 运行中')"
          @pointerdown.stop
          @click.stop="onPetBadgeClick"
        >{{ petBadgeText }}</div>
        <div class="pet-label">✦ JARVIS ✦</div>
        <button
          class="pet-sfx-btn"
          :class="{ 'is-off': !petSfxOn }"
          :title="petSfxOn ? '关闭宠物音效' : '开启宠物音效'"
          @click.stop="togglePetSfx"
        >{{ petSfxOn ? '🔊' : '🔇' }}</button>
        <button
          class="pet-pin-btn"
          :class="{ 'is-on': petPinned }"
          :title="petPinned ? '取消固定（允许随机移动）' : '固定宠物（禁止随机移动）'"
          @click.stop="togglePetPin"
        >{{ petPinned ? '📌' : '📍' }}</button>
        <button
          class="pet-power-btn"
          :class="{ 'is-on': petPowerSave }"
          :title="petPowerSave ? '关闭省电模式（恢复特效）' : '开启省电模式（关闭特效，降低耗电）'"
          @click.stop="togglePetPowerSave"
        >{{ petPowerSave ? '🔋' : '⚡' }}</button>
        <div
          class="pet-hit"
          @pointerdown="onPetPointerDown"
          @pointermove="onPetPointerMove"
          @pointerup="onPetPointerUp"
          @pointercancel="onPetPointerUp"
          @contextmenu.prevent.stop
          @mouseenter="petHover = true; clearPetEdgeLeaveTimer()"
          @mouseleave="petHover = false"
        ></div>
      </div>
    </div>

    <!-- 贴边收起态：固定在屏幕内侧边缘的唤出触发条（宠物大部分在视口外，靠它接收鼠标移入）。
         独立于 .pet-float 定位（position:fixed），不随宠物滑入/滑出动画移动，
         否则动画期间触发条会跟着宠物跑出屏幕，导致鼠标反复 enter/leave 而抖动。
         展开态的收回改由 document 的 mousemove 判定（见 onPetMouseMove），
         避免宠物热区在动画中扫过鼠标位置抢走 hover 而反复抖动 -->
    <div
      v-show="petEdge && !petEdgeRevealed && petVisible"
      class="pet-edge-trigger"
      :class="petEdge === 'left' ? 'is-left' : 'is-right'"
      :style="{ top: petPos.y + 'px', height: petH() + 'px', width: petEdgePeek() + 'px' }"
      @mouseenter="onPetEdgeEnter"
      @pointerdown.stop.prevent="onPetEdgeActivate"
      @click.stop.prevent="onPetEdgeActivate"
    ></div>

    <!-- 宠物旁的迷你网络拓扑（贴边收起态随宠物一起隐藏） -->
    <PetMiniTopology
      v-show="petVisible && petTopoOn && !petPowerSaveActive && (!petEdge || petEdgeRevealed)"
      :nodes="nodes"
      :agents="agentList || []"
      :getStatusClass="getStatusClass"
      :x="petMiniPos.x"
      :y="petMiniPos.y"
      @open="petOpenTopology"
    />
    <!-- 隐藏后的还原按钮 -->
    <button
      v-if="props.isConnected && petHidden"
      class="pet-restore"
      :style="{ left: restorePos.x + 'px', top: restorePos.y + 'px' }"
      title="唤回宠物（可拖动）"
      @pointerdown="onRestorePointerDown"
      @pointermove="onRestorePointerMove"
      @pointerup="onRestorePointerUp"
      @pointercancel="onRestorePointerUp"
      @contextmenu.prevent.stop
    >🐾</button>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import PetMiniTopology from './PetMiniTopology.vue'

const props = defineProps({
  isConnected: { type: Boolean, default: true },
  windowWidth: Number,
  agentList: Array,
  agentStatuses: Map,
  isWaitingInput: Function,
  currentAgentId: String,
  nodes: { type: Array, default: () => [] },
  getStatusClass: Function,
})
const emit = defineEmits([
  'petSyncStatus',
  'petInterruptCurrent',
  'petGotoWaiting',
  'petToggleSidebar',
  'petOpenTopology',
  'petOpenCommandPalette',
])

// ==================== 宠物挂件 ====================
const PET_POS_KEY = 'jarvis_pet_pos'
const PET_TOPO_KEY = 'jarvis_pet_topo'
const PET_RESTORE_POS_KEY = 'jarvis_pet_restore_pos'
const PET_HIDDEN_KEY = 'jarvis_pet_hidden'
const PET_POWER_SAVE_KEY = 'jarvis_pet_power_save'
const PET_PIN_KEY = 'jarvis_pet_pinned'
const PET_EDGE_KEY = 'jarvis_pet_edge'
// 贴边判定阈值：拖拽结束时距屏幕左右边缘小于该值即吸附
const PET_EDGE_SNAP = 24
// 贴边收起后仍露出的宽度（像素）：保证收起态仍能看到宠物一角，便于定位
const PET_EDGE_PEEK_DESKTOP = 28
const PET_EDGE_PEEK_MOBILE = 40
// 鼠标移出后延迟收回的时长（毫秒）：避免在触发条与宠物之间移动时来回抖动
const PET_EDGE_LEAVE_DELAY = 160
// 移动端宠物整体缩小一半（配合 .pet-float 的 scale(0.5)），此处返回视觉尺寸
const PET_SCALE_MOBILE = 0.5
const PET_W = 200
const PET_H = 230
const RESTORE_W = 40
const RESTORE_H = 40
// 宠物视觉尺寸：移动端为桌面端的一半（与 CSS 缩放保持一致）
function petW() {
  return isMobileView.value ? Math.round(PET_W * PET_SCALE_MOBILE) : PET_W
}
function petH() {
  return isMobileView.value ? Math.round(PET_H * PET_SCALE_MOBILE) : PET_H
}
// 贴边收起后露出的宽度：移动端宠物被 scale(0.5) 缩小，需给更大的原始值才能露出可辨识的一角
function petEdgePeek() {
  return isMobileView.value ? PET_EDGE_PEEK_MOBILE : PET_EDGE_PEEK_DESKTOP
}
const petPos = ref({ x: 0, y: 0 })
const restorePos = ref({ x: 0, y: 0 })
const petHover = ref(false)
const petDrag = ref(false)
const petJump = ref(false)
const petAction = ref('')
const petPupil = ref({ x: 0, y: 0 })
const petTilt = ref(0)
const petFaceDir = ref(1)   // 朝向：1 向右，-1 向左
// 丰富交互新增状态
const petSleep = ref(false)      // 打盹中
const petPetting = ref(false)    // 摸头中
const petHidden = ref(false)     // 已隐藏
const petWalking = ref(false)    // 随机漫步中
const petSpeech = ref('')        // 随机台词
const petTopoOn = ref(true)      // 是否显示迷你拓扑图
const petCast = ref('')          // 正在施放的法术类型（'' 表示未施法）
const petPowerSave = ref(false)  // 省电模式：关闭一切装饰性特效与常驻运算（移动端/桌面端均可开启）
const petPinned = ref(false)     // 固定宠物：禁止随机漫步（不影响其它交互）
// 贴边隐藏：'left' | 'right' | null；非 null 表示已吸附到该侧并收起
const petEdge = ref(null)
// 贴边收起态下是否临时滑出（鼠标移入时展开）
const petEdgeRevealed = ref(false)
// 贴边态鼠标移出后的延时收回定时器
let petEdgeLeaveTimer = 0

// 是否处于移动端（用于宠物整体缩放等，不再限制省电模式开关）
const isMobileView = computed(() => (props.windowWidth || window.innerWidth) <= 768)
// 省电模式生效中：开关打开即生效（移动端与桌面端均可用）
const petPowerSaveActive = computed(() => petPowerSave.value)

// 头顶数字法环：一圈 0/1 灵符，玄幻风格，随状态联动
const PET_RUNE_COUNT = 18
const PET_RUNE_RADIUS = 62
const petRuneBits = Array.from({ length: PET_RUNE_COUNT }, (_, i) =>
  (i * 7 + 3) % 3 === 0 ? '1' : '0'
)
function petRuneBitStyle(i) {
  const step = 360 / PET_RUNE_COUNT
  const angle = i * step
  // 每个字符随机相位/时长，形成灵光闪烁的错落感
  const delay = ((i * 37) % 100) / 100 * 2.4
  const dur = 1.8 + ((i * 53) % 100) / 100 * 1.6
  return {
    transform: `rotate(${angle}deg) translateY(-${PET_RUNE_RADIUS}px)`,
    '--rune-glow-delay': delay.toFixed(2) + 's',
    '--rune-glow-dur': dur.toFixed(2) + 's',
  }
}

// 未连接（如登录界面）时不显示宠物及其附属 UI
const petVisible = computed(() => props.isConnected && !petHidden.value)

// 随机台词库
const PET_LINES = [
  '你好呀~',
  '今天也要加油鸭！',
  '需要帮忙吗？',
  '我在这儿陪着你~',
  '记得休息一下哦',
  '嘿嘿，被你摸到了',
  '有新的任务吗？',
  '我一直都在呢 ✦',
]

// 鼓励语库：定时随机显示，替代原先常驻的「需要输入」提示
const PET_ENCOURAGE_LINES = [
  '加油，你可以的！',
  '慢慢来，不着急~',
  '你已经很棒啦 ✦',
  '再坚持一下下！',
  '喝口水休息会儿吧',
  '有我在，别担心~',
  '今天也辛苦啦',
  '一切都会好起来的',
  '深呼吸，继续加油！',
  '你的努力我都看在眼里',
  '别给自己太大压力哦',
  '冲鸭！我陪着你 ✦',
]

// 宠物状态：waiting（有 Agent 等待输入）| running（有 Agent 运行中）| idle
const petState = computed(() => {
  const list = props.agentList || []
  if (list.some(a => props.isWaitingInput && props.isWaitingInput(a))) return 'waiting'
  const statuses = props.agentStatuses
  if (statuses && list.some(a => {
    const st = statuses.get(a.agent_id)
    return st && (st.execution_status === 'running' || st.execution_status === 'executing')
  })) return 'running'
  return 'idle'
})

// 气泡文本：仅显示临时台词（等待输入不再常驻显示）
const petBubbleText = computed(() => {
  return petSpeech.value
})

// ==================== 网关操作：宠物状态聚合 ====================
// 等待输入的 Agent 列表
const petWaitingAgents = computed(() =>
  (props.agentList || []).filter(a => props.isWaitingInput && props.isWaitingInput(a))
)

// 运行中的 Agent 数量
const petRunningCount = computed(() => {
  const list = props.agentList || []
  const statuses = props.agentStatuses
  if (!statuses) return 0
  return list.filter(a => {
    const st = statuses.get(a.agent_id)
    return st && (st.execution_status === 'running' || st.execution_status === 'executing')
  }).length
})

// 徽标文本：优先显示等待数，其次显示运行数
const petBadgeText = computed(() => {
  if (petWaitingAgents.value.length > 0) return String(petWaitingAgents.value.length)
  if (petRunningCount.value > 0) return String(petRunningCount.value)
  return ''
})

// 点击头顶徽标：跳转到下一个等待输入的 Agent（由父组件负责循环切换）
function onPetBadgeClick() {
  if (petWaitingAgents.value.length === 0) return
  emit('petGotoWaiting')
}

// 当前施放法术的类别（array/throw/beam/swarm），用于区分特效与状态类
const PET_CAST_KINDS = {
  thunder: 'array', flame: 'array', frost: 'array', star: 'array',
  rune: 'throw', bolt: 'beam', sword: 'beam', swarm: 'swarm',
}
const petCastKind = computed(() => PET_CAST_KINDS[petCast.value] || '')

const petClasses = computed(() => [
  'is-' + petState.value,
  {
    'is-hover': petHover.value,
    'is-drag': petDrag.value,
    'is-jump': petJump.value,
    'is-speak': !!petSpeech.value,
    'is-sleep': petSleep.value,
    'is-petting': petPetting.value,
    'is-walk': petWalking.value,
    'face-left': petFaceDir.value < 0,
    'rune-running': petState.value === 'running',
    'rune-waiting': petWaitingAgents.length > 0,
    'rune-sleep': petSleep.value,
    // is-casting 仅用于「法阵类」法术，避免覆盖 act-throw 等其它法术的动画
    'is-casting': petCastKind.value === 'array',
    'power-save': petPowerSaveActive.value,
    'pet-compact': isMobileView.value,
  },
  petAction.value ? 'act-' + petAction.value : '',
  petCast.value ? 'cast-' + petCast.value : '',
])
// 是否正在看迷你拓扑图（开着且宠物可见/清醒；省电模式下不显示，避免常驻渲染）
const petWatchingTopo = computed(() => petTopoOn.value && !petPowerSaveActive.value && !petHidden.value && !petSleep.value)

// 迷你图水平方向相对宠物中心的偏移：-1 左 / 0 中 / 1 右
const petTopoDirX = computed(() => {
  const headCx = petPos.value.x + petW() / 2
  const topoCx = petMiniPos.value.x + 48
  const d = topoCx - headCx
  if (d > 8) return 1
  if (d < -8) return -1
  return 0
})

// 实际瞳孔偏移：看迷你图时抬头向上看（朝其方向），否则跟随鼠标
const petEffectivePupil = computed(() => {
  if (petWatchingTopo.value && !petHover.value && !petDrag.value) {
    return { x: petTopoDirX.value * 3, y: -4 }
  }
  return petPupil.value
})

const petPupilStyle = computed(() => ({
  transform: `translate(calc(-50% + ${petEffectivePupil.value.x}px), calc(-50% + ${petEffectivePupil.value.y}px))`,
}))

// 迷你拓扑位置：放在宠物头顶前方（不遮挡宠物身体），空间不足时回退到下方/侧边，并限制在视口内
const petMiniPos = computed(() => {
  const MINI = 96
  const vw = window.innerWidth
  const vh = window.innerHeight
  const maxX = Math.max(4, vw - MINI - 4)
  const maxY = Math.max(4, vh - MINI - 4)
  const clampX = (x) => Math.max(4, Math.min(maxX, x))
  const clampY = (y) => Math.max(4, Math.min(maxY, y))

  // 首选：宠物头顶上方居中（宠物抬头看向它）
  const topX = petPos.value.x + petW() / 2 - MINI / 2
  const topY = petPos.value.y - MINI - 6
  if (topY >= 4) return { x: clampX(topX), y: topY }

  // 回退1：宠物下方居中
  const belowY = petPos.value.y + petH() + 6
  if (belowY <= maxY) return { x: clampX(topX), y: belowY }

  // 回退2：宠物右侧
  const sideX = petPos.value.x + petW() + 6
  const sideY = petPos.value.y + petH() / 2 - MINI / 2
  if (sideX <= maxX) return { x: sideX, y: clampY(sideY) }

  // 最终：宠物左侧
  return { x: clampX(petPos.value.x - MINI - 6), y: clampY(sideY) }
})

const petHeadStyle = computed(() => {
  if (petHover.value || petDrag.value) return {}
  // 看迷你拓扑图时：抬头（轻微上移）并偏向迷你图一侧
  if (petWatchingTopo.value) {
    const tilt = petTopoDirX.value * 4
    return { transform: `translateX(-50%) translateY(-3px) rotate(${tilt}deg)` }
  }
  return { transform: `translateX(-50%) rotate(${petTilt.value}deg)` }
})

function clampPetPos(x, y) {
  const maxX = Math.max(0, window.innerWidth - petW())
  const maxY = Math.max(0, window.innerHeight - petH())
  return { x: Math.max(0, Math.min(maxX, x)), y: Math.max(0, Math.min(maxY, y)) }
}

// ==================== 贴边隐藏 ====================
// 贴边收起时宠物左上角的 x：左侧露右边一小条，右侧露左边一小条
function petEdgeCollapsedX(edge) {
  return edge === 'left' ? -(petW() - petEdgePeek()) : window.innerWidth - petEdgePeek()
}

// 贴边展开时宠物左上角的 x：完全贴到该侧边缘
function petEdgeExpandedX(edge) {
  return edge === 'left' ? 0 : Math.max(0, window.innerWidth - petW())
}

// 依据贴边状态与是否临时滑出，更新宠物 x（贴边态不走 clamp，允许越出视口）
function applyPetEdge() {
  if (!petEdge.value) return
  const x = petEdgeRevealed.value
    ? petEdgeExpandedX(petEdge.value)
    : petEdgeCollapsedX(petEdge.value)
  petPos.value = { x, y: petPos.value.y }
}

// 拖拽结束：贴近左右边缘则吸附并收起，否则取消贴边
function snapPetToEdge() {
  const x = petPos.value.x
  const maxX = Math.max(0, window.innerWidth - petW())
  const nearLeft = x <= PET_EDGE_SNAP
  const nearRight = x >= maxX - PET_EDGE_SNAP
  if (nearLeft || nearRight) {
    petEdge.value = nearLeft ? 'left' : 'right'
    petEdgeRevealed.value = false
    applyPetEdge()
  } else {
    petEdge.value = null
    petEdgeRevealed.value = false
  }
  savePetEdge()
}

// 鼠标移入：贴边态临时滑出，便于交互
function onPetEdgeEnter() {
  if (!petEdge.value || petEdgeRevealed.value) return
  clearPetEdgeLeaveTimer()
  petEdgeRevealed.value = true
  applyPetEdge()
}

// 点击/触摸触发条：把宠物完整唤回屏幕内（彻底解除贴边）。
// 桌面端鼠标移入触发条时 onPetEdgeEnter 已让其临时滑出，此时点击同样解除贴边，
// 避免「滑出后又被 mousemove 判定收回」的闪回；移动端无 hover，点击直接唤回。
function onPetEdgeActivate() {
  if (!petEdge.value) return
  clearPetEdgeLeaveTimer()
  const edge = petEdge.value
  // 先滑出到该侧边缘，再解除贴边并夹取回可视区，避免位置跳变
  const expandedX = petEdgeExpandedX(edge)
  petEdge.value = null
  petEdgeRevealed.value = false
  petPos.value = clampPetPos(expandedX, petPos.value.y)
  savePetEdge()
  savePetPos()
  petSfxChirp()
}

// 鼠标移出：贴边态滑回收起（延时执行，避免在触发条与宠物之间移动时来回抖动）
function onPetEdgeLeave() {
  if (!petEdge.value || !petEdgeRevealed.value) return
  clearPetEdgeLeaveTimer()
  petEdgeLeaveTimer = window.setTimeout(() => {
    petEdgeLeaveTimer = 0
    if (!petEdge.value || !petEdgeRevealed.value) return
    petEdgeRevealed.value = false
    applyPetEdge()
  }, PET_EDGE_LEAVE_DELAY)
}

function clearPetEdgeLeaveTimer() {
  if (petEdgeLeaveTimer) {
    clearTimeout(petEdgeLeaveTimer)
    petEdgeLeaveTimer = 0
  }
}

function savePetEdge() {
  try {
    localStorage.setItem(PET_EDGE_KEY, petEdge.value || '')
  } catch (e) {
    console.warn('[AGENT_SIDEBAR] Failed to save pet edge:', e)
  }
}

function initPetEdge() {
  let saved = ''
  try {
    saved = localStorage.getItem(PET_EDGE_KEY) || ''
  } catch (e) {
    saved = ''
  }
  if (saved === 'left' || saved === 'right') {
    petEdge.value = saved
    petEdgeRevealed.value = false
    applyPetEdge()
  }
}

// 还原按钮独立于宠物尺寸，可拖到屏幕任意边角
function clampRestorePos(x, y) {
  const maxX = Math.max(0, window.innerWidth - RESTORE_W)
  const maxY = Math.max(0, window.innerHeight - RESTORE_H)
  return { x: Math.max(0, Math.min(maxX, x)), y: Math.max(0, Math.min(maxY, y)) }
}

function saveRestorePos() {
  try {
    localStorage.setItem(PET_RESTORE_POS_KEY, JSON.stringify(restorePos.value))
  } catch (e) {
    console.warn('[AGENT_SIDEBAR] Failed to save pet restore position:', e)
  }
}

function initRestorePos() {
  let saved = null
  try {
    saved = JSON.parse(localStorage.getItem(PET_RESTORE_POS_KEY) || 'null')
  } catch (e) {
    saved = null
  }
  if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
    restorePos.value = clampRestorePos(saved.x, saved.y)
    restoreUserMoved = true
    return
  }
  // 默认与宠物当前位置一致
  restorePos.value = clampRestorePos(petPos.value.x, petPos.value.y)
}

function savePetPos() {
  try {
    localStorage.setItem(PET_POS_KEY, JSON.stringify(petPos.value))
  } catch (e) {
    console.warn('[AGENT_SIDEBAR] Failed to save pet position:', e)
  }
}

function initPetPos() {
  let saved = null
  try {
    saved = JSON.parse(localStorage.getItem(PET_POS_KEY) || 'null')
  } catch (e) {
    saved = null
  }
  if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
    petPos.value = clampPetPos(saved.x, saved.y)
    return
  }
  // 默认位置：侧边栏底部居中
  const sidebar = document.querySelector('.agent-sidebar')
  const rect = sidebar ? sidebar.getBoundingClientRect() : { left: 0, width: 320 }
  petPos.value = clampPetPos(
    rect.left + (rect.width - petW()) / 2,
    window.innerHeight - petH() - 8
  )
}

let petRaf = 0
function onPetMouseMove(e) {
  // 贴边展开态：用鼠标位置判定是否仍在「宠物 ∪ 触发条」范围内，决定收回。
  // 不依赖元素 mouseleave，避免宠物热区在滑出动画中扫过鼠标位置抢走 hover 而反复抖动
  if (petVisible.value && petEdge.value && petEdgeRevealed.value) {
    const f = document.querySelector('.pet-float')
    if (f) {
      const r = f.getBoundingClientRect()
      // 宠物矩形（含收起时露出的部分）与屏幕内侧触发条共同构成"保持展开"区域
      const inPet = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom
      const inTrigger = petEdge.value === 'left'
        ? e.clientX <= petEdgePeek()
        : e.clientX >= window.innerWidth - petEdgePeek()
      if (inPet || inTrigger) clearPetEdgeLeaveTimer()
      else onPetEdgeLeave()
    }
  }
  if (petRaf) return
  petRaf = requestAnimationFrame(() => {
    petRaf = 0
    // 睡眠/隐藏时不跟踪鼠标
    if (petSleep.value || petHidden.value) return
    const head = document.querySelector('.pet-float .pet-head')
    if (!head) return
    const r = head.getBoundingClientRect()
    const cx = r.left + r.width / 2
    const cy = r.top + r.height / 2
    const dx = e.clientX - cx
    const dy = e.clientY - cy
    const d = Math.hypot(dx, dy) || 1
    const max = 4.5
    petPupil.value = {
      x: (dx / d) * Math.min(max, d / 14),
      y: (dy / d) * Math.min(max, d / 14),
    }
    if (!petHover.value && !petDrag.value) {
      petTilt.value = Math.max(-6, Math.min(6, dx / 22))
    }
  })
}

let petDragging = false
let petMoved = false
let petStartX = 0
let petStartY = 0
let petOriginX = 0
let petOriginY = 0

// 交互判定定时器
let petClickTimer = 0    // 单击延迟判定
let petSpeechTimer = 0   // 台词气泡
let petHideTimer = 0     // 隐藏定时器（兼容保留）
let petPettingFxTimer = 0      // 摸头爱心循环

// ==================== 宠物环形菜单 ====================
let petMenuLongPressTimer = 0               // 还原按钮长按判定

function onPetPointerDown(e) {
  if (e.button !== undefined && e.button !== 0) return  // 仅左键
  stopPetWalk()
  petDragging = true
  petMoved = false
  petStartX = e.clientX
  petStartY = e.clientY
  petOriginX = petPos.value.x
  petOriginY = petPos.value.y
  e.target.setPointerCapture?.(e.pointerId)
  e.preventDefault()
}

// 右键：拦截浏览器默认菜单，不做任何响应（技能菜单不再由右键触发）

function onPetPointerMove(e) {
  if (!petDragging) return
  const dx = e.clientX - petStartX
  const dy = e.clientY - petStartY
  if (!petMoved && Math.hypot(dx, dy) > 5) {
    petMoved = true
    petDrag.value = true
    if (petPetting.value) stopPetting()
  }
  if (petMoved) {
    petPos.value = clampPetPos(petOriginX + dx, petOriginY + dy)
  }
}

function onPetPointerUp(e) {
  if (!petDragging) return
  petDragging = false
  e.target.releasePointerCapture?.(e.pointerId)
  if (petMoved) {
    petDrag.value = false
    snapPetToEdge()
    savePetPos()
    return
  }
  petDrag.value = false
  // 单击 / 双击判定
  if (petClickTimer) {
    // 300ms 内第二次：双击 → 撒花庆祝并唤起命令面板（与右键行为互换）
    clearTimeout(petClickTimer)
    petClickTimer = 0
    onPetDoubleClick(e.clientX, e.clientY)
    return
  }
  const cx = e.clientX
  const cy = e.clientY
  petClickTimer = window.setTimeout(() => {
    petClickTimer = 0
    onPetSingleClick(cx, cy)
  }, 300)
}

// 单击：睡眠则唤醒；否则跳跃 + 粒子 + 音效 + 随机台词
function onPetSingleClick(x, y) {
  if (petSleep.value) {
    wakePet()
    return
  }
  petJump.value = true
  setTimeout(() => { petJump.value = false }, 560)
  spawnPetFx(x, y)
  petSfxChirp()
  showPetSpeech()
}

// 双击行为：撒花庆祝，并唤起命令面板
function onPetDoubleClick(x, y) {
  wakePet()
  petJump.value = true
  setTimeout(() => { petJump.value = false }, 560)
  petAction.value = 'cheer'
  setTimeout(() => { if (petAction.value === 'cheer') petAction.value = '' }, 1600)
  spawnPetConfetti(x, y)
  spawnPetFx(x, y)
  petSfxCheer()
  showPetSpeech()
  emit('petOpenCommandPalette')
}

// 随机台词气泡：显示 2s
function showPetSpeech() {
  petSpeech.value = PET_LINES[Math.floor(Math.random() * PET_LINES.length)]
  clearTimeout(petSpeechTimer)
  petSpeechTimer = window.setTimeout(() => { petSpeech.value = '' }, 2000)
}

// 定时随机显示鼓励语（约 20~40s 一次，显示 4s）
let petEncourageTimer = 0
function schedulePetEncourage() {
  clearTimeout(petEncourageTimer)
  petEncourageTimer = window.setTimeout(() => {
    if (!petPowerSaveActive.value && !document.hidden && !petHidden.value && !petSleep.value &&
        !petHover.value && !petDrag.value && !petPetting.value && !petWalking.value) {
      petSpeech.value = PET_ENCOURAGE_LINES[Math.floor(Math.random() * PET_ENCOURAGE_LINES.length)]
      clearTimeout(petSpeechTimer)
      petSpeechTimer = window.setTimeout(() => { petSpeech.value = '' }, 4000)
    }
    schedulePetEncourage()
  }, 20000 + Math.random() * 20000)
}

// 撒花特效
function spawnPetConfetti(x, y) {
  const colors = ['#20c8ff', '#7ee7ff', '#ff8ad8', '#ffd166', '#a78bfa']
  for (let i = 0; i < 14; i++) {
    const el = document.createElement('div')
    el.className = 'pet-confetti'
    el.style.left = x + 'px'
    el.style.top = y + 'px'
    el.style.background = colors[i % colors.length]
    el.style.setProperty('--dx', (Math.random() * 120 - 60) + 'px')
    el.style.setProperty('--dy', (-40 - Math.random() * 70) + 'px')
    el.style.setProperty('--rot', (Math.random() * 540 - 270) + 'deg')
    el.style.animationDelay = (i * 0.02) + 's'
    document.body.appendChild(el)
    setTimeout(() => el.remove(), 1400)
  }
}

// 摸头
function startPetting() {
  wakePet()
  petPetting.value = true
  petSfxPurr()
  spawnPetHearts()
  clearInterval(petPettingFxTimer)
  petPettingFxTimer = window.setInterval(spawnPetHearts, 420)
}

function stopPetting() {
  petPetting.value = false
  clearInterval(petPettingFxTimer)
  petPettingFxTimer = 0
}

// 冒出爱心（基于宠物当前位置）
function spawnPetHearts() {
  const el = document.querySelector('.pet-float')
  const r = el ? el.getBoundingClientRect() : { left: petPos.value.x, top: petPos.value.y, width: petW(), height: petH() }
  const x = r.left + r.width / 2
  const y = r.top + r.height * 0.28
  for (let i = 0; i < 2; i++) {
    const h = document.createElement('div')
    h.className = 'pet-heart-fx'
    h.textContent = Math.random() > 0.5 ? '❤' : '💗'
    h.style.left = (x + (Math.random() * 40 - 20)) + 'px'
    h.style.top = (y + (Math.random() * 16 - 8)) + 'px'
    h.style.setProperty('--dx', (Math.random() * 50 - 25) + 'px')
    document.body.appendChild(h)
    setTimeout(() => h.remove(), 1300)
  }
}

// ==================== 菜单动作 ====================
// 喂食：食物落下 + 咀嚼
function petFeed() {
  wakePet()
  const el = document.querySelector('.pet-float')
  const r = el ? el.getBoundingClientRect() : { left: petPos.value.x, top: petPos.value.y, width: petW(), height: petH() }
  const food = document.createElement('div')
  food.className = 'pet-food'
  food.textContent = '🍖'
  food.style.left = (r.left + r.width / 2) + 'px'
  food.style.top = (r.top + r.height * 0.1) + 'px'
  document.body.appendChild(food)
  setTimeout(() => food.remove(), 900)
  setTimeout(() => {
    petAction.value = 'chomp'
    setTimeout(() => { if (petAction.value === 'chomp') petAction.value = '' }, 1000)
    petSfxChomp()
    spawnPetHearts()
  }, 520)
}

// 玩球：球飞过 + 追逐
function petPlayBall() {
  wakePet()
  const el = document.querySelector('.pet-float')
  const r = el ? el.getBoundingClientRect() : { left: petPos.value.x, top: petPos.value.y, width: petW(), height: petH() }
  const ball = document.createElement('div')
  ball.className = 'pet-ball'
  ball.textContent = '🎾'
  ball.style.left = (r.left - 30) + 'px'
  ball.style.top = (r.top + r.height * 0.62) + 'px'
  ball.style.setProperty('--fly', (r.width + 70) + 'px')
  document.body.appendChild(ball)
  setTimeout(() => ball.remove(), 1500)
  petAction.value = 'chase'
  setTimeout(() => { if (petAction.value === 'chase') petAction.value = '' }, 1400)
  petSfxChirp()
}

// 打盹 / 唤醒
let petSleepTimer = 0   // 睡一会自动醒来的定时器
// 每次入睡随机小睡 20~40 秒后自己醒来
function schedulePetWake() {
  clearTimeout(petSleepTimer)
  petSleepTimer = window.setTimeout(() => {
    petSleepTimer = 0
    if (petSleep.value) wakePet()
  }, 20000 + Math.random() * 20000)
}

// 唤醒（若在睡眠中），并清理自动醒来定时器
function wakePet() {
  clearTimeout(petSleepTimer)
  petSleepTimer = 0
  if (petSleep.value) {
    petSleep.value = false
    petSfxChirp()
  }
}

function togglePetSleep() {
  petSleep.value = !petSleep.value
  if (petSleep.value) {
    petSpeech.value = ''
    petSfxYawn()
    schedulePetWake()
  } else {
    clearTimeout(petSleepTimer)
    petSleepTimer = 0
    petSfxChirp()
  }
}

// 唱歌：音符飘出 + 音阶
function petSing() {
  wakePet()
  const el = document.querySelector('.pet-float')
  const r = el ? el.getBoundingClientRect() : { left: petPos.value.x, top: petPos.value.y, width: petW(), height: petH() }
  const notes = ['♪', '♫', '🎵', '♬']
  for (let i = 0; i < 6; i++) {
    const n = document.createElement('div')
    n.className = 'pet-note'
    n.textContent = notes[i % notes.length]
    n.style.left = (r.left + r.width / 2 + (Math.random() * 50 - 25)) + 'px'
    n.style.top = (r.top + r.height * 0.3) + 'px'
    n.style.setProperty('--dx', (Math.random() * 50 - 25) + 'px')
    n.style.animationDelay = (i * 0.16) + 's'
    document.body.appendChild(n)
    setTimeout(() => n.remove(), 1800)
  }
  petAction.value = 'sing'
  setTimeout(() => { if (petAction.value === 'sing') petAction.value = '' }, 1400)
  petSfxSong()
}

// 隐藏宠物（保持隐藏直到手动唤回；同时停掉相关运算以节省资源）
function petHide() {
  stopPetting()
  // 未手动拖过还原按钮时，让它出现在宠物当前位置，体验连贯
  if (!restoreUserMoved) {
    restorePos.value = clampRestorePos(petPos.value.x, petPos.value.y)
  }
  petHidden.value = true
  try { localStorage.setItem(PET_HIDDEN_KEY, '1') } catch (e) {}
  clearTimeout(petHideTimer)
  stopPetLoops()
}

function showPet() {
  clearTimeout(petHideTimer)
  petHidden.value = false
  try { localStorage.setItem(PET_HIDDEN_KEY, '0') } catch (e) {}
  startPetLoops()
  petSfxChirp()
}

// 切换宠物显示/隐藏（供命令面板等外部调用）
function togglePet() {
  if (petHidden.value) {
    showPet()
  } else {
    petHide()
  }
}

// 还原按钮（🐾）拖动：位置独立于宠物尺寸，可拖到屏幕任意边角
let restoreDragging = false
let restoreMoved = false
let restoreUserMoved = false  // 用户是否手动拖动过还原按钮
let restoreLongPressFired = false  // 本次长按已触发（撒花 + 命令面板）
let restoreClickTimer = 0     // 单击延迟判定（区分单击还原 / 双击撒花+命令面板）
let restoreStartX = 0
let restoreStartY = 0
let restoreOriginX = 0
let restoreOriginY = 0

function onRestorePointerDown(e) {
  if (e.button !== undefined && e.button !== 0) return  // 仅左键
  restoreDragging = true
  restoreMoved = false
  restoreLongPressFired = false
  restoreStartX = e.clientX
  restoreStartY = e.clientY
  restoreOriginX = restorePos.value.x
  restoreOriginY = restorePos.value.y
  e.target.setPointerCapture?.(e.pointerId)
  e.preventDefault()
  // 长按判定：600ms 未移动则撒花庆祝并唤起命令面板（与显示态宠物一致）
  clearTimeout(petMenuLongPressTimer)
  petMenuLongPressTimer = window.setTimeout(() => {
    if (restoreDragging && !restoreMoved) {
      restoreLongPressFired = true
      const r = restoreStageRect()
      onPetDoubleClick(r.left + r.width / 2, r.top + r.height / 2)
    }
  }, 600)
}

// 隐藏态还原按钮（🐾）右键：拦截浏览器默认菜单，不做任何响应

function onRestorePointerMove(e) {
  if (!restoreDragging) return
  const dx = e.clientX - restoreStartX
  const dy = e.clientY - restoreStartY
  if (!restoreMoved && Math.hypot(dx, dy) > 5) {
    restoreMoved = true
    clearTimeout(petMenuLongPressTimer)
  }
  if (restoreMoved) {
    restorePos.value = clampRestorePos(restoreOriginX + dx, restoreOriginY + dy)
  }
}

function onRestorePointerUp(e) {
  if (!restoreDragging) return
  restoreDragging = false
  clearTimeout(petMenuLongPressTimer)
  e.target.releasePointerCapture?.(e.pointerId)
  if (restoreMoved) {
    restoreUserMoved = true
    saveRestorePos()
    return
  }
  // 长按已触发：撒花 + 命令面板已执行，不再触发单击/双击
  if (restoreLongPressFired) {
    restoreLongPressFired = false
    return
  }
  // 单击 / 双击判定（与显示态宠物一致：双击 → 撒花庆祝并唤起命令面板）
  if (restoreClickTimer) {
    clearTimeout(restoreClickTimer)
    restoreClickTimer = 0
    onPetDoubleClick(e.clientX, e.clientY)
    return
  }
  restoreClickTimer = window.setTimeout(() => {
    restoreClickTimer = 0
    showPet()
  }, 300)
}

// ==================== 网关操作 ====================
// 同步所有已连接 Agent 的状态
function petSyncStatus() {
  emit('petSyncStatus')
  petAction.value = 'cheer'
  setTimeout(() => { if (petAction.value === 'cheer') petAction.value = '' }, 1200)
  petSfxChirp()
}

// 中断当前 Agent（人工介入）
function petInterrupt() {
  if (!props.currentAgentId) {
    petSpeech.value = '没有选中的 Agent'
    clearTimeout(petSpeechTimer)
    petSpeechTimer = window.setTimeout(() => { petSpeech.value = '' }, 2000)
    return
  }
  emit('petInterruptCurrent')
  petAction.value = 'chomp'
  setTimeout(() => { if (petAction.value === 'chomp') petAction.value = '' }, 1000)
  petSfxChomp()
}

// 奔赴等待输入的 Agent
function petGotoWaiting() {
  if (petWaitingAgents.value.length === 0) return
  emit('petGotoWaiting')
  petSfxChirp()
}

// 切换侧边栏显示/隐藏
function petToggleSidebar() {
  emit('petToggleSidebar')
}

// 打开网络拓扑大图
function petOpenTopology() {
  emit('petOpenTopology')
  petSfxChirp()
}


function spawnPetFx(x, y) {
  const icons = ['❤', '✨', '★', '💫', '✦']
  for (let i = 0; i < 4; i++) {
    const el = document.createElement('div')
    el.className = 'pet-fx'
    el.textContent = icons[Math.floor(Math.random() * icons.length)]
    el.style.left = (x + (Math.random() * 36 - 18)) + 'px'
    el.style.top = (y + (Math.random() * 14 - 7)) + 'px'
    el.style.color = Math.random() > 0.5 ? '#7ee7ff' : '#ff8ad8'
    el.style.setProperty('--rot', (Math.random() * 60 - 30) + 'deg')
    el.style.animationDelay = (i * 0.06) + 's'
    document.body.appendChild(el)
    setTimeout(() => el.remove(), 1400)
  }
}

// ==================== 玄幻法术特效 ====================
// kind: array=脚下法阵 | throw=抛出头顶法环 | beam=远程灵光 | swarm=万剑归宗
const PET_SPELLS = [
  { key: 'thunder', kind: 'array', glyphs: ['⚡', '雷', '✦'], color: '#9fd8ff', glow: '#5db2ff' },
  { key: 'flame',   kind: 'array', glyphs: ['🔥', '炎', '✷'], color: '#ffb066', glow: '#ff7a2f' },
  { key: 'frost',   kind: 'array', glyphs: ['❄', '冰', '✳'], color: '#bff2ff', glow: '#6fe3ff' },
  { key: 'star',    kind: 'array', glyphs: ['✨', '星', '✴'], color: '#ffe6a8', glow: '#ffd166' },
  { key: 'rune',    kind: 'throw' },                          // 抛出头顶数字光环
  { key: 'bolt',    kind: 'beam', color: '#9fd8ff', glow: '#5db2ff' },  // 远程：雷光箭
  { key: 'sword',   kind: 'beam', color: '#c8e6ff', glow: '#7aa8ff' },  // 远程：御剑
  { key: 'swarm',   kind: 'swarm', color: '#cfe8ff', glow: '#6f9dff' }, // 万剑归宗：随机曲线飞散后归巢
]

// 宠物本体（含头顶法环）的屏幕矩形，兜底用宠物位置
function petStageRect() {
  const el = document.querySelector('.pet-float')
  return el
    ? el.getBoundingClientRect()
    : { left: petPos.value.x, top: petPos.value.y, width: petW(), height: petH() }
}

// 隐藏后 🐾 还原按钮的屏幕矩形，兜底用还原按钮位置
function restoreStageRect() {
  const el = document.querySelector('.pet-restore')
  return el
    ? el.getBoundingClientRect()
    : { left: restorePos.value.x, top: restorePos.value.y, width: 32, height: 32 }
}

// 抛出头顶法环：复用现有的 throw 动作与 pet-rune-throw 动画
function petCastRuneThrow() {
  petAction.value = 'throw'
  petSfxAction('throw')
  setTimeout(() => { if (petAction.value === 'throw') petAction.value = '' }, 2600)
}

// 远程释放：从宠物朝随机方向射出一道灵光，抵达后爆开
function petCastBeam(spell) {
  const r = petStageRect()
  const ox = r.left + r.width / 2
  const oy = r.top + r.height * 0.4
  // 随机瞄准屏幕内任一点（含四角），保证能打到全屏范围
  const tx = Math.random() * window.innerWidth
  const ty = Math.random() * window.innerHeight
  const dx = tx - ox
  const dy = ty - oy
  const dist = Math.hypot(dx, dy) || 1
  const angle = Math.atan2(dy, dx) * 180 / Math.PI
  // 时长随距离增长（越远飞越久），并保证足够慢以看清轨迹
  const dur = Math.max(0.75, Math.min(1.8, dist / 900))

  // 光束
  const beam = document.createElement('div')
  beam.className = 'pet-spell-beam'
  beam.style.left = ox + 'px'
  beam.style.top = oy + 'px'
  beam.style.width = dist + 'px'
  beam.style.transform = `rotate(${angle}deg)`
  beam.style.setProperty('--spell-color', spell.color)
  beam.style.setProperty('--spell-glow', spell.glow)
  beam.style.setProperty('--beam-dur', dur + 's')
  document.body.appendChild(beam)
  setTimeout(() => beam.remove(), (dur + 0.5) * 1000)

  // 飞行灵符
  const bolt = document.createElement('div')
  bolt.className = 'pet-spell-bolt'
  bolt.textContent = '✦'
  bolt.style.left = ox + 'px'
  bolt.style.top = oy + 'px'
  bolt.style.color = spell.color
  bolt.style.textShadow = `0 0 10px ${spell.glow}, 0 0 20px ${spell.glow}`
  bolt.style.setProperty('--bx', dx + 'px')
  bolt.style.setProperty('--by', dy + 'px')
  bolt.style.setProperty('--beam-dur', dur + 's')
  document.body.appendChild(bolt)
  setTimeout(() => bolt.remove(), (dur + 0.5) * 1000)

  // 命中爆点
  const hit = document.createElement('div')
  hit.className = 'pet-spell-hit'
  hit.style.left = tx + 'px'
  hit.style.top = ty + 'px'
  hit.style.borderColor = spell.glow
  hit.style.boxShadow = `0 0 26px ${spell.glow}, inset 0 0 26px ${spell.glow}`
  hit.style.animationDelay = dur + 's'
  document.body.appendChild(hit)
  setTimeout(() => hit.remove(), (dur + 0.9) * 1000)
}
// 万剑归宗：一群飞剑沿随机曲线向外刺出，划弧后全部归拢回宠物本体
function petCastSwarm(spell) {
  const r = petStageRect()
  const ox = r.left + r.width / 2
  const oy = r.top + r.height * 0.42
  // 剑出鞘要先「蓄势」：宠物本体抖一下
  petAction.value = 'throw'
  setTimeout(() => { if (petAction.value === 'throw') petAction.value = '' }, 900)

  const N = 9
  const maxR = Math.min(window.innerWidth, window.innerHeight) * 0.62
  for (let i = 0; i < N; i++) {
    const sword = document.createElement('div')
    sword.className = 'pet-spell-sword'
    sword.innerHTML = '<i class="pet-sword-blade"></i><i class="pet-sword-hilt"></i>'
    sword.style.left = ox + 'px'
    sword.style.top = oy + 'px'
    sword.style.color = spell.color
    sword.style.setProperty('--spell-glow', spell.glow)

    // 目标点：以随机角度、随机距离飞散，使每把剑路径都不同
    const a = (i / N) * Math.PI * 2 + (Math.random() - 0.5) * 0.7
    const reach = maxR * (0.75 + Math.random() * 0.4)
    const dx = Math.cos(a) * reach
    const dy = Math.sin(a) * reach - maxR * 0.18   // 略偏上，像腾空
    // 控制点：垂直于主轴方向偏移，形成弯月般的曲线去程（系数放大以飞得更远）
    const c1x = dx * 0.8 + -dy * (0.35 + Math.random() * 0.4)
    const c1y = dy * 0.8 + dx * (0.35 + Math.random() * 0.4)
    // 控制点 2：返程回弯
    const c2x = dx * 0.9 - dy * 0.75
    const c2y = dy * 0.9 + dx * 0.75

    // offset-path 的 path() 无法在 CSS 里解析 var()，故在 JS 侧拼好完整路径字符串
    sword.style.setProperty('--sw-path',
      `path('M 0 0 C ${c1x.toFixed(0)} ${c1y.toFixed(0)}, ${c2x.toFixed(0)} ${c2y.toFixed(0)}, 0 0')`)
    sword.style.setProperty('--sw-dur', (1.7 + Math.random() * 0.5).toFixed(2) + 's')
    sword.style.animationDelay = (i * 0.06 + Math.random() * 0.05).toFixed(2) + 's'
    document.body.appendChild(sword)
    setTimeout(() => sword.remove(), 3200)
  }

  // 剑阵起势：脚下浮现一圈剑意灵光
  const sigil = document.createElement('div')
  sigil.className = 'pet-spell-swarm-sigil'
  sigil.style.left = ox + 'px'
  sigil.style.top = (r.top + r.height - 26) + 'px'
  sigil.style.borderColor = spell.glow
  sigil.style.boxShadow = `0 0 18px ${spell.glow}, inset 0 0 18px ${spell.glow}`
  document.body.appendChild(sigil)
  setTimeout(() => sigil.remove(), 3400)

  // 归位瞬间的中心聚光
  const core = document.createElement('div')
  core.className = 'pet-spell-swarm-core'
  core.style.left = ox + 'px'
  core.style.top = oy + 'px'
  core.style.background = `radial-gradient(circle, #ffffff 0%, ${spell.color} 40%, transparent 72%)`
  core.style.boxShadow = `0 0 42px ${spell.glow}`
  core.style.animationDelay = '1.55s'
  document.body.appendChild(core)
  setTimeout(() => core.remove(), 2700)
}

// 施放一波法术：在宠物脚下展开一座旋转的灵光法阵
function petCastSpell(spell) {
  const r = petStageRect()
  const cx = r.left + r.width / 2
  const cy = r.top + r.height - 34   // 法阵落在宠物脚下

  const array = document.createElement('div')
  array.className = 'pet-spell-array'
  array.style.left = cx + 'px'
  array.style.top = cy + 'px'
  array.style.setProperty('--spell-color', spell.color)
  array.style.setProperty('--spell-glow', spell.glow)

  // 外层旋转符箓圈：一圈法术字符
  const glyphRing = document.createElement('div')
  glyphRing.className = 'pet-array-glyphring'
  const N = 12
  for (let i = 0; i < N; i++) {
    const g = document.createElement('span')
    g.className = 'pet-array-glyph'
    g.textContent = spell.glyphs[i % spell.glyphs.length]
    const angle = (i / N) * 360
    g.style.transform = `rotate(${angle}deg) translateY(-58px)`
    glyphRing.appendChild(g)
  }
  array.appendChild(glyphRing)

  // 内层反向旋转的刻线环
  const lineRing = document.createElement('div')
  lineRing.className = 'pet-array-linering'
  array.appendChild(lineRing)

  // 中心几何法印：两个交叠方形（旋转 45°）构成八角星形
  const seal = document.createElement('div')
  seal.className = 'pet-array-seal'
  seal.innerHTML = '<i></i><i></i>'
  array.appendChild(seal)

  // 中心光核
  const core = document.createElement('div')
  core.className = 'pet-array-core'
  array.appendChild(core)

  document.body.appendChild(array)
  setTimeout(() => array.remove(), 1900)
}

// 施放指定法术（按 kind 分发特效与音效）
function castSpell(spell) {
  if (!spell) return
  petCast.value = spell.key
  if (spell.kind === 'throw')      petCastRuneThrow()
  else if (spell.kind === 'beam')  petCastBeam(spell)
  else if (spell.kind === 'swarm') petCastSwarm(spell)
  else                             petCastSpell(spell)
  petSfxCast(spell.kind)
  clearTimeout(petCastClearTimer)
  petCastClearTimer = window.setTimeout(() => { petCast.value = '' }, 2600)
}

// 随机施放一波法术
function castRandomSpell() {
  if (petCast.value) return
  castSpell(PET_SPELLS[Math.floor(Math.random() * PET_SPELLS.length)])
}

// 调试钩子：window.__jarvisPetCast('swarm') 手动触发指定法术，便于预览
function installPetCastDebugHook() {
  try {
    window.__jarvisPetCast = (key) => {
      const spell = PET_SPELLS.find(s => s.key === key)
      if (!spell) return { ok: false, error: 'unknown spell: ' + key, available: PET_SPELLS.map(s => s.key) }
      castSpell(spell)
      return { ok: true, spell: spell.key, kind: spell.kind }
    }
    window.__jarvisPetSpells = () => PET_SPELLS.map(s => ({ key: s.key, kind: s.kind }))
  } catch (e) {
    // 忽略：调试钩子失败不影响正常功能
  }
}

// 约 30s 放一波法术（±5s 抖动，避免过于机械）
let petCastTimer = 0
// 施法后清除 petCast 状态的定时器（与调度定时器分开，避免互相清除）
let petCastClearTimer = 0
function schedulePetCast() {
  clearTimeout(petCastTimer)
  petCastTimer = window.setTimeout(() => {
    if (!petPowerSaveActive.value && !document.hidden && !petHover.value && !petDrag.value && !petSleep.value &&
        !petHidden.value && !petPetting.value && !petWalking.value) {
      castRandomSpell()
    }
    schedulePetCast()
  }, 25000 + Math.random() * 10000)
}

// ==================== 宠物音效（Web Audio 合成，无外部资源） ====================
const PET_SFX_KEY = 'jarvis_pet_sfx'
const petSfxOn = ref(true)

let petAudioCtx = null
function getPetAudioCtx() {
  if (typeof window === 'undefined') return null
  // 省电模式：不创建/复用音频上下文，静音所有音效
  if (petPowerSaveActive.value) return null
  const AC = window.AudioContext || window.webkitAudioContext
  if (!AC) return null
  if (!petAudioCtx) petAudioCtx = new AC()
  if (petAudioCtx.state === 'suspended') petAudioCtx.resume()
  return petAudioCtx
}

function petTone(freq, start, dur, type, vol, slideTo) {
  const ctx = getPetAudioCtx()
  if (!ctx) return
  try {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.type = type || 'sine'
    const t0 = ctx.currentTime + start
    osc.frequency.setValueAtTime(freq, t0)
    if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur)
    gain.gain.setValueAtTime(0.0001, t0)
    gain.gain.exponentialRampToValueAtTime(vol || 0.08, t0 + 0.012)
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur)
    osc.start(t0)
    osc.stop(t0 + dur + 0.02)
  } catch (e) {
    // 忽略音频异常，不影响交互
  }
}

// 点击：清脆"啾啾"
function petSfxChirp() {
  if (!petSfxOn.value) return
  petTone(900, 0, 0.09, 'triangle', 0.09, 1500)
  petTone(1500, 0.07, 0.11, 'triangle', 0.07, 2100)
}

// 随机小动作配音
function petSfxAction(action) {
  if (!petSfxOn.value) return
  switch (action) {
    case 'look':
      petTone(1200, 0, 0.07, 'sine', 0.05, 1400)
      break
    case 'yawn':
      petTone(700, 0, 0.42, 'sine', 0.06, 380)
      break
    case 'spin':
      petTone(700, 0, 0.08, 'triangle', 0.06)
      petTone(1000, 0.08, 0.08, 'triangle', 0.06)
      petTone(1400, 0.16, 0.1, 'triangle', 0.06)
      break
    case 'hop':
      petTone(600, 0, 0.12, 'sine', 0.08, 1300)
      break
    case 'throw':
      petTone(500, 0, 0.09, 'triangle', 0.07, 1600)
      petTone(1600, 0.1, 0.1, 'triangle', 0.06, 900)
      break
  }
}

// 双击欢呼
function petSfxCheer() {
  if (!petSfxOn.value) return
  petTone(880, 0, 0.1, 'triangle', 0.08, 1320)
  petTone(1320, 0.09, 0.1, 'triangle', 0.08, 1760)
  petTone(1760, 0.18, 0.18, 'triangle', 0.07, 2200)
}

// 咀嚼：短促双音
function petSfxChomp() {
  if (!petSfxOn.value) return
  petTone(320, 0, 0.07, 'square', 0.05, 180)
  petTone(300, 0.14, 0.07, 'square', 0.05, 170)
}

// 呼噜：低频颤音
function petSfxPurr() {
  if (!petSfxOn.value) return
  petTone(180, 0, 0.5, 'sawtooth', 0.035, 210)
  petTone(150, 0.06, 0.45, 'sine', 0.03, 175)
}

// 唱歌：音阶序列
function petSfxSong() {
  if (!petSfxOn.value) return
  const scale = [523, 587, 659, 784, 880, 1047]
  scale.forEach((f, i) => petTone(f, i * 0.14, 0.16, 'sine', 0.06))
}

// 打盹哈欠
function petSfxYawn() {
  if (!petSfxOn.value) return
  petTone(620, 0, 0.45, 'sine', 0.06, 300)
}

// 施法：玄妙上扬的和声
function petSfxCast(type) {
  if (!petSfxOn.value) return
  switch (type) {
    case 'thunder':
      petTone(220, 0, 0.5, 'sawtooth', 0.05, 880)
      petTone(660, 0.06, 0.3, 'triangle', 0.05, 1320)
      break
    case 'flame':
      petTone(300, 0, 0.4, 'sawtooth', 0.045, 620)
      petTone(880, 0.08, 0.25, 'sine', 0.05, 1180)
      break
    case 'frost':
      petTone(1600, 0, 0.35, 'sine', 0.05, 900)
      petTone(1200, 0.1, 0.3, 'triangle', 0.045, 1900)
      break
    case 'beam':   // 远程：破空疾射
      petTone(1400, 0, 0.22, 'sawtooth', 0.045, 320)
      petTone(210, 0.02, 0.3, 'triangle', 0.05, 160)
      break
    case 'throw':  // 抛出法环
      petTone(700, 0, 0.2, 'triangle', 0.05, 1400)
      petTone(1180, 0.12, 0.35, 'sine', 0.045, 1760)
      break
    case 'swarm':  // 万剑归宗：锵然剑鸣 + 剑气呼啸
      petTone(2400, 0, 0.18, 'sawtooth', 0.05, 520)
      petTone(1500, 0.04, 0.3, 'triangle', 0.045, 2600)
      petTone(320, 0.5, 0.5, 'sine', 0.05, 180)
      petTone(1900, 1.5, 0.4, 'triangle', 0.045, 900)
      break
    default: // star
      petTone(784, 0, 0.16, 'sine', 0.05, 1046)
      petTone(1046, 0.14, 0.16, 'sine', 0.05, 1318)
      petTone(1318, 0.28, 0.3, 'sine', 0.045, 1568)
      break
  }
}

function togglePetSfx() {
  petSfxOn.value = !petSfxOn.value
  try {
    localStorage.setItem(PET_SFX_KEY, petSfxOn.value ? '1' : '0')
  } catch (e) {
    // 忽略存储异常
  }
  if (petSfxOn.value) petSfxChirp()
}

// 切换迷你拓扑图显示
function togglePetTopo() {
  petTopoOn.value = !petTopoOn.value
  try {
    localStorage.setItem(PET_TOPO_KEY, petTopoOn.value ? '1' : '0')
  } catch (e) {
    // 忽略存储异常
  }
  petSfxChirp()
}

// 随机小动作
// 随机小动作（throw 已归入法术特效，见 PET_SPELLS）
const PET_ACTIONS = ['look', 'yawn', 'spin', 'hop']
// 随机趣味行为：偶尔自发喂食/玩球/唱歌/打盹（不再由菜单触发）
const PET_FUN_ACTIONS = [petFeed, petPlayBall, petSing, togglePetSleep]
let petActTimer = 0
function schedulePetAction() {
  clearTimeout(petActTimer)
  petActTimer = window.setTimeout(() => {
    if (!petPowerSaveActive.value && !document.hidden && !petHover.value && !petDrag.value && !petSleep.value && !petHidden.value && !petPetting.value && !petWalking.value) {
      // 约四分之一概率触发趣味行为，其余为普通小动作
      if (Math.random() < 0.25) {
        const fun = PET_FUN_ACTIONS[Math.floor(Math.random() * PET_FUN_ACTIONS.length)]
        fun()
      } else {
        const act = PET_ACTIONS[Math.floor(Math.random() * PET_ACTIONS.length)]
        petAction.value = act
        petSfxAction(act)
        const actDur = act === 'throw' ? 2600 : 1700
        setTimeout(() => { petAction.value = '' }, actDur)
      }
    }
    schedulePetAction()
  }, 5000 + Math.random() * 7000)
}

function onPetResize() {
  if (petEdge.value) {
    // 贴边态：按新视口宽度重算贴边位置
    applyPetEdge()
    return
  }
  petPos.value = clampPetPos(petPos.value.x, petPos.value.y)
}

// ==================== 随机漫步 ====================
let petWanderTimer = 0   // 下次醒来的时间
let petWanderRaf = 0     // 漫步动画帧
// 当前是否可自由漫步：未固定/拖拽/悬停/睡眠/隐藏/摸头，且页面可见
function canPetWander() {
  return !petPinned.value && !petPowerSaveActive.value && !document.hidden && !petHover.value && !petDrag.value &&
    !petSleep.value && !petHidden.value && !petPetting.value && !petWalking.value && !petEdge.value
}

function schedulePetWander() {
  clearTimeout(petWanderTimer)
  petWanderTimer = window.setTimeout(() => {
    if (canPetWander()) startPetWalk()
    schedulePetWander()
  }, 9000 + Math.random() * 14000)
}

// 随机选一个附近的目的地：多数时候小范围踱步，偶尔走远一点
function pickPetDestination() {
  const maxX = Math.max(0, window.innerWidth - petW())
  const maxY = Math.max(0, window.innerHeight - petH())
  const far = Math.random() < 0.15
  const rangeX = far ? window.innerWidth * 0.4 : 170
  const rangeY = far ? window.innerHeight * 0.35 : 90
  const nx = petPos.value.x + (Math.random() * 2 - 1) * rangeX
  const ny = petPos.value.y + (Math.random() * 2 - 1) * rangeY
  return {
    x: Math.max(0, Math.min(maxX, nx)),
    y: Math.max(0, Math.min(maxY, ny)),
  }
}

function startPetWalk() {
  const from = { x: petPos.value.x, y: petPos.value.y }
  const to = pickPetDestination()
  const dist = Math.hypot(to.x - from.x, to.y - from.y)
  // 移动太小就不走了，避免原地抖动
  if (dist < 40) return
  // 朝向：根据水平方向翻转
  petFaceDir.value = to.x < from.x ? -1 : 1
  petWalking.value = true
  // 悄悄移动就不发声了，避免打扰
  // 移动端宠物更小，移动速度减半（时长翻倍）
  const speedFactor = isMobileView.value ? 22 : 11
  const dur = Math.max(1600, Math.min(6000, dist * speedFactor))
  const t0 = performance.now()
  const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2)
  const step = (now) => {
    const t = Math.min(1, (now - t0) / dur)
    const e = easeInOut(t)
    petPos.value = clampPetPos(
      from.x + (to.x - from.x) * e,
      from.y + (to.y - from.y) * e
    )
    if (t < 1) {
      petWanderRaf = requestAnimationFrame(step)
    } else {
      petWanderRaf = 0
      petWalking.value = false
      savePetPos()
    }
  }
  cancelAnimationFrame(petWanderRaf)
  petWanderRaf = requestAnimationFrame(step)
}

// 中断漫步（拖拽/交互时）
function stopPetWalk() {
  if (petWanderRaf) {
    cancelAnimationFrame(petWanderRaf)
    petWanderRaf = 0
  }
  petWalking.value = false
}

// 宠物隐藏时停掉所有常驻运算（小动作/漫步调度、动画帧、鼠标跟踪监听），节省资源
function stopPetLoops() {
  clearTimeout(petActTimer)
  petActTimer = 0
  clearTimeout(petWanderTimer)
  petWanderTimer = 0
  clearTimeout(petSleepTimer)
  petSleepTimer = 0
  clearTimeout(petCastTimer)
  petCastTimer = 0
  clearTimeout(petCastClearTimer)
  petCastClearTimer = 0
  petCast.value = ''
  stopPetWalk()
  clearTimeout(petEncourageTimer)
  petEncourageTimer = 0
  if (petRaf) {
    cancelAnimationFrame(petRaf)
    petRaf = 0
  }
  document.removeEventListener('mousemove', onPetMouseMove)
}

// 宠物重新显示时重启常驻运算（幂等：已在运行时不会重复启动）
function startPetLoops() {
  if (petPowerSaveActive.value) return  // 省电模式：不启动任何常驻特效与运算
  if (!petActTimer) schedulePetAction()
  if (!petWanderTimer) schedulePetWander()
  if (!petCastTimer) schedulePetCast()
  if (!petEncourageTimer) schedulePetEncourage()
  document.addEventListener('mousemove', onPetMouseMove)
}

// 切换省电模式：开启时停掉所有常驻运算与特效，关闭时恢复
function togglePetPowerSave() {
  petPowerSave.value = !petPowerSave.value
  try {
    localStorage.setItem(PET_POWER_SAVE_KEY, petPowerSave.value ? '1' : '0')
  } catch (e) {
    // 忽略存储异常
  }
  if (petPowerSaveActive.value) {
    stopPetLoops()
    petAction.value = ''
    petSpeech.value = ''
    petCast.value = ''
    clearTimeout(petSpeechTimer)
    petSpeechTimer = 0
  } else {
    startPetLoops()
  }
}

// 切换固定状态：固定时立即停止当前漫步，并禁止后续随机移动
function togglePetPin() {
  petPinned.value = !petPinned.value
  try {
    localStorage.setItem(PET_PIN_KEY, petPinned.value ? '1' : '0')
  } catch (e) {
    // 忽略存储异常
  }
  if (petPinned.value) stopPetWalk()
  petSfxChirp()
}

onMounted(() => {
  initPetPos()
  initRestorePos()
  initPetEdge()
  try {
    petSfxOn.value = localStorage.getItem(PET_SFX_KEY) !== '0'
  } catch (e) {
    petSfxOn.value = true
  }
  try {
    petTopoOn.value = localStorage.getItem(PET_TOPO_KEY) !== '0'
  } catch (e) {
    petTopoOn.value = true
  }
  try {
    petHidden.value = localStorage.getItem(PET_HIDDEN_KEY) === '1'
  } catch (e) {
    petHidden.value = false
  }
  try {
    petPowerSave.value = localStorage.getItem(PET_POWER_SAVE_KEY) === '1'
  } catch (e) {
    petPowerSave.value = false
  }
  try {
    petPinned.value = localStorage.getItem(PET_PIN_KEY) === '1'
  } catch (e) {
    petPinned.value = false
  }
  document.addEventListener('mousemove', onPetMouseMove)
  window.addEventListener('resize', onPetResize)
  installPetCastDebugHook()
  startPetLoops()
})

// 未连接（登录界面）时宠物不可见，同步停止/恢复其常驻运算
watch(() => props.isConnected, (connected) => {
  if (connected) {
    startPetLoops()
  } else {
    stopPetLoops()
  }
})

// 省电模式生效状态变化（含移动端/桌面端切换）时，同步启停常驻运算
watch(petPowerSaveActive, (active) => {
  if (active) {
    stopPetLoops()
  } else if (props.isConnected) {
    startPetLoops()
  }
})

onUnmounted(() => {
  document.removeEventListener('mousemove', onPetMouseMove)
  window.removeEventListener('resize', onPetResize)
  clearTimeout(petMenuLongPressTimer)
  clearTimeout(petActTimer)
  clearTimeout(petClickTimer)
  clearTimeout(restoreClickTimer)
  clearTimeout(petSpeechTimer)
  clearTimeout(petHideTimer)
  clearInterval(petPettingFxTimer)
  clearTimeout(petWanderTimer)
  clearTimeout(petSleepTimer)
  clearTimeout(petCastTimer)
  clearTimeout(petCastClearTimer)
  clearTimeout(petEncourageTimer)
  clearTimeout(petEdgeLeaveTimer)
  if (petRaf) cancelAnimationFrame(petRaf)
  if (petWanderRaf) cancelAnimationFrame(petWanderRaf)
  try {
    delete window.__jarvisPetCast
    delete window.__jarvisPetSpells
  } catch (e) {
    // 忽略
  }
})

defineExpose({
  togglePet,
  hidePet: petHide,
  showPet,
})
</script>

<style scoped>
/* 宠物挂件：浮动于页面，可拖拽并记忆位置 */
.pet-float {
  position: fixed;
  z-index: 900;
  width: 200px;
  height: 230px;
  pointer-events: none;
  touch-action: none;
  /* 贴边滑入/滑出动画（位移走 left，避免与移动端 scale 的 transform 冲突） */
  transition: left 0.22s ease;
}

/* 贴边态：固定在屏幕内侧边缘的唤出触发条，接收鼠标移入以临时滑出宠物。
   用 position:fixed 独立于 .pet-float 定位，避免随宠物滑入/滑出动画移动 */
.pet-edge-trigger {
  position: fixed;
  width: 18px;
  pointer-events: auto;
  cursor: pointer;
  touch-action: none;
  /* 参考全局工具条贴边窄边条：z-index 需高于 .pet-float(900)，
     否则贴边收起时露出的那点边会被宠物热区 .pet-hit 覆盖，点击/触摸收不到事件。
     收起态触发条在宠物之上，点它即唤出；滑出态触发条 v-show 隐藏，不影响宠物操作 */
  z-index: 10000;
}
.pet-edge-trigger.is-left {
  left: 0;
}
.pet-edge-trigger.is-right {
  right: 0;
}

/* 移动端：宠物整体缩小一半。以左上角为缩放原点，使 petPos 仍是视觉左上角，
   与 JS 侧的 petW()/petH()（返回缩放后尺寸）保持一致 */
.pet-float.pet-compact {
  transform: scale(0.5);
  transform-origin: top left;
  /* 跳跃/起伏高度减半 */
  --pet-hop: 0.5;
}

.pet-inner {
  position: relative;
  width: 100%;
  height: 100%;
}

.pet-glow {
  position: absolute;
  left: 50%;
  bottom: 26px;
  width: 236px;
  height: 52px;
  transform: translateX(-50%);
  border-radius: 50%;
  pointer-events: none;
  opacity: 0.25;
  background: radial-gradient(50% 50% at 50% 50%, rgba(32, 200, 255, 0.35) 0%, transparent 70%);
  animation: pet-glow 2.6s ease-in-out infinite;
}

/* ==================== 头顶数字光环（天使光环造型的 0/1 灵符圈） ==================== */
.pet-rune-ring {
  position: absolute;
  left: 50%;
  top: 40px;
  width: 0;
  height: 0;
  /* 天使光环：整体压扁成椭圆并略微倾斜（前低后高），悬于头顶上方；随宠物朝向镜像 */
  transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1));
  pointer-events: none;
  z-index: 1;
}

/* 光环整体缓慢自转，营造灵阵运转之感（周期由 --rune-spin-dur 统一控制） */
.pet-rune-orbit {
  position: absolute;
  left: 0;
  top: 0;
  width: 0;
  height: 0;
  animation: pet-rune-spin var(--rune-spin-dur, 26s) linear infinite;
}

/* 每个灵符：外层只负责定位（先转到方位角，再沿半径外推），不做动画 */
.pet-rune-bit {
  position: absolute;
  left: 0;
  top: 0;
  width: 14px;
  height: 14px;
  margin: -7px 0 0 -7px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 内层字符：抵消光环自转与压扁，使字符始终正立且不被压扁；同时做呼吸闪烁 */
.pet-rune-glyph {
  font-family: 'Courier New', Consolas, monospace;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  color: #b8f4ff;
  text-shadow: 0 0 6px rgba(126, 231, 255, 0.95), 0 0 14px rgba(32, 200, 255, 0.7);
  opacity: 0.85;
  /* 反向旋转抵消 orbit 自转，使字符始终正立；压扁由容器统一处理 */
  animation-name: pet-rune-counter, pet-rune-glow;
  animation-duration: var(--rune-spin-dur, 26s), var(--rune-glow-dur, 2.4s);
  animation-timing-function: linear, ease-in-out;
  animation-delay: 0s, var(--rune-glow-delay, 0s);
  animation-iteration-count: infinite, infinite;
}

/* 光环内圈：淡青灵光，衬托宠物头顶（同样压扁成椭圆） */
.pet-rune-core {
  position: absolute;
  left: 0;
  top: 0;
  width: 124px;
  height: 124px;
  margin: -62px 0 0 -62px;
  border-radius: 50%;
  border: 1px solid rgba(126, 231, 255, 0.22);
  box-shadow: inset 0 0 24px rgba(32, 200, 255, 0.18), 0 0 18px rgba(32, 200, 255, 0.12);
  opacity: 0.7;
  animation: pet-rune-breathe 3.4s ease-in-out infinite;
}

@keyframes pet-rune-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 与 pet-rune-spin 同周期反向，抵消父级自转使字符正立；scaleY 补偿容器压扁 */
@keyframes pet-rune-counter {
  from { transform: rotate(0deg) scaleY(2.381); }
  to { transform: rotate(-360deg) scaleY(2.381); }
}

@keyframes pet-rune-glow {
  0%, 100% { opacity: 0.35; filter: brightness(0.9); }
  50% { opacity: 1; filter: brightness(1.5); }
}

@keyframes pet-rune-breathe {
  0%, 100% { opacity: 0.45; transform: scale(0.96); }
  50% { opacity: 0.85; transform: scale(1.04); }
}

/* ==================== 环绕宠物的轨道灵珠/符文（与头顶光环同一套玄幻语言） ==================== */
/* 两圈不同倾角、反向旋转的椭圆轨道，各带灵珠/符文绕身体公转 */
.pet-orbit {
  position: absolute;
  left: 50%;
  top: 46%;
  width: 0;
  height: 0;
  pointer-events: none;
  opacity: 0.75;
  transition: opacity 0.6s ease;
}

/* 轨道 A：较平缓，青色灵珠 */
.pet-orbit.orbit-a {
  --orbit-tilt: 18deg;
  --orbit-squash: 0.34;
  --orbit-dur: 14s;
  transform: translateX(-50%) rotateZ(var(--orbit-tilt)) scaleY(var(--orbit-squash));
}

/* 轨道 B：较陡，反向旋转的星光符文 */
.pet-orbit.orbit-b {
  --orbit-tilt: -32deg;
  --orbit-squash: 0.5;
  --orbit-dur: 20s;
  transform: translateX(-50%) rotateZ(var(--orbit-tilt)) scaleY(var(--orbit-squash));
}

.pet-orbit-track {
  position: absolute;
  left: 0;
  top: 0;
  width: 0;
  height: 0;
  animation: pet-orbit-spin var(--orbit-dur, 16s) linear infinite;
}

/* 反向旋转的轨道整体转向相反 */
.pet-orbit.orbit-b .pet-orbit-track {
  animation-direction: reverse;
}

/* 灵珠：沿轨道均分分布，补偿压扁使圆点仍为圆 */
.pet-orbit-mote {
  position: absolute;
  left: 0;
  top: 0;
  width: 6px;
  height: 6px;
  margin: -3px 0 0 -3px;
  border-radius: 50%;
  background: radial-gradient(circle, #ffffff 0%, #9fe9ff 45%, transparent 75%);
  box-shadow: 0 0 8px rgba(126, 231, 255, 0.95);
  transform: translateY(-96px) scaleY(calc(1 / var(--orbit-squash, 1)));
}

.pet-orbit-mote:nth-child(1) { transform: rotate(0deg) translateY(-96px) scaleY(calc(1 / var(--orbit-squash, 1))); }
.pet-orbit-mote:nth-child(2) { transform: rotate(120deg) translateY(-96px) scaleY(calc(1 / var(--orbit-squash, 1))); }
.pet-orbit-mote:nth-child(3) { transform: rotate(240deg) translateY(-96px) scaleY(calc(1 / var(--orbit-squash, 1))); }

/* 符文：沿轨道分布，自身反向自转保持正立 */
.pet-orbit-rune {
  position: absolute;
  left: 0;
  top: 0;
  width: 14px;
  height: 14px;
  margin: -7px 0 0 -7px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  line-height: 1;
  color: #d8f6ff;
  text-shadow: 0 0 6px rgba(126, 231, 255, 0.95), 0 0 12px rgba(32, 200, 255, 0.7);
  transform: translateY(-104px) scaleY(calc(1 / var(--orbit-squash, 1)));
  animation: pet-orbit-rune-glow 2.6s ease-in-out infinite;
}

.pet-orbit-rune:nth-child(1) { transform: rotate(0deg) translateY(-104px) scaleY(calc(1 / var(--orbit-squash, 1))); }
.pet-orbit-rune:nth-child(2) { transform: rotate(120deg) translateY(-104px) scaleY(calc(1 / var(--orbit-squash, 1))); }
.pet-orbit-rune:nth-child(3) { transform: rotate(240deg) translateY(-104px) scaleY(calc(1 / var(--orbit-squash, 1))); }

@keyframes pet-orbit-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes pet-orbit-rune-glow {
  0%, 100% { opacity: 0.4; filter: brightness(0.9); }
  50% { opacity: 1; filter: brightness(1.5); }
}

/* 运行中：轨道转快、灵光大盛 */
.pet-float.rune-running .pet-orbit {
  opacity: 1;
}
.pet-float.rune-running .pet-orbit.orbit-a { --orbit-dur: 8s; }
.pet-float.rune-running .pet-orbit.orbit-b { --orbit-dur: 11s; }

/* 打盹：轨道近乎停滞、黯淡 */
.pet-float.rune-sleep .pet-orbit {
  opacity: 0.22;
}
.pet-float.rune-sleep .pet-orbit.orbit-a { --orbit-dur: 120s; }
.pet-float.rune-sleep .pet-orbit.orbit-b { --orbit-dur: 150s; }

/* 施法瞬间：轨道骤然加速 */
.pet-float.is-casting .pet-orbit {
  opacity: 1;
}
.pet-float.is-casting .pet-orbit.orbit-a { --orbit-dur: 3s; }
.pet-float.is-casting .pet-orbit.orbit-b { --orbit-dur: 4.5s; }

/* —— 状态联动（转速统一由 --rune-spin-dur 控制，orbit 与字符反向自转同步）—— */
/* 运行中：灵符转快、青芒炽盛 */
.pet-float.rune-running {
  --rune-spin-dur: 9s;
}
.pet-float.rune-running .pet-rune-glyph {
  color: #d8fbff;
  text-shadow: 0 0 8px rgba(126, 231, 255, 1), 0 0 20px rgba(32, 200, 255, 0.95);
}
.pet-float.rune-running .pet-rune-core {
  border-color: rgba(126, 231, 255, 0.5);
  box-shadow: inset 0 0 30px rgba(32, 200, 255, 0.35), 0 0 26px rgba(32, 200, 255, 0.35);
}

/* 等待输入：转为金色脉冲，警示感 */
.pet-float.rune-waiting {
  --rune-spin-dur: 14s;
}
.pet-float.rune-waiting .pet-rune-glyph {
  color: #ffe6a8;
  text-shadow: 0 0 8px rgba(255, 209, 102, 1), 0 0 18px rgba(255, 152, 0, 0.85);
}
.pet-float.rune-waiting .pet-rune-core {
  border-color: rgba(255, 209, 102, 0.6);
  box-shadow: inset 0 0 30px rgba(255, 152, 0, 0.35), 0 0 28px rgba(255, 152, 0, 0.45);
  animation-duration: 1.4s;
}

/* 打盹：灵光暗淡、近乎停滞 */
.pet-float.rune-sleep {
  --rune-spin-dur: 90s;
}
.pet-float.rune-sleep .pet-rune-ring {
  opacity: 0.28;
  transition: opacity 0.6s ease;
}
.pet-float.rune-sleep .pet-rune-glyph {
  color: #7fa6b8;
  text-shadow: 0 0 6px rgba(126, 231, 255, 0.4);
}

.pet-hit {
  position: absolute;
  left: 50%;
  bottom: 44px;
  width: 150px;
  height: 130px;
  transform: translateX(-50%);
  cursor: grab;
  pointer-events: auto;
  z-index: 3;
}

.pet-float.is-drag .pet-hit {
  cursor: grabbing;
}

.pet-body {
  position: absolute;
  left: 50%;
  bottom: 52px;
  width: 126px;
  height: 110px;
  transform: translateX(-50%);
  pointer-events: none;
  animation: pet-bob 2.6s ease-in-out infinite;
}

.pet-head {
  position: absolute;
  left: 50%;
  top: 0;
  width: 95px;
  height: 83px;
  transform: translateX(-50%);
  background: linear-gradient(160deg, #2ee6ff 0%, #1a9fd6 55%, #0e6f9e 100%);
  border-radius: 50% 50% 46% 46%;
  box-shadow: 0 0 18px rgba(32, 200, 255, 0.45), inset 0 -6px 12px rgba(0, 0, 0, 0.25),
    inset 0 4px 8px rgba(255, 255, 255, 0.18);
  transition: transform 0.25s ease;
}

.pet-ear {
  position: absolute;
  top: -18px;
  width: 0;
  height: 0;
  border-left: 18px solid transparent;
  border-right: 18px solid transparent;
  border-bottom: 27px solid #23b9e8;
  filter: drop-shadow(0 0 6px rgba(32, 200, 255, 0.5));
  transition: transform 0.25s ease;
}

.pet-ear.l {
  left: 4px;
  transform: rotate(-18deg);
}

.pet-ear.r {
  right: 4px;
  transform: rotate(18deg);
}

.pet-eye {
  position: absolute;
  top: 31px;
  width: 16px;
  height: 19px;
  border-radius: 50%;
  background: #06131f;
  box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.75);
  animation: pet-blink 4.2s infinite;
}

.pet-eye.l {
  left: 22px;
}

.pet-eye.r {
  right: 22px;
}

.pet-pupil {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(234, 252, 255, 0.9);
  transform: translate(-50%, -50%);
  transition: transform 0.12s ease-out;
}

.pet-mouth {
  position: absolute;
  left: 50%;
  top: 60px;
  width: 23px;
  height: 12px;
  transform: translateX(-50%);
  border-bottom: 2px solid rgba(6, 19, 31, 0.75);
  border-radius: 0 0 8px 8px;
  transition: all 0.2s ease;
}

.pet-tail {
  position: absolute;
  right: -19px;
  bottom: 16px;
  width: 43px;
  height: 43px;
  border: 3px solid #23b9e8;
  border-color: #23b9e8 transparent transparent transparent;
  border-radius: 50%;
  transform-origin: 0% 100%;
  animation: pet-tail 1.6s ease-in-out infinite;
  filter: drop-shadow(0 0 6px rgba(32, 200, 255, 0.45));
}

.pet-shadow {
  position: absolute;
  left: 50%;
  bottom: 39px;
  width: 102px;
  height: 18px;
  transform: translateX(-50%);
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.35);
  filter: blur(2px);
  pointer-events: none;
  animation: pet-shadow 2.6s ease-in-out infinite;
}

.pet-spark {
  position: absolute;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #7ee7ff;
  box-shadow: 0 0 6px #7ee7ff;
  opacity: 0;
  pointer-events: none;
  animation: pet-spark 3.2s ease-in-out infinite;
}

.pet-spark.s1 {
  left: 22%;
  bottom: 102px;
  animation-delay: 0.2s;
}

.pet-spark.s2 {
  left: 74%;
  bottom: 137px;
  animation-delay: 1.1s;
}

.pet-spark.s3 {
  left: 50%;
  bottom: 166px;
  animation-delay: 2s;
}

.pet-label {
  position: absolute;
  left: 50%;
  bottom: 6px;
  transform: translateX(-50%);
  font-size: 13px;
  letter-spacing: 2px;
  color: rgba(126, 231, 255, 0.55);
  white-space: nowrap;
  pointer-events: none;
}

.pet-sfx-btn {
  position: absolute;
  right: 8px;
  bottom: 4px;
  width: 24px;
  height: 24px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  line-height: 1;
  border: none;
  border-radius: 50%;
  background: rgba(32, 200, 255, 0.12);
  cursor: pointer;
  pointer-events: auto;
  z-index: 5;
  opacity: 0.5;
  transition: opacity 0.2s ease, background 0.2s ease, transform 0.2s ease;
}

.pet-sfx-btn:hover {
  opacity: 1;
  background: rgba(32, 200, 255, 0.25);
  transform: scale(1.12);
}

.pet-sfx-btn.is-off {
  opacity: 0.35;
  filter: grayscale(1);
}

/* 固定宠物开关（置于省电模式按钮正上方） */
.pet-pin-btn {
  position: absolute;
  right: 8px;
  bottom: 60px;
  width: 24px;
  height: 24px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  line-height: 1;
  border: none;
  border-radius: 50%;
  background: rgba(32, 200, 255, 0.12);
  cursor: pointer;
  pointer-events: auto;
  z-index: 5;
  opacity: 0.5;
  transition: opacity 0.2s ease, background 0.2s ease, transform 0.2s ease;
}
.pet-pin-btn:hover {
  opacity: 1;
  background: rgba(32, 200, 255, 0.25);
  transform: scale(1.12);
}
.pet-pin-btn.is-on {
  opacity: 1;
  background: rgba(255, 209, 102, 0.22);
}

/* 省电模式开关（移动端/桌面端均显示，置于声音按钮正上方） */
.pet-power-btn {
  position: absolute;
  right: 8px;
  bottom: 32px;
  width: 24px;
  height: 24px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  line-height: 1;
  border: none;
  border-radius: 50%;
  background: rgba(32, 200, 255, 0.12);
  cursor: pointer;
  pointer-events: auto;
  z-index: 5;
  opacity: 0.5;
  transition: opacity 0.2s ease, background 0.2s ease, transform 0.2s ease;
}
.pet-power-btn:hover {
  opacity: 1;
  background: rgba(32, 200, 255, 0.25);
  transform: scale(1.12);
}
.pet-power-btn.is-on {
  opacity: 1;
  background: rgba(120, 255, 170, 0.22);
}

/* ==================== 省电模式：关闭一切装饰性动画与特效 ==================== */
.pet-float.power-save .pet-spark,
.pet-float.power-save .pet-orbit,
.pet-float.power-save .pet-zzz,
.pet-float.power-save .pet-rune,
.pet-float.power-save .pet-rune-ring,
.pet-float.power-save .pet-rune-glyph,
.pet-float.power-save .pet-rune-core,
.pet-float.power-save .pet-tail,
.pet-float.power-save .pet-eye,
.pet-float.power-save .pet-bubble,
.pet-float.power-save .pet-shadow {
  animation: none !important;
  transition: none !important;
}
/* 隐藏纯装饰性元素，进一步降低渲染开销 */
.pet-float.power-save .pet-spark,
.pet-float.power-save .pet-orbit,
.pet-float.power-save .pet-zzz,
.pet-float.power-save .pet-rune-ring,
.pet-float.power-save .pet-rune-glyph,
.pet-float.power-save .pet-rune-core {
  display: none !important;
}
/* 宠物本体过渡与滤镜也一并关闭 */
.pet-float.power-save,
.pet-float.power-save * {
  animation: none !important;
}

/* 悬停反应 */
.pet-float.is-hover .pet-tail {
  animation-duration: 0.7s;
}

.pet-float.is-hover .pet-eye {
  animation-duration: 1.8s;
}

.pet-float.is-hover .pet-head {
  transform: translateX(-50%) translateY(-6px) scale(1.04);
}

.pet-float.is-hover .pet-mouth {
  width: 28px;
  border-bottom-width: 3px;
}

/* 拖拽反馈 */
.pet-float.is-drag .pet-body {
  animation-play-state: paused;
}

.pet-float.is-drag .pet-head {
  transform: translateX(-50%) scale(1.06);
}

.pet-float.is-drag .pet-shadow {
  transform: translateX(-50%) scale(0.6);
  opacity: 0.15;
}

.pet-float.is-drag .pet-tail {
  animation-duration: 0.5s;
}

/* 点击反馈 */
.pet-float.is-jump .pet-body {
  animation: pet-jump 0.55s cubic-bezier(0.3, -0.4, 0.4, 1.4);
}

/* 随机漫步：走路时身体轻微起伏、尾巴加速摆动 */
.pet-float.is-walk .pet-body {
  animation: pet-walk 0.5s ease-in-out infinite;
}

.pet-float.is-walk .pet-tail {
  animation-duration: 0.45s;
}

.pet-float.is-walk .pet-shadow {
  animation: pet-walk-shadow 0.5s ease-in-out infinite;
}

/* 朝向翻转：只翻转身体本体，不影响气泡/徽标/文字 */
.pet-float.face-left .pet-body {
  --pet-flip: -1;
}

/* 朝向翻转时，头顶光环一并镜像（含倾斜方向） */
.pet-float.face-left .pet-rune-ring {
  --pet-flip: -1;
}

/* 状态联动 */
.pet-float.is-run .pet-body {
  animation-duration: 1.8s;
}

.pet-float.is-run .pet-tail {
  animation-duration: 1.1s;
}

.pet-float.is-idle .pet-body {
  animation-duration: 3.6s;
}

.pet-float.is-idle .pet-tail {
  animation-duration: 2.4s;
}

.pet-float.is-idle .pet-eye {
  animation-duration: 6.5s;
}

.pet-float.is-waiting .pet-body {
  animation-duration: 1.4s;
}

/* 等待输入提示气泡 */
.pet-bubble {
  position: absolute;
  left: 50%;
  top: 6px;
  transform: translateX(-50%) scale(0.6);
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  color: #06131f;
  background: linear-gradient(135deg, #7ee7ff, #20c8ff);
  box-shadow: 0 0 14px rgba(32, 200, 255, 0.6);
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.25s ease, transform 0.25s ease;
}

/* 等待输入不再常驻显示气泡（避免空条条）；气泡仅在 is-speak（有临时台词）时显示 */

/* 随机小动作 */
.pet-float.act-look .pet-head {
  animation: pet-look 1.6s ease-in-out;
}

.pet-float.act-yawn .pet-mouth {
  animation: pet-yawn 1.6s ease-in-out;
}

.pet-float.act-spin .pet-body {
  animation: pet-spin 1.4s ease-in-out;
}

/* 空翻时头顶光环同步翻转一圈，与宠物动作呼应 */
.pet-float.act-spin .pet-rune-ring {
  animation: pet-rune-flip 1.4s ease-in-out;
}

/* 头顶光环被抛出去再飞回来：飞行与自转都很快，用 linear 保证自转匀速 */
.pet-float.act-throw .pet-rune-ring {
  animation: pet-rune-throw 2.4s linear;
}

.pet-float.act-hop .pet-body {
  animation: pet-jump 0.6s cubic-bezier(0.3, -0.4, 0.4, 1.4);
}

@keyframes pet-bob {
  0%,
  100% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(0);
  }
  50% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(calc(-13px * var(--pet-hop, 1)));
  }
}

/* 漫步时的小碎步起伏与压扁影子（--pet-flip 承载朝向，默认 1） */
@keyframes pet-walk {
  0%,
  100% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(0) rotate(-2deg);
  }
  50% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(-7px) rotate(2deg);
  }
}

@keyframes pet-walk-shadow {
  0%,
  100% {
    transform: translateX(-50%) scale(1);
    opacity: 0.35;
  }
  50% {
    transform: translateX(-50%) scale(0.82);
    opacity: 0.22;
  }
}

@keyframes pet-shadow {
  0%,
  100% {
    transform: translateX(-50%) scale(1);
    opacity: 0.35;
  }
  50% {
    transform: translateX(-50%) scale(0.82);
    opacity: 0.2;
  }
}

@keyframes pet-tail {
  0%,
  100% {
    transform: rotate(-8deg);
  }
  50% {
    transform: rotate(14deg);
  }
}

@keyframes pet-blink {
  0%,
  92%,
  100% {
    transform: scaleY(1);
  }
  96% {
    transform: scaleY(0.1);
  }
}

@keyframes pet-glow {
  0%,
  100% {
    opacity: 0.55;
  }
  50% {
    opacity: 1;
  }
}

@keyframes pet-spark {
  0%,
  100% {
    opacity: 0;
    transform: translateY(0) scale(0.6);
  }
  40% {
    opacity: 1;
    transform: translateY(-10px) scale(1);
  }
}

@keyframes pet-jump {
  0% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(0) scale(1, 1);
  }
  30% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(calc(-26px * var(--pet-hop, 1))) scale(0.94, 1.08);
  }
  60% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(0) scale(1.06, 0.94);
  }
  100% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(0) scale(1, 1);
  }
}

@keyframes pet-look {
  0%,
  100% {
    transform: translateX(-50%) rotate(0deg);
  }
  25% {
    transform: translateX(-50%) rotate(-7deg);
  }
  75% {
    transform: translateX(-50%) rotate(7deg);
  }
}

@keyframes pet-yawn {
  0%,
  100% {
    height: 12px;
    width: 23px;
  }
  50% {
    height: 22px;
    width: 30px;
    border-bottom-width: 4px;
  }
}

@keyframes pet-spin {
  0% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) rotate(0deg) scale(1);
  }
  50% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) rotate(180deg) scale(0.92);
  }
  100% {
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) rotate(360deg) scale(1);
  }
}

/* 头顶光环空翻：在原有压扁/倾斜/镜像基础上叠加一圈旋转 */
@keyframes pet-rune-flip {
  0% {
    transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) rotate(0deg);
  }
  50% {
    transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) rotate(180deg);
  }
  100% {
    transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) rotate(360deg);
  }
}

/* 抛出：快速飞到屏幕边缘并匀速自转，停顿一瞬后快速飞回原位 */
@keyframes pet-rune-throw {
  0% {
    transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) translate(0, 0) rotate(0deg);
  }
  40% {
    transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) translate(calc(46vw * var(--pet-flip, 1)), -42vh) rotate(720deg);
  }
  52% {
    transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) translate(calc(50vw * var(--pet-flip, 1)), -45vh) rotate(936deg);
  }
  88% {
    transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) translate(calc(5vw * var(--pet-flip, 1)), -4vh) rotate(1584deg);
  }
  100% {
    transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) translate(0, 0) rotate(1800deg);
  }
}

@keyframes pet-bubble-bounce {
  0%,
  100% {
    transform: translateX(-50%) scale(1) translateY(0);
  }
  50% {
    transform: translateX(-50%) scale(1.06) translateY(-4px);
  }
}

/* ==================== 新增交互样式 ==================== */
/* 宠物头顶状态徽标（等待/运行）*/
.pet-badge {
  position: absolute;
  left: 50%;
  top: 44px;
  transform: translateX(-50%);
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #06131f;
  background: linear-gradient(135deg, #7ee7ff, #20c8ff);
  border-radius: 11px;
  box-shadow: 0 0 12px rgba(32, 200, 255, 0.6);
  pointer-events: none;
  z-index: 4;
}

.pet-badge.is-alert {
  background: linear-gradient(135deg, #ffd166, #ff9800);
  box-shadow: 0 0 14px rgba(255, 152, 0, 0.7);
  animation: pet-badge-pulse 1.4s ease-in-out infinite;
}

/* 有等待输入的 Agent 时，徽标可点击跳转 */
.pet-badge.is-clickable {
  pointer-events: auto;
  cursor: pointer;
}

/* 移动端：徽标放大，便于手指点击 */
.pet-float.pet-compact .pet-badge {
  top: 22px;
  min-width: 34px;
  height: 34px;
  padding: 0 10px;
  font-size: 19px;
  border-radius: 17px;
}

/* 移动端：扩大徽标的可点击热区（视觉不变，热区外扩） */
.pet-float.pet-compact .pet-badge.is-clickable::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 56px;
  height: 56px;
  transform: translate(-50%, -50%);
}

@keyframes pet-badge-pulse {
  0%, 100% { transform: translateX(-50%) scale(1); }
  50% { transform: translateX(-50%) scale(1.12); }
}

/* 隐藏后的还原按钮 */
.pet-restore {
  position: fixed;
  z-index: 900;
  width: 40px;
  height: 40px;
  padding: 0;
  font-size: 18px;
  line-height: 1;
  border: 1px solid rgba(32, 200, 255, 0.4);
  border-radius: 50%;
  background: rgba(15, 30, 48, 0.9);
  cursor: grab;
  touch-action: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45), 0 0 12px rgba(32, 200, 255, 0.3);
  animation: pet-restore-in 0.25s ease-out;
  transition: background 0.18s ease;
}
.pet-restore:hover {
  transform: scale(1.1);
  background: rgba(32, 200, 255, 0.22);
}

@keyframes pet-restore-in {
  from { opacity: 0; transform: scale(0.6); }
  to { opacity: 1; transform: scale(1); }
}

/* ZZZ 睡眠标识 */
.pet-zzz {
  position: absolute;
  color: rgba(126, 231, 255, 0.85);
  font-weight: 700;
  opacity: 0;
  pointer-events: none;
  text-shadow: 0 0 8px rgba(32, 200, 255, 0.6);
}

.pet-zzz.z1 { left: 58%; top: 42px; font-size: 13px; }
.pet-zzz.z2 { left: 68%; top: 26px; font-size: 15px; }
.pet-zzz.z3 { left: 78%; top: 8px; font-size: 18px; }

.pet-float.is-sleep .pet-zzz {
  animation: pet-zzz 2.4s ease-in-out infinite;
}

.pet-float.is-sleep .pet-zzz.z2 { animation-delay: 0.5s; }
.pet-float.is-sleep .pet-zzz.z3 { animation-delay: 1s; }

@keyframes pet-zzz {
  0% { opacity: 0; transform: translateY(6px) scale(0.8); }
  40% { opacity: 1; }
  100% { opacity: 0; transform: translateY(-14px) scale(1.1); }
}

/* 睡眠：合眼、身体呼吸放慢 */
.pet-float.is-sleep .pet-eye {
  animation: none;
  height: 4px;
  border-radius: 3px;
  margin-top: 8px;
}

.pet-float.is-sleep .pet-pupil {
  opacity: 0;
}

.pet-float.is-sleep .pet-body {
  animation-duration: 4.4s;
}

.pet-float.is-sleep .pet-tail {
  animation-duration: 3.6s;
}

.pet-float.is-sleep .pet-mouth {
  width: 14px;
  height: 8px;
}

/* 摸头 */
.pet-float.is-petting .pet-head {
  animation: pet-pet-head 0.9s ease-in-out infinite;
}

.pet-float.is-petting .pet-eye {
  animation-duration: 1.6s;
}

.pet-float.is-petting .pet-tail {
  animation-duration: 0.6s;
}

@keyframes pet-pet-head {
  0%, 100% { transform: translateX(-50%) translateY(0) rotate(0deg); }
  50% { transform: translateX(-50%) translateY(-4px) rotate(2deg); }
}

/* 台词气泡：非等待输入时也显示 */
.pet-float.is-speak .pet-bubble {
  opacity: 1;
  transform: translateX(-50%) scale(1);
}

/* 双击撒花（cheer） */
.pet-float.act-cheer .pet-body {
  animation: pet-jump 0.5s cubic-bezier(0.3, -0.4, 0.4, 1.4) 2;
}

/* 喂食咀嚼 */
.pet-float.act-chomp .pet-mouth {
  animation: pet-chomp 0.36s ease-in-out 3;
}

@keyframes pet-chomp {
  0%, 100% { transform: translateX(-50%) scaleY(1); }
  50% { transform: translateX(-50%) scaleY(2.2); }
}

/* 追球 */
.pet-float.act-chase .pet-body {
  animation: pet-chase 1.3s ease-in-out;
}

@keyframes pet-chase {
  0%, 100% { transform: translateX(-50%) translateY(0) rotate(0deg); }
  25% { transform: translateX(-50%) translateY(-8px) rotate(-7deg); }
  75% { transform: translateX(-50%) translateY(-8px) rotate(7deg); }
}

/* 唱歌摇摆 */
.pet-float.act-sing .pet-body {
  animation: pet-sing 0.7s ease-in-out 2;
}

@keyframes pet-sing {
  0%, 100% { transform: translateX(-50%) rotate(-4deg); }
  50% { transform: translateX(-50%) rotate(4deg); }
}

/* 施法：身体微微悬起、头顶法环急促旋转并放大发光 */
.pet-float.is-casting .pet-body {
  animation: pet-cast-float 1.5s ease-in-out;
}

.pet-float.is-casting .pet-rune-ring {
  --rune-spin-dur: 3.2s;
  animation: pet-cast-ring 1.5s ease-out;
}

.pet-float.is-casting .pet-rune-glyph {
  animation-duration: var(--rune-spin-dur, 26s), 0.5s;
}

.pet-float.is-casting .pet-rune-core {
  animation-duration: 0.5s;
  border-color: rgba(126, 231, 255, 0.85);
  box-shadow: inset 0 0 34px rgba(32, 200, 255, 0.55), 0 0 30px rgba(32, 200, 255, 0.5);
}

@keyframes pet-cast-float {
  0%, 100% { transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(0) scale(1); }
  30% { transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(-12px) scale(1.05); }
  60% { transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(-6px) scale(1.02); }
}

/* 施法时头顶光环爆发式放大后回落 */
@keyframes pet-cast-ring {
  0% { transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) scale(1); }
  35% { transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) scale(1.5); }
  100% { transform: translateX(-50%) rotate(-10deg) scaleY(0.42) scaleX(var(--pet-flip, 1)) scale(1); }
}
</style>

<!-- 动态特效元素（append 到 body，需非 scoped 样式） -->
<style>
.pet-fx,
.pet-confetti,
.pet-heart-fx,
.pet-food,
.pet-ball,
.pet-note,
.pet-spell-array {
  position: fixed;
  z-index: 3100;
  pointer-events: none;
  user-select: none;
}

/* ==================== 施法：脚下灵光法阵 ==================== */
.pet-spell-array {
  width: 0;
  height: 0;
  /* 压扁成贴地的椭圆，营造俯视透视感 */
  transform: translate(-50%, -50%) rotateX(62deg);
  transform-style: preserve-3d;
  animation: pet-array-in 1.9s ease-out forwards;
}

/* 外层符箓圈：整圈缓慢自转 */
.pet-array-glyphring {
  position: absolute;
  left: 0;
  top: 0;
  width: 0;
  height: 0;
  animation: pet-array-spin 6s linear infinite;
}

.pet-array-glyph {
  position: absolute;
  left: 0;
  top: 0;
  width: 20px;
  height: 20px;
  margin: -10px 0 0 -10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  color: var(--spell-color, #9fd8ff);
  text-shadow: 0 0 8px var(--spell-glow, #5db2ff), 0 0 16px var(--spell-glow, #5db2ff);
}

/* 内层刻线环：反向旋转，虚线光边 */
.pet-array-linering {
  position: absolute;
  left: 0;
  top: 0;
  width: 92px;
  height: 92px;
  margin: -46px 0 0 -46px;
  border-radius: 50%;
  border: 1.5px dashed var(--spell-glow, #5db2ff);
  box-shadow: 0 0 14px var(--spell-glow, #5db2ff), inset 0 0 14px var(--spell-glow, #5db2ff);
  opacity: 0.85;
  animation: pet-array-spin-rev 4.5s linear infinite;
}

/* 中心几何法印：两个交叠方形旋转 45° 成八角星 */
.pet-array-seal {
  position: absolute;
  left: 0;
  top: 0;
  width: 0;
  height: 0;
  animation: pet-array-pulse 1.4s ease-in-out infinite;
}

.pet-array-seal i {
  position: absolute;
  left: 0;
  top: 0;
  width: 62px;
  height: 62px;
  margin: -31px 0 0 -31px;
  border: 1.5px solid var(--spell-color, #9fd8ff);
  box-shadow: 0 0 10px var(--spell-glow, #5db2ff), inset 0 0 10px var(--spell-glow, #5db2ff);
  opacity: 0.9;
}

.pet-array-seal i:nth-child(2) {
  transform: rotate(45deg);
}

/* 中心光核：耀眼一点 */
.pet-array-core {
  position: absolute;
  left: 0;
  top: 0;
  width: 26px;
  height: 26px;
  margin: -13px 0 0 -13px;
  border-radius: 50%;
  background: radial-gradient(circle, #ffffff 0%, var(--spell-color, #9fd8ff) 40%, transparent 72%);
  box-shadow: 0 0 22px var(--spell-glow, #5db2ff), 0 0 44px var(--spell-glow, #5db2ff);
  animation: pet-array-pulse 0.9s ease-in-out infinite;
}

@keyframes pet-array-in {
  0% { opacity: 0; scale: 0.4; }
  18% { opacity: 1; scale: 1.08; }
  30% { scale: 1; }
  78% { opacity: 1; scale: 1; }
  100% { opacity: 0; scale: 1.06; }
}

@keyframes pet-array-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes pet-array-spin-rev {
  from { transform: rotate(0deg); }
  to { transform: rotate(-360deg); }
}

@keyframes pet-array-pulse {
  0%, 100% { opacity: 0.75; }
  50% { opacity: 1; }
}

.pet-fx {
  font-size: 15px;
  animation: pet-fx-float 1.3s ease-out forwards;
}

@keyframes pet-fx-float {
  0% { opacity: 0; transform: translateY(0) scale(0.6) rotate(0deg); }
  25% { opacity: 1; }
  100% { opacity: 0; transform: translateY(-46px) scale(1.15) rotate(var(--rot, 0deg)); }
}

.pet-confetti {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  animation: pet-confetti-fly 1.2s cubic-bezier(0.2, 0.7, 0.4, 1) forwards;
}

@keyframes pet-confetti-fly {
  0% { opacity: 1; transform: translate(0, 0) rotate(0deg) scale(1); }
  60% { opacity: 1; }
  100% { opacity: 0; transform: translate(var(--dx, 0), var(--dy, -60px)) rotate(var(--rot, 180deg)) scale(0.5); }
}

.pet-heart-fx {
  font-size: 16px;
  color: #ff8ad8;
  animation: pet-heart-float 1.2s ease-out forwards;
}

@keyframes pet-heart-float {
  0% { opacity: 0; transform: translate(0, 0) scale(0.6); }
  25% { opacity: 1; }
  100% { opacity: 0; transform: translate(var(--dx, 0), -52px) scale(1.2); }
}

.pet-food {
  font-size: 22px;
  animation: pet-food-drop 0.85s cubic-bezier(0.5, 0, 0.8, 1) forwards;
}

@keyframes pet-food-drop {
  0% { opacity: 0; transform: translate(-50%, -30px) scale(0.7); }
  30% { opacity: 1; }
  100% { opacity: 0; transform: translate(-50%, 46px) scale(1.05); }
}

.pet-ball {
  font-size: 20px;
  animation: pet-ball-fly 1.4s ease-in-out forwards;
}

@keyframes pet-ball-fly {
  0% { opacity: 0; transform: translate(0, 0) rotate(0deg); }
  15% { opacity: 1; }
  50% { transform: translate(calc(var(--fly, 200px) / 2), -34px) rotate(180deg); }
  100% { opacity: 0; transform: translate(var(--fly, 200px), 0) rotate(360deg); }
}

.pet-note {
  font-size: 17px;
  color: #7ee7ff;
  text-shadow: 0 0 8px rgba(32, 200, 255, 0.6);
  animation: pet-note-float 1.6s ease-out forwards;
}

@keyframes pet-note-float {
  0% { opacity: 0; transform: translate(0, 0) scale(0.7); }
  20% { opacity: 1; }
  100% { opacity: 0; transform: translate(var(--dx, 0), -70px) scale(1.1) rotate(12deg); }
}
/* ==================== 施法：远程灵光 / 范围冲击 / 万剑归宗 ==================== */
/* 远程光束：从宠物射出的能量轨迹 */
.pet-spell-beam {
  position: fixed;
  z-index: 3100;
  pointer-events: none;
  height: 3px;
  border-radius: 3px;
  transform-origin: 0 50%;
  background: linear-gradient(90deg,
    transparent 0%,
    var(--spell-glow, #5db2ff) 12%,
    var(--spell-color, #9fd8ff) 55%,
    #ffffff 100%);
  box-shadow: 0 0 10px var(--spell-glow, #5db2ff), 0 0 22px var(--spell-glow, #5db2ff);
  animation: pet-beam-fire var(--beam-dur, 0.7s) cubic-bezier(0.2, 0.8, 0.3, 1) forwards;
}

@keyframes pet-beam-fire {
  0% { opacity: 0; scale: 0 0.4; }
  25% { opacity: 1; scale: 1 1; }
  100% { opacity: 0; scale: 1 1; }
}

/* 飞行灵符：沿光束方向疾行 */
.pet-spell-bolt {
  position: fixed;
  z-index: 3101;
  pointer-events: none;
  width: 0;
  height: 0;
  font-size: 24px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: pet-bolt-fly var(--beam-dur, 0.7s) cubic-bezier(0.3, 0.5, 0.2, 1) forwards;
}

@keyframes pet-bolt-fly {
  0% { opacity: 0; transform: translate(-50%, -50%) scale(0.5) rotate(0deg); }
  15% { opacity: 1; }
  85% { opacity: 1; }
  100% { opacity: 0; transform: translate(calc(-50% + var(--bx, 0px)), calc(-50% + var(--by, 0px))) scale(1.15) rotate(540deg); }
}

/* 命中爆点：抵达目标位置后炸开 */
.pet-spell-hit {
  position: fixed;
  z-index: 3101;
  pointer-events: none;
  width: 10px;
  height: 10px;
  margin: -5px 0 0 -5px;
  border-radius: 50%;
  border: 2px solid transparent;
  opacity: 0;
  animation: pet-hit-burst 0.5s ease-out forwards;
}

@keyframes pet-hit-burst {
  0% { opacity: 0; transform: scale(0.3); }
  30% { opacity: 1; transform: scale(1); }
  100% { opacity: 0; transform: scale(7); }
}

/* ==================== 万剑归宗 ==================== */
.pet-spell-sword {
  position: fixed;
  z-index: 3101;
  pointer-events: none;
  width: 0;
  height: 0;
  /* 沿 JS 生成的贝塞尔曲线飞行；起点即元素定位点 */
  offset-path: var(--sw-path);
  offset-rotate: auto;
  animation: pet-sword-swarm var(--sw-dur, 1.7s) cubic-bezier(0.32, 0.02, 0.5, 1) forwards;
}

/* 剑刃：细长光锥，指向飞行方向 */
.pet-sword-blade {
  position: absolute;
  left: 0;
  top: 0;
  width: 26px;
  height: 2.5px;
  margin: -1.25px 0 0 -2px;
  border-radius: 2px 50% 50% 2px;
  background: linear-gradient(90deg, transparent 0%, var(--spell-glow, #6f9dff) 30%, #ffffff 100%);
  box-shadow: 0 0 8px var(--spell-glow, #6f9dff), 0 0 16px var(--spell-glow, #6f9dff);
}

/* 剑柄：短一截的暗色基座 */
.pet-sword-hilt {
  position: absolute;
  left: 0;
  top: 0;
  width: 8px;
  height: 3px;
  margin: -1.5px 0 0 -8px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--spell-glow, #6f9dff) 70%, #ffffff 30%);
  box-shadow: 0 0 6px var(--spell-glow, #6f9dff);
}

/* 沿曲线外刺并归巢：起止均在宠物本体（曲线闭合），中途飞远 */
@keyframes pet-sword-swarm {
  0% { opacity: 0; offset-distance: 0%; scale: 0.6; }
  12% { opacity: 1; }
  50% { offset-distance: 50%; scale: 1.15; }
  90% { opacity: 1; }
  100% { opacity: 0; offset-distance: 100%; scale: 0.5; }
}

/* 剑阵起势：脚下的剑意光环 */
.pet-spell-swarm-sigil {
  position: fixed;
  z-index: 3099;
  pointer-events: none;
  width: 0;
  height: 0;
  border-radius: 50%;
  border: 1.5px dashed transparent;
  animation: pet-swarm-sigil 1.6s ease-out forwards;
}

@keyframes pet-swarm-sigil {
  0% { opacity: 0; width: 0; height: 0; margin: 0; }
  20% { opacity: 1; width: 70px; height: 70px; margin: -35px 0 0 -35px; }
  100% { opacity: 0; width: 190px; height: 190px; margin: -95px 0 0 -95px; }
}

/* 归位瞬间的中心聚光 */
.pet-spell-swarm-core {
  position: fixed;
  z-index: 3100;
  pointer-events: none;
  width: 90px;
  height: 90px;
  margin: -45px 0 0 -45px;
  border-radius: 50%;
  opacity: 0;
  animation: pet-swarm-core 0.9s ease-out forwards;
}

@keyframes pet-swarm-core {
  0% { opacity: 0; transform: scale(1.6); }
  35% { opacity: 1; transform: scale(0.9); }
  100% { opacity: 0; transform: scale(0.3); }
}
</style>
