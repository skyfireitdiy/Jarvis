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
              <!-- 列表项操作按钮（重命名/复制/权限/重生/删除）已移至 Ctrl+P 命令面板，此处不再显示 -->
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
            <!-- 列表项操作按钮（重命名/复制/权限/重生/删除）已移至 Ctrl+P 命令面板，此处不再显示 -->
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
      v-show="petVisible"
      class="pet-float"
      :class="petClasses"
      :style="{ left: petPos.x + 'px', top: petPos.y + 'px' }"
      aria-hidden="true"
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
        <div class="pet-zzz z1">z</div>
        <div class="pet-zzz z2">z</div>
        <div class="pet-zzz z3">Z</div>
        <div
          v-if="petBadgeText"
          class="pet-badge"
          :class="{ 'is-alert': petWaitingAgents.length > 0 }"
          :title="petWaitingAgents.length > 0 ? (petWaitingAgents.length + ' 个 Agent 等待输入') : (petRunningCount + ' 个 Agent 运行中')"
        >{{ petBadgeText }}</div>
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

    <!-- 宠物旁的迷你网络拓扑 -->
    <PetMiniTopology
      v-show="petVisible && petTopoOn"
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
    >🐾</button>
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
import PetMiniTopology from './PetMiniTopology.vue'

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
  nodes: { type: Array, default: () => [] },
  currentUserId: { type: String, default: '' },
  currentUserName: { type: String, default: '' },
  isConnected: { type: Boolean, default: true }
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
  'petSyncStatus',
  'petInterruptCurrent',
  'petGotoWaiting',
  'petToggleSidebar',
  'petOpenTopology',
  'petOpenCommandPalette',
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
const PET_TOPO_KEY = 'jarvis_pet_topo'
const PET_RESTORE_POS_KEY = 'jarvis_pet_restore_pos'
const PET_HIDDEN_KEY = 'jarvis_pet_hidden'
const PET_W = 200
const PET_H = 230
const RESTORE_W = 40
const RESTORE_H = 40
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

// 气泡文本：等待输入优先，其次随机台词
const petBubbleText = computed(() => {
  if (petState.value === 'waiting') return '需要输入'
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
  },
  petAction.value ? 'act-' + petAction.value : '',
])

// 是否正在看迷你拓扑图（开着且宠物可见/清醒）
const petWatchingTopo = computed(() => petTopoOn.value && !petHidden.value && !petSleep.value)

// 迷你图水平方向相对宠物中心的偏移：-1 左 / 0 中 / 1 右
const petTopoDirX = computed(() => {
  const headCx = petPos.value.x + PET_W / 2
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
  const topX = petPos.value.x + PET_W / 2 - MINI / 2
  const topY = petPos.value.y - MINI - 6
  if (topY >= 4) return { x: clampX(topX), y: topY }

  // 回退1：宠物下方居中
  const belowY = petPos.value.y + PET_H + 6
  if (belowY <= maxY) return { x: clampX(topX), y: belowY }

  // 回退2：宠物右侧
  const sideX = petPos.value.x + PET_W + 6
  const sideY = petPos.value.y + PET_H / 2 - MINI / 2
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
  const maxX = Math.max(0, window.innerWidth - PET_W)
  const maxY = Math.max(0, window.innerHeight - PET_H)
  return { x: Math.max(0, Math.min(maxX, x)), y: Math.max(0, Math.min(maxY, y)) }
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
    rect.left + (rect.width - PET_W) / 2,
    window.innerHeight - PET_H - 8
  )
}

