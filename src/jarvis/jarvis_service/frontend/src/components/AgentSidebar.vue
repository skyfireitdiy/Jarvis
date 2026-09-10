<template>
  <aside
    class="agent-sidebar"
    :class="{ collapsed: !visible, 'agent-sidebar-resizing': resizeState.active }"
    :style="sidebarStyle"
  >
    <div class="agent-sidebar-header">
      <h3>Agent 列表</h3>
      <div class="sidebar-header-actions">
        <button class="icon-btn" :class="{ active: isBatchMode }" @click="$emit('toggleBatchMode')" title="批量选择模式">☑</button>
        <button class="icon-btn" @click="$emit('createAgent')" title="创建新 Agent">➕</button>
        <button class="icon-btn" @click="$emit('close')" title="关闭侧边栏">✕</button>
      </div>
    </div>
    <div class="agent-list">
      <div class="hello-user-banner" aria-hidden="true">
        <span class="hello-user-glow">Hello, {{ currentUserName || '' }}</span>
        <span class="hello-user-sub">✦ 你好，{{ currentUserName || '' }} ✦</span>
      </div>
      <template v-for="agentGroup in displayGroups" :key="agentGroup.key">
        <div v-if="agentGroup.isCollapsible && agentGroup.agents.length > 0" class="agent-collapsed-section">
          <button
            class="agent-collapsed-toggle"
            :class="{
              'group-waiting-unread': hasUnreadWaitingAgent(agentGroup.agents),
              'group-waiting-clicked': hasClickedWaitingAgent(agentGroup.agents)
            }"
            @click="toggleGroupCollapse(agentGroup.key)"
          >
            <span class="agent-collapsed-arrow">{{ isGroupCollapsed(agentGroup.key) ? '▶' : '▼' }}</span>
            <span class="agent-collapsed-title">{{ agentGroup.title }}</span>
            <span class="agent-collapsed-count">({{ agentGroup.agents.filter(a => getStatusClass(a) !== 'stopped').length }}/{{ agentGroup.agents.length }})</span>
          </button>
          <div v-if="!isGroupCollapsed(agentGroup.key)">
            <div
              v-for="agent in agentGroup.agents"
              :key="agent.agent_id"
              class="agent-item"
              :class="{ active: currentAgentId === agent.agent_id, selected: isSelected(agent.agent_id), 'waiting-input': isWaitingInput(agent), 'waiting-input-unread': isWaitingInput(agent) && !clickedWaitingAgents.has(agent.agent_id) }"
              @click="handleAgentClick(agent, $event)"
            >
              <div v-if="isBatchMode" class="agent-checkbox" @click.stop>
                <input type="checkbox" :checked="isSelected(agent.agent_id)" @change="$emit('toggleSelectAgent', agent.agent_id)">
              </div>
              <div class="agent-info">
                <span class="agent-type-icon" :title="agent.agent_type">{{ agent.agent_type === 'code_agent' ? '💻' : '🤖' }}</span>
                <span class="agent-name">{{ agent.name }}</span>
                <span class="agent-status-dot" :class="getStatusClass(agent)" :title="getStatusText(agent)"></span>
              </div>
              <div class="agent-dir-line">
                <span class="agent-dir" :title="agent.working_dir">{{ agent.working_dir }}</span>
                <span class="agent-meta-tag">📍 {{ getNodeLabel(agent) }}</span>
                <span class="agent-meta-tag" v-if="agent.proxy_node">🔀 {{ getProxyNodeLabel(agent) }}</span>
                <span class="agent-meta-tag" v-if="agent.llm_group">🧠 {{ agent.llm_group }}</span>
                <span class="agent-meta-tag" v-if="agent.worktree">🌿</span>
                <span class="agent-meta-tag" v-if="agent.quick_mode">⚡</span>
              </div>
              <div class="agent-item-actions">
                <button class="icon-btn-small" @click.stop="$emit('renameAgent', agent)" title="重命名">✏</button>
                <button class="icon-btn-small" @click.stop="$emit('copyAgent', agent)" title="复制 Agent">📋</button>
                <button v-if="agent.owner_id === currentUserId" class="icon-btn-small" @click.stop="$emit('editAccess', agent)" title="权限管理">🔒</button>
                <button v-if="agent.owner_id === currentUserId" class="icon-btn-small" @click.stop="$emit('regenerateAgent', agent)" title="无损重生">🔄</button>
                <button class="icon-btn-small stop-btn" @click.stop="$emit('deleteAgent', agent.agent_id)" title="删除 Agent">🗑</button>
              </div>
            </div>
          </div>
        </div>
        <template v-else>
          <div
            v-for="agent in agentGroup.agents"
            :key="agent.agent_id"
            class="agent-item"
            :class="{ active: currentAgentId === agent.agent_id, selected: isSelected(agent.agent_id), 'waiting-input': isWaitingInput(agent), 'waiting-input-unread': isWaitingInput(agent) && !clickedWaitingAgents.has(agent.agent_id) }"
            @click="handleAgentClick(agent, $event)"
          >
            <div v-if="isBatchMode" class="agent-checkbox" @click.stop>
              <input type="checkbox" :checked="isSelected(agent.agent_id)" @change="$emit('toggleSelectAgent', agent.agent_id)">
            </div>
            <div class="agent-info">
              <span class="agent-type-icon" :title="agent.agent_type">{{ agent.agent_type === 'code_agent' ? '💻' : '🤖' }}</span>
              <span class="agent-name">{{ agent.name }}</span>
              <span class="agent-status-dot" :class="getStatusClass(agent)" :title="getStatusText(agent)"></span>
            </div>
            <div class="agent-dir-line">
              <span class="agent-dir" :title="agent.working_dir">{{ agent.working_dir }}</span>
              <span class="agent-meta-tag">📍 {{ getNodeLabel(agent) }}</span>
              <span class="agent-meta-tag" v-if="agent.proxy_node">🔀 {{ getProxyNodeLabel(agent) }}</span>
              <span class="agent-meta-tag" v-if="agent.llm_group">🧠 {{ agent.llm_group }}</span>
              <span class="agent-meta-tag" v-if="agent.worktree">🌿</span>
              <span class="agent-meta-tag" v-if="agent.quick_mode">⚡</span>
            </div>
            <div class="agent-item-actions">
              <button class="icon-btn-small" @click.stop="$emit('renameAgent', agent)" title="重命名">✏</button>
              <button class="icon-btn-small" @click.stop="$emit('copyAgent', agent)" title="复制 Agent">📋</button>
              <button v-if="agent.owner_id === currentUserId" class="icon-btn-small" @click.stop="$emit('editAccess', agent)" title="权限管理">🔒</button>
              <button v-if="agent.owner_id === currentUserId" class="icon-btn-small" @click.stop="$emit('regenerateAgent', agent)" title="无损重生">🔄</button>
              <button class="icon-btn-small stop-btn" @click.stop="$emit('deleteAgent', agent.agent_id)" title="删除 Agent">🗑</button>
            </div>
          </div>
        </template>
      </template>
      <!-- 批量操作按钮栏 -->
      <div v-if="isBatchMode && agentList.length > 0" class="batch-actions-bar">
        <div class="batch-actions-info">
          已选 {{ selectedCount }} 个
        </div>
        <div class="batch-actions-buttons">
          <button class="icon-btn-small" @click="$emit('toggleSelectAll')" :title="isAllSelected ? '取消全选' : '全选'">
            {{ isAllSelected ? '⬜' : '☑' }}
          </button>
          <button class="icon-btn-small" @click="$emit('batchCopy')" title="批量复制">
            📋
          </button>
          <button class="icon-btn-small" @click="openGroupModal" title="加入分组">
            📁
          </button>
          <button class="icon-btn-small stop-btn" @click="$emit('batchDelete')" title="批量删除">
            🗑
          </button>
          <button class="icon-btn-small" @click="$emit('toggleBatchMode')" title="退出批量模式">
            ✕
          </button>
        </div>
      </div>
      <div v-if="agentList.length === 0" class="agent-empty">
        暂无 Agent，点击 + 创建
      </div>
    </div>
    <div
      v-if="visible && windowWidth > 768"
      class="agent-sidebar-resize-handle"
      @mousedown="$emit('startResize', $event)"
    ></div>
  </aside>

  <!-- 宠物挂件：浮动于页面，可拖拽并记忆位置 -->
  <Teleport to="body">
    <div
      class="pet-float"
      :class="petClasses"
      :style="{ left: petPos.x + 'px', top: petPos.y + 'px' }"
      aria-hidden="true"
    >
      <div class="pet-inner">
        <div class="pet-glow"></div>
        <div class="pet-bubble">需要输入</div>
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
        <div class="pet-label">✦ JARVIS ✦</div>
        <button
          class="pet-sfx-btn"
          :class="{ 'is-off': !petSfxOn }"
          :title="petSfxOn ? '关闭宠物音效' : '开启宠物音效'"
          @click.stop="togglePetSfx"
        >{{ petSfxOn ? '🔊' : '🔇' }}</button>
        <div
          class="pet-hit"
          @pointerdown="onPetPointerDown"
          @pointermove="onPetPointerMove"
          @pointerup="onPetPointerUp"
          @pointercancel="onPetPointerUp"
          @mouseenter="petHover = true"
          @mouseleave="petHover = false"
        ></div>
      </div>
    </div>
  </Teleport>

  <!-- 加入分组弹窗 -->
  <Teleport to="body">
    <div v-if="showGroupModal" class="group-modal-overlay" @click.self="closeGroupModal">
      <div class="group-modal">
        <div class="group-modal-header">
          <span>加入分组</span>
          <button class="icon-btn-small" @click="closeGroupModal" title="关闭">✕</button>
        </div>
        <div v-if="agentGroups.length === 0" class="agent-group-empty">暂无分组，请先创建</div>
        <div
          v-for="group in agentGroups"
          :key="group.id"
          class="agent-group-item"
          @click="selectGroup(group.id)"
        >
          <span class="agent-group-item-name">📁 {{ group.name }}</span>
          <span class="agent-group-item-count">({{ group.agentIds?.length || 0 }})</span>
        </div>
        <div class="agent-group-create">
          <input
            v-model="newGroupName"
            class="agent-group-create-input"
            placeholder="新建分组名称"
            @keyup.enter="handleCreateGroup"
          />
          <button class="icon-btn-small" @click="handleCreateGroup" title="创建分组">➕</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, defineProps, defineEmits, onMounted, onUnmounted } from 'vue'

// 分组折叠状态管理 - 使用对象存储，避免 Set 响应式问题
const collapsedGroupsMap = ref({})

// 追踪已点击过的等待输入Agent - 从localStorage恢复状态
const CLICKED_WAITING_STORAGE_KEY = 'jarvis_clicked_waiting_agents'

// 从localStorage加载已点击状态
function loadClickedWaitingAgents() {
  try {
    const stored = localStorage.getItem(CLICKED_WAITING_STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored)
      return new Set(Array.isArray(parsed) ? parsed : [])
    }
  } catch (e) {
    console.warn('[AGENT_SIDEBAR] Failed to load clicked waiting agents:', e)
  }
  return new Set()
}

// 保存已点击状态到localStorage
function saveClickedWaitingAgents(set) {
  try {
    localStorage.setItem(CLICKED_WAITING_STORAGE_KEY, JSON.stringify([...set]))
  } catch (e) {
    console.warn('[AGENT_SIDEBAR] Failed to save clicked waiting agents:', e)
  }
}

const clickedWaitingAgents = ref(loadClickedWaitingAgents())

function isGroupCollapsed(groupKey) {
  return !!collapsedGroupsMap.value[groupKey]
}

function toggleGroupCollapse(groupKey) {
  if (collapsedGroupsMap.value[groupKey]) {
    collapsedGroupsMap.value[groupKey] = false
  } else {
    collapsedGroupsMap.value[groupKey] = true
  }
}

// 处理Agent点击事件，记录点击状态
function handleAgentClick(agent, event) {
  // 如果是等待输入状态，记录点击
  if (props.isWaitingInput(agent)) {
    clickedWaitingAgents.value.add(agent.agent_id)
    // 持久化到localStorage
    saveClickedWaitingAgents(clickedWaitingAgents.value)
    // 触发响应式更新
    clickedWaitingAgents.value = new Set(clickedWaitingAgents.value)
  }
  // 触发父组件的点击事件
  emit('agentClick', agent, event)
}

// 判断组内是否有未点击的等待输入Agent（闪烁）
function hasUnreadWaitingAgent(agents) {
  return agents.some(agent =>
    props.isWaitingInput(agent) && !clickedWaitingAgents.value.has(agent.agent_id)
  )
}

// 判断组内是否有已点击的等待输入Agent（背景色）
function hasClickedWaitingAgent(agents) {
  return agents.some(agent =>
    props.isWaitingInput(agent) && clickedWaitingAgents.value.has(agent.agent_id)
  )
}

const props = defineProps({
  visible: Boolean,
  resizeState: Object,
  sidebarStyle: Object,
  isBatchMode: Boolean,
  displayGroups: Array,
  currentAgentId: String,
  selectedCount: Number,
  agentList: Array,
  windowWidth: Number,
  isAllSelected: Boolean,
  agentStatuses: Map,  // Agent状态映射 (agent_id -> {execution_status})
  getStatusClass: Function,
  getStatusText: Function,
  getNodeLabel: Function,
  getProxyNodeLabel: Function,
  isSelected: Function,
  isWaitingInput: Function,
  agentGroups: { type: Array, default: () => [] },
  currentUserId: { type: String, default: '' },
  currentUserName: { type: String, default: '' }
})

// 分组弹窗状态
const showGroupModal = ref(false)
const newGroupName = ref('')

function openGroupModal() {
  newGroupName.value = ''
  showGroupModal.value = true
}

function closeGroupModal() {
  showGroupModal.value = false
}

function selectGroup(groupId) {
  emit('addToGroup', groupId)
  closeGroupModal()
}

function handleCreateGroup() {
  const name = newGroupName.value.trim()
  if (!name) return
  emit('createGroupWithAgents', name)
  newGroupName.value = ''
  closeGroupModal()
}

// 初始化时折叠所有分组 - 只在首次初始化时设置，避免后续数据更新覆盖用户操作
watch(() => props.displayGroups, (newGroups) => {
  if (!newGroups || newGroups.length === 0) return
  // 只在 collapsedGroupsMap 为空时初始化折叠状态
  if (Object.keys(collapsedGroupsMap.value).length === 0) {
    newGroups.forEach(group => {
      if (group.isCollapsible) {
        collapsedGroupsMap.value[group.key] = true
      }
    })
  }
}, { immediate: true })

const emit = defineEmits([
  'close',
  'toggleBatchMode',
  'createAgent',
  'agentClick',
  'toggleSelectAgent',
  'renameAgent',
  'copyAgent',
  'deleteAgent',
  'toggleSelectAll',
  'batchCopy',
  'batchDelete',
  'addToGroup',
  'createGroupWithAgents',
  'startResize',
  'editAccess',
  'regenerateAgent',
])

// 监听 agentStatuses 变化，当 agent 状态从等待输入变为非等待输入时清除点击标记
// 使用 ref 来跟踪上一次的状态
const previousStatusMap = ref(new Map())

watch(() => props.agentStatuses, (newStatuses) => {
  if (!newStatuses) return

  // 遍历所有 agent，检查状态变化
  props.agentList?.forEach(agent => {
    const agentId = agent.agent_id
    const currentStatus = newStatuses.get(agentId)
    const previousStatus = previousStatusMap.value.get(agentId)

    // 如果当前状态存在
    if (currentStatus) {
      const executionStatus = currentStatus.execution_status
      const isWaiting = executionStatus === 'waiting_multi' || executionStatus === 'waiting_single' || executionStatus === 'waiting_confirm'

      // 如果之前是等待输入状态，现在不是了，清除点击标记
      if (previousStatus) {
        const prevExecutionStatus = previousStatus.execution_status
        const wasWaiting = prevExecutionStatus === 'waiting_multi' || prevExecutionStatus === 'waiting_single' || prevExecutionStatus === 'waiting_confirm'

        if (wasWaiting && !isWaiting) {
          if (clickedWaitingAgents.value.has(agentId)) {
            clickedWaitingAgents.value.delete(agentId)
            // 持久化到localStorage
            saveClickedWaitingAgents(clickedWaitingAgents.value)
            // 触发响应式更新
            clickedWaitingAgents.value = new Set(clickedWaitingAgents.value)
          }
        }
      }

      // 更新上一次的状态
      previousStatusMap.value.set(agentId, { ...currentStatus })
    }
  })
}, { deep: true })

// 监听currentAgentId变化，自动展开对应节点分组
watch(() => props.currentAgentId, (newAgentId) => {
  if (!newAgentId || !props.agentList) return

  const agent = props.agentList.find(a => a.agent_id === newAgentId)
  if (!agent) return

  // 获取节点标签
  const nodeLabel = props.getNodeLabel(agent)
  const groupKey = `node-${nodeLabel}`

  // 如果该分组是折叠的，则展开它
  if (collapsedGroupsMap.value[groupKey]) {
    collapsedGroupsMap.value[groupKey] = false
  }
})
// ==================== 宠物挂件 ====================
const PET_POS_KEY = 'jarvis_pet_pos'
const PET_W = 200
const PET_H = 230

const petPos = ref({ x: 0, y: 0 })
const petHover = ref(false)
const petDrag = ref(false)
const petJump = ref(false)
const petAction = ref('')
const petPupil = ref({ x: 0, y: 0 })
const petTilt = ref(0)

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

const petClasses = computed(() => [
  'is-' + petState.value,
  {
    'is-hover': petHover.value,
    'is-drag': petDrag.value,
    'is-jump': petJump.value,
  },
  petAction.value ? 'act-' + petAction.value : '',
])

const petPupilStyle = computed(() => ({
  transform: `translate(calc(-50% + ${petPupil.value.x}px), calc(-50% + ${petPupil.value.y}px))`,
}))

const petHeadStyle = computed(() => {
  if (petHover.value || petDrag.value) return {}
  return { transform: `translateX(-50%) rotate(${petTilt.value}deg)` }
})

function clampPetPos(x, y) {
  const maxX = Math.max(0, window.innerWidth - PET_W)
  const maxY = Math.max(0, window.innerHeight - PET_H)
  return { x: Math.max(0, Math.min(maxX, x)), y: Math.max(0, Math.min(maxY, y)) }
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
    rect.left + (rect.width - PET_W) / 2,
    window.innerHeight - PET_H - 8
  )
}

let petRaf = 0
function onPetMouseMove(e) {
  if (petRaf) return
  petRaf = requestAnimationFrame(() => {
    petRaf = 0
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
let petLastClick = 0

function onPetPointerDown(e) {
  petDragging = true
  petMoved = false
  petStartX = e.clientX
  petStartY = e.clientY
  petOriginX = petPos.value.x
  petOriginY = petPos.value.y
  e.target.setPointerCapture?.(e.pointerId)
  e.preventDefault()
}

function onPetPointerMove(e) {
  if (!petDragging) return
  const dx = e.clientX - petStartX
  const dy = e.clientY - petStartY
  if (!petMoved && Math.hypot(dx, dy) > 5) {
    petMoved = true
    petDrag.value = true
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
    savePetPos()
    return
  }
  petDrag.value = false
  const now = Date.now()
  if (now - petLastClick < 280) return
  petLastClick = now
  petJump.value = true
  setTimeout(() => { petJump.value = false }, 560)
  spawnPetFx(e.clientX, e.clientY)
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

// ==================== 宠物音效（Web Audio 合成，无外部资源） ====================
const PET_SFX_KEY = 'jarvis_pet_sfx'
const petSfxOn = ref(true)

let petAudioCtx = null
function getPetAudioCtx() {
  if (typeof window === 'undefined') return null
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

// 随机小动作
const PET_ACTIONS = ['look', 'yawn', 'spin', 'hop']
let petActTimer = 0
function schedulePetAction() {
  petActTimer = window.setTimeout(() => {
    if (!document.hidden && !petHover.value && !petDrag.value) {
      const act = PET_ACTIONS[Math.floor(Math.random() * PET_ACTIONS.length)]
      petAction.value = act
      petSfxAction(act)
      setTimeout(() => { petAction.value = '' }, 1700)
    }
    schedulePetAction()
  }, 5000 + Math.random() * 7000)
}

function onPetResize() {
  petPos.value = clampPetPos(petPos.value.x, petPos.value.y)
}

onMounted(() => {
  initPetPos()
  try {
    petSfxOn.value = localStorage.getItem(PET_SFX_KEY) !== '0'
  } catch (e) {
    petSfxOn.value = true
  }
  document.addEventListener('mousemove', onPetMouseMove)
  window.addEventListener('resize', onPetResize)
  schedulePetAction()
})

onUnmounted(() => {
  document.removeEventListener('mousemove', onPetMouseMove)
  window.removeEventListener('resize', onPetResize)
  clearTimeout(petActTimer)
  if (petRaf) cancelAnimationFrame(petRaf)
})

</script>

<style scoped>
.icon-btn {
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius);
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  color: var(--color-text-secondary);
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-btn:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
  transform: translateY(-1px);
}

.icon-btn:active:not(:disabled) {
  transform: translateY(0);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon-btn.active {
  background: var(--color-accent-subtle);
  color: var(--color-accent);
  border-color: var(--color-border-active);
}

.agent-sidebar {
  position: relative;
  width: 320px;
  min-width: 0;
  background: var(--color-bg-secondary);
  border-right: 0.5px solid var(--color-border-subtle);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.agent-sidebar.collapsed {
  width: 0;
  border-right: none;
  overflow: hidden;
}

.agent-sidebar-resizing {
  user-select: none;
}

.agent-sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: -4px;
  width: 8px;
  height: 100%;
  cursor: ew-resize;
  z-index: 5;
}

.agent-sidebar-resize-handle::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 2px;
  transform: translateX(-50%);
  background: transparent;
  transition: background 0.15s ease;
}

.agent-sidebar-resize-handle:hover::after,
.agent-sidebar-resizing .agent-sidebar-resize-handle::after {
  background: var(--color-accent-glow);
}

.agent-sidebar-header {
  padding: 12px;
  border-bottom: 0.5px solid var(--color-border-subtle);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--color-bg-tertiary);
}

.sidebar-header-actions {
  display: flex;
  gap: 8px;
}

.agent-sidebar-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 宠物挂件：浮动于页面，可拖拽并记忆位置 */
.pet-float {
  position: fixed;
  z-index: 900;
  width: 200px;
  height: 230px;
  pointer-events: none;
  touch-action: none;
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

.pet-float.is-waiting .pet-bubble {
  opacity: 1;
  transform: translateX(-50%) scale(1);
  animation: pet-bubble-bounce 1s ease-in-out infinite;
}

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

.pet-float.act-hop .pet-body {
  animation: pet-jump 0.6s cubic-bezier(0.3, -0.4, 0.4, 1.4);
}

@keyframes pet-bob {
  0%,
  100% {
    transform: translateX(-50%) translateY(0);
  }
  50% {
    transform: translateX(-50%) translateY(-13px);
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
    transform: translateX(-50%) translateY(0) scale(1, 1);
  }
  30% {
    transform: translateX(-50%) translateY(-26px) scale(0.94, 1.08);
  }
  60% {
    transform: translateX(-50%) translateY(0) scale(1.06, 0.94);
  }
  100% {
    transform: translateX(-50%) translateY(0) scale(1, 1);
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
    transform: translateX(-50%) rotate(0deg) scale(1);
  }
  50% {
    transform: translateX(-50%) rotate(180deg) scale(0.92);
  }
  100% {
    transform: translateX(-50%) rotate(360deg) scale(1);
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

.hello-user-banner {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 14px 8px;
  margin-bottom: 8px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(120, 80, 255, 0.18), rgba(0, 200, 255, 0.18));
  border: 1px solid rgba(150, 120, 255, 0.35);
}

.hello-user-glow {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.5px;
  background: linear-gradient(90deg, #7b5cff, #00d4ff, #ff5cc8, #7b5cff);
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: hello-user-flow 4s linear infinite;
  filter: drop-shadow(0 0 5px rgba(123, 92, 255, 0.45));
}

.hello-user-sub {
  font-size: 11px;
  letter-spacing: 2px;
  color: var(--color-text-secondary, #9aa4b2);
}

@keyframes hello-user-flow {
  0% { background-position: 0% 50%; }
  100% { background-position: 300% 50%; }
}

.agent-collapsed-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-collapsed-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  text-align: left;
}

.agent-collapsed-toggle:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

/* 组内有已点击的等待输入Agent - 背景色 */
.agent-collapsed-toggle.group-waiting-clicked {
  background: rgba(210, 153, 34, 0.35);
}

/* 组内有未点击的等待输入Agent - 呼吸灯闪烁 */
.agent-collapsed-toggle.group-waiting-unread {
  animation: group-breathing 2s ease-in-out infinite;
}

@keyframes group-breathing {
  0%, 100% {
    background: rgba(210, 153, 34, 0.35);
  }
  50% {
    background: rgba(210, 153, 34, 0.65);
  }
}

.agent-collapsed-arrow {
  width: 16px;
  color: var(--color-accent);
}

.agent-collapsed-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.agent-collapsed-count {
  font-size: 12px;
  color: var(--color-text-muted);
}

.agent-item {
  padding: 6px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius-xs);
  cursor: pointer;
  position: relative;
}

.agent-item:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-active);
}

.agent-item.active {
  background: rgba(32, 200, 255, 0.25);
  border-color: var(--color-border-active);
}

.agent-item.selected {
  background: var(--color-accent-subtle);
  border-color: var(--color-border-active);
}

.agent-item.waiting-input {
  background: rgba(210, 153, 34, 0.35);
}

/* 激活+等待输入组合状态 - 使用紫色背景 */
.agent-item.active.waiting-input {
  background: rgba(32, 200, 255, 0.35);
}

/* 未点击的等待输入状态 - 呼吸灯效果 */
.agent-item.waiting-input-unread {
  animation: breathing 2s ease-in-out infinite;
}

@keyframes breathing {
  0%, 100% {
    background: rgba(210, 153, 34, 0.35);
  }
  50% {
    background: rgba(210, 153, 34, 0.65);
  }
}

.agent-checkbox {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}

.agent-checkbox input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--color-accent);
}

.batch-actions-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border-subtle);
  gap: 12px;
}

.batch-actions-info {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.batch-actions-buttons {
  display: flex;
  gap: 8px;
}

.group-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3000;
}

.group-modal {
  width: 320px;
  max-width: 90vw;
  max-height: 70vh;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.group-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.agent-group-empty {
  font-size: 12px;
  color: var(--color-text-muted);
  padding: 4px 0;
}

.agent-group-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px;
  border-radius: var(--tile-radius-xs);
  cursor: pointer;
  transition: background 0.15s ease;
}

.agent-group-item:hover {
  background: var(--color-bg-hover);
}

.agent-group-item-name {
  font-size: 12px;
  color: var(--color-text-primary);
}

.agent-group-item-count {
  font-size: 11px;
  color: var(--color-text-muted);
}

.agent-group-create {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-top: 4px;
}

.agent-group-create-input {
  flex: 1;
  font-size: 12px;
  padding: 4px 6px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-xs);
  color: var(--color-text-primary);
  outline: none;
}

.agent-group-create-input:focus {
  border-color: var(--color-border-active);
}

.agent-item .agent-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--color-bg-hover);
  margin-left: 8px;
}

.agent-item .agent-status.running {
  background: var(--color-accent-subtle);
  color: var(--color-accent);
}

.agent-item .agent-status.stopped {
  background: rgba(54, 255, 124, 0.15);
  color: var(--color-success);
}

.agent-item .agent-status.waiting_multi {
  background: rgba(255, 133, 32, 0.15);
  color: var(--color-warning);
}

.agent-item .agent-status.waiting_single {
  background: rgba(255, 60, 72, 0.15);
  color: var(--color-error);
}

.agent-info {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 2px;
}

.agent-type {
  font-size: 16px;
}

.agent-status {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.agent-status.running {
  background: rgba(54, 255, 124, 0.15);
  color: var(--color-success);
}

.agent-status.stopped {
  background: rgba(255, 60, 72, 0.15);
  color: var(--color-error);
}

.agent-status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-left: 4px;
  flex-shrink: 0;
}

.agent-status-dot.running {
  background: var(--color-success);
  box-shadow: var(--tile-shadow);
}

.agent-status-dot.stopped {
  background: var(--color-error);
  box-shadow: var(--tile-shadow);
}

.agent-status-dot.waiting_multi {
  background: var(--color-warning);
  box-shadow: var(--tile-shadow);
}

.agent-status-dot.waiting_single {
  background: var(--color-warning);
  box-shadow: var(--tile-shadow);
}

.agent-status-dot.waiting_confirm {
  background: var(--color-warning);
  box-shadow: var(--tile-shadow);
}

.agent-llm-group {
  font-size: 10px;
  color: #666;
  background: rgba(138, 163, 184, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
}

.agent-port {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-left: auto;
}

.agent-type-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.agent-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-primary);
  flex-shrink: 0;
}

.agent-dir-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.agent-dir {
  font-size: 10px;
  color: var(--color-text-secondary);
  word-break: break-all;
  line-height: 1.3;
  flex: 1;
  min-width: 0;
}

.agent-item-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  margin-top: 4px;
  justify-content: flex-end;
}

.agent-actions {
  display: flex;
  gap: 3px;
  margin-top: 4px;
  justify-content: flex-end;
}

.icon-btn-small {
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius-xs);
  font-size: 12px;
  cursor: pointer;
  padding: 3px 6px;
  color: var(--color-text-secondary);
  transition: all 0.2s ease;
}

.icon-btn-small:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
  transform: translateY(-1px);
}

.icon-btn-small:active {
  transform: translateY(0);
}

.icon-btn-small:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.agent-actions .icon-btn-small.stop-btn:hover {
  background: rgba(255, 60, 72, 0.15);
  color: var(--color-error);
}

.agent-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  font-size: 14px;
  padding: 20px;
}

.agent-proxy-node-label {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--tile-radius);
  background: rgba(32, 200, 255, 0.1); /* 浅蓝色背景 */
  color: #20c8ff; /* 蓝色文字 */
  border: none;
  margin-left: 4px;
}

.agent-meta-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.agent-node-label {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--tile-radius);
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
  border: none;
  margin-left: 4px;
}
</style>