let petRaf = 0
function onPetMouseMove(e) {
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
let petLongPressTimer = 0  // 长按判定
let petSpeechTimer = 0   // 台词气泡
let petHideTimer = 0     // 隐藏定时器（兼容保留）
let petLongPressFired = false  // 本次长按已触发
let petPettingFxTimer = 0      // 摸头爱心循环

function onPetPointerDown(e) {
  if (e.button !== undefined && e.button !== 0) return  // 仅左键
  stopPetWalk()
  petDragging = true
  petMoved = false
  petLongPressFired = false
  petStartX = e.clientX
  petStartY = e.clientY
  petOriginX = petPos.value.x
  petOriginY = petPos.value.y
  e.target.setPointerCapture?.(e.pointerId)
  e.preventDefault()
  // 长按判定：600ms 未移动则触发摸头
  clearTimeout(petLongPressTimer)
  petLongPressTimer = window.setTimeout(() => {
    if (petDragging && !petMoved) {
      petLongPressFired = true
      startPetting()
    }
  }, 600)
}

function onPetPointerMove(e) {
  if (!petDragging) return
  const dx = e.clientX - petStartX
  const dy = e.clientY - petStartY
  if (!petMoved && Math.hypot(dx, dy) > 5) {
    petMoved = true
    petDrag.value = true
    // 拖拽开始则取消长按
    clearTimeout(petLongPressTimer)
    if (petPetting.value) stopPetting()
  }
  if (petMoved) {
    petPos.value = clampPetPos(petOriginX + dx, petOriginY + dy)
  }
}

function onPetPointerUp(e) {
  if (!petDragging) return
  petDragging = false
  clearTimeout(petLongPressTimer)
  e.target.releasePointerCapture?.(e.pointerId)
  if (petMoved) {
    petDrag.value = false
    savePetPos()
    return
  }
  petDrag.value = false
  // 长按已触发：结束摸头，不再触发单击/双击
  if (petLongPressFired) {
    petLongPressFired = false
    stopPetting()
    return
  }
  // 单击 / 双击判定
  if (petClickTimer) {
    // 300ms 内第二次：双击
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
    petSleep.value = false
    petSfxChirp()
    return
  }
  petJump.value = true
  setTimeout(() => { petJump.value = false }, 560)
  spawnPetFx(x, y)
  petSfxChirp()
  showPetSpeech()
}

// 双击：撒花庆祝，并唤起命令面板
function onPetDoubleClick(x, y) {
  if (petSleep.value) petSleep.value = false
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
  if (petSleep.value) petSleep.value = false
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
  const r = el ? el.getBoundingClientRect() : { left: petPos.value.x, top: petPos.value.y, width: PET_W, height: PET_H }
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
  if (petSleep.value) petSleep.value = false
  const el = document.querySelector('.pet-float')
  const r = el ? el.getBoundingClientRect() : { left: petPos.value.x, top: petPos.value.y, width: PET_W, height: PET_H }
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
  if (petSleep.value) petSleep.value = false
  const el = document.querySelector('.pet-float')
  const r = el ? el.getBoundingClientRect() : { left: petPos.value.x, top: petPos.value.y, width: PET_W, height: PET_H }
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
function togglePetSleep() {
  petSleep.value = !petSleep.value
  if (petSleep.value) {
    petSpeech.value = ''
    petSfxYawn()
  } else {
    petSfxChirp()
  }
}

// 唱歌：音符飘出 + 音阶
function petSing() {
  if (petSleep.value) petSleep.value = false
  const el = document.querySelector('.pet-float')
  const r = el ? el.getBoundingClientRect() : { left: petPos.value.x, top: petPos.value.y, width: PET_W, height: PET_H }
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
let restoreStartX = 0
let restoreStartY = 0
let restoreOriginX = 0
let restoreOriginY = 0

function onRestorePointerDown(e) {
  if (e.button !== undefined && e.button !== 0) return  // 仅左键
  restoreDragging = true
  restoreMoved = false
  restoreStartX = e.clientX
  restoreStartY = e.clientY
  restoreOriginX = restorePos.value.x
  restoreOriginY = restorePos.value.y
  e.target.setPointerCapture?.(e.pointerId)
  e.preventDefault()
}

function onRestorePointerMove(e) {
  if (!restoreDragging) return
  const dx = e.clientX - restoreStartX
  const dy = e.clientY - restoreStartY
  if (!restoreMoved && Math.hypot(dx, dy) > 5) restoreMoved = true
  if (restoreMoved) {
    restorePos.value = clampRestorePos(restoreOriginX + dx, restoreOriginY + dy)
  }
}

function onRestorePointerUp(e) {
  if (!restoreDragging) return
  restoreDragging = false
  e.target.releasePointerCapture?.(e.pointerId)
  if (restoreMoved) {
    restoreUserMoved = true
    saveRestorePos()
  } else {
    showPet()
  }
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

// 折叠所有可折叠分组
function petCollapseAll() {
  const map = { ...collapsedGroupsMap.value }
  ;(props.displayGroups || []).forEach(g => {
    if (g.isCollapsible) map[g.key] = true
  })
  collapsedGroupsMap.value = map
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
const PET_ACTIONS = ['look', 'yawn', 'spin', 'hop', 'throw']
// 随机趣味行为：偶尔自发喂食/玩球/唱歌/打盹（不再由菜单触发）
const PET_FUN_ACTIONS = [petFeed, petPlayBall, petSing, togglePetSleep]
let petActTimer = 0
function schedulePetAction() {
  clearTimeout(petActTimer)
  petActTimer = window.setTimeout(() => {
    if (!document.hidden && !petHover.value && !petDrag.value && !petSleep.value && !petHidden.value && !petPetting.value && !petWalking.value) {
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
  petPos.value = clampPetPos(petPos.value.x, petPos.value.y)
}

// ==================== 随机漫步 ====================
let petWanderTimer = 0   // 下次醒来的时间
let petWanderRaf = 0     // 漫步动画帧
// 当前是否可自由漫步：未拖拽/悬停/睡眠/隐藏/摸头，且页面可见
function canPetWander() {
  return !document.hidden && !petHover.value && !petDrag.value &&
    !petSleep.value && !petHidden.value && !petPetting.value && !petWalking.value
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
  const maxX = Math.max(0, window.innerWidth - PET_W)
  const maxY = Math.max(0, window.innerHeight - PET_H)
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
  const dur = Math.max(1600, Math.min(6000, dist * 11))
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
  stopPetWalk()
  if (petRaf) {
    cancelAnimationFrame(petRaf)
    petRaf = 0
  }
  document.removeEventListener('mousemove', onPetMouseMove)
}

// 宠物重新显示时重启常驻运算（幂等：已在运行时不会重复启动）
function startPetLoops() {
  if (!petActTimer) schedulePetAction()
  if (!petWanderTimer) schedulePetWander()
  document.addEventListener('mousemove', onPetMouseMove)
}

onMounted(() => {
  initPetPos()
  initRestorePos()
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
  document.addEventListener('mousemove', onPetMouseMove)
  window.addEventListener('resize', onPetResize)
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

onUnmounted(() => {
  document.removeEventListener('mousemove', onPetMouseMove)
  window.removeEventListener('resize', onPetResize)
  clearTimeout(petActTimer)
  clearTimeout(petClickTimer)
  clearTimeout(petLongPressTimer)
  clearTimeout(petSpeechTimer)
  clearTimeout(petHideTimer)
  clearInterval(petPettingFxTimer)
  clearTimeout(petWanderTimer)
  if (petRaf) cancelAnimationFrame(petRaf)
  if (petWanderRaf) cancelAnimationFrame(petWanderRaf)
})

defineExpose({
  togglePet,
  hidePet: petHide,
  showPet,
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
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(-13px);
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
    transform: translateX(-50%) scaleX(var(--pet-flip, 1)) translateY(-26px) scale(0.94, 1.08);
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


</style>

<!-- 动态特效元素（append 到 body，需非 scoped 样式） -->
<style>
.pet-fx,
.pet-confetti,
.pet-heart-fx,
.pet-food,
.pet-ball,
.pet-note {
  position: fixed;
  z-index: 3100;
  pointer-events: none;
  user-select: none;
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

</style>