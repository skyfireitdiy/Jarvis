<!-- 网络拓扑大图浮层（点击宠物旁迷你图展开） -->
<template>
  <transition name="topo-fade">
    <div v-if="visible" class="topo-overlay" @click.self="close">
      <div class="topo-panel" role="dialog" aria-label="网络拓扑">
        <div class="topo-header">
          <div class="topo-title">
            <span class="topo-title-ico">🗺️</span>
            <span>网络拓扑</span>
            <span class="topo-sub">{{ counts.online }}/{{ counts.nodes }} 节点在线 · {{ counts.agents }} 个 Agent<template v-if="counts.waiting > 0"> · {{ counts.waiting }} 等待输入</template></span>
          </div>
          <button class="topo-close" title="关闭 (Esc)" @click="close">✕</button>
        </div>

        <div class="topo-body" ref="bodyEl" @mousemove="onMove" @mouseleave="hovered = null">
          <!-- 左上角统计卡片 -->
          <div class="topo-stats">
            <div class="topo-stats-title">Agent 概览</div>
            <div class="topo-stats-list">
              <div class="topo-stats-item" :style="{ '--stat-color': AGENT_COLORS.running }">
                <span class="topo-stats-icon">▶</span>
                <span class="topo-stats-label">运行中</span>
                <span class="topo-stats-value">{{ counts.running || 0 }}</span>
              </div>
              <div class="topo-stats-item" :style="{ '--stat-color': AGENT_COLORS.waiting }">
                <span class="topo-stats-icon">⏸</span>
                <span class="topo-stats-label">等待输入</span>
                <span class="topo-stats-value">{{ counts.waiting || 0 }}</span>
              </div>
              <div class="topo-stats-item" :style="{ '--stat-color': AGENT_COLORS.stopped }">
                <span class="topo-stats-icon">⏹</span>
                <span class="topo-stats-label">已停止</span>
                <span class="topo-stats-value">{{ counts.stopped || 0 }}</span>
              </div>
            </div>
            <div class="topo-stats-foot">共 {{ counts.agents || 0 }} 个 Agent</div>
          </div>

          <svg class="topo-svg" :width="W" :height="H" :viewBox="`0 0 ${W} ${H}`">
            <defs>
              <radialGradient id="topo-bg" cx="50%" cy="50%" r="70%">
                <stop offset="0%" stop-color="rgba(32,200,255,0.10)" />
                <stop offset="100%" stop-color="rgba(4,8,16,0)" />
              </radialGradient>
              <filter id="topo-glow" x="-80%" y="-80%" width="260%" height="260%">
                <feGaussianBlur stdDeviation="3" result="b" />
                <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
              <linearGradient id="topo-center-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#ffe89a" />
                <stop offset="100%" stop-color="#f0b429" />
              </linearGradient>
            </defs>

            <rect :width="W" :height="H" fill="url(#topo-bg)" />

            <!-- 连线：master -> 各节点 -->
            <g class="topo-links">
              <line
                v-for="l in lines"
                :key="'L' + l.id"
                :x1="layout.center.x"
                :y1="layout.center.y"
                :x2="l.x"
                :y2="l.y"
                :stroke="l.state === 'offline' ? 'rgba(255,93,108,0.35)' : '#20c8ff'"
                :stroke-opacity="l.state === 'offline' ? 1 : 0.55"
                :stroke-width="l.hot ? 2.4 : 1.6"
                :stroke-dasharray="l.state === 'offline' ? '6 5' : ''"
                class="topo-link"
                :class="{ 'is-hot': l.hot, 'is-flow': l.state !== 'offline' }"
              />
            </g>

            <!-- 连线：节点 -> 其 agent -->
            <g class="topo-agent-links">
              <line
                v-for="al in agentLinks"
                :key="'AL' + al.id"
                :x1="al.x1"
                :y1="al.y1"
                :x2="al.x2"
                :y2="al.y2"
                :stroke="agentColor(al.state)"
                stroke-width="1"
                stroke-dasharray="3 3"
                opacity="0.45"
              />
            </g>

            <!-- 连线：master -> 本机执行面节点（浏览器扩展/本地后台服务），曲线 -->
            <!-- 必须排在节点之前渲染：SVG 无 z-index，后渲染者在上层，否则连线会盖住网关节点 -->
            <g class="topo-links-local">
              <path
                v-for="l in localLinks"
                :key="'LL' + l.id"
                :d="l.d"
                :stroke="l.state === 'offline' ? 'rgba(255,93,108,0.35)' : '#20c8ff'"
                :stroke-opacity="l.state === 'offline' ? 1 : 0.55"
                :stroke-width="l.hot ? 2.4 : 1.6"
                :stroke-dasharray="l.state === 'offline' ? '6 5' : ''"
                class="topo-link"
                :class="{ 'is-hot': l.hot, 'is-flow': l.state !== 'offline' }"
                fill="none"
              />
            </g>

            <!-- Agent 节点（机器人造型；code_agent 带护目镜，已停止的 agent 不绘制） -->
            <g
              v-for="a in agentLayout.agents"
              :key="'A' + a.id"
              class="topo-agent"
              :class="['st-' + a.state, a.type === 'code_agent' ? 'is-code' : 'is-chat']"
              @mouseenter="hovered = a.nodeId"
            >
              <circle v-if="a.state === 'waiting' || a.state === 'running'" :cx="a.x" :cy="a.y" :r="AGENT_R + 4" :stroke="agentColor(a.state)" stroke-width="1" fill="none" class="topo-ring" />
              <circle :cx="a.x" :cy="a.y" :r="AGENT_R + 1" :fill="agentFill(a.state)" :stroke="agentColor(a.state)" stroke-width="1.4" />
              <!-- 机器人头部 -->
              <rect :x="a.x - AGENT_R + 3" :y="a.y - AGENT_R + 4" :width="AGENT_R * 2 - 6" :height="AGENT_R * 2 - 8" rx="4"
                    :fill="agentColor(a.state)" class="topo-bot-head" />
              <!-- 天线 -->
              <line :x1="a.x" :y1="a.y - AGENT_R + 3" :x2="a.x" :y2="a.y - AGENT_R - 1"
                    :stroke="agentColor(a.state)" stroke-width="1.4" />
              <circle :cx="a.x" :cy="a.y - AGENT_R - 2.5" r="1.8" :fill="agentColor(a.state)" />
              <!-- 眼睛：code_agent 用横向护目镜，普通用两圆眼 -->
              <template v-if="a.type === 'code_agent'">
                <rect :x="a.x - AGENT_R + 5" :y="a.y - 3" :width="AGENT_R * 2 - 10" :height="4.4" rx="2.2"
                      fill="#041018" class="topo-goggle" />
              </template>
              <template v-else>
                <circle :cx="a.x - 3.4" :cy="a.y - 0.6" r="1.6" fill="#041018" />
                <circle :cx="a.x + 3.4" :cy="a.y - 0.6" r="1.6" fill="#041018" />
              </template>
              <!-- 嘴/呼吸灯 -->
              <rect :x="a.x - 3" :y="a.y + 4" :width="6" :height="2" rx="1" fill="#041018" opacity="0.75" />
              <text :x="a.labelX" :y="a.labelY" :text-anchor="a.labelAnchor" :dominant-baseline="a.labelBaseline" class="topo-agent-label">{{ agentShort(a.name) }}</text>
            </g>

            <!-- 其余节点（服务器机箱造型） -->
            <g
              v-for="n in nodePoints"
              :key="n.id"
              class="topo-node"
              :class="['st-' + n.state, { 'is-hot': hovered === n.id }]"
              @mouseenter="hovered = n.id"
            >
              <rect v-if="n.state !== 'offline'" :x="n.x - NODE_R - 4" :y="n.y - NODE_R * 0.86 - 4" :width="NODE_R * 2 + 8" :height="NODE_R * 1.72 + 8" rx="9"
                    :stroke="n.color" stroke-width="1.4" fill="none" class="topo-ring" />
              <!-- 机箱主体 -->
              <rect :x="n.x - NODE_R" :y="n.y - NODE_R * 0.86" :width="NODE_R * 2" :height="NODE_R * 1.72" rx="6"
                    :fill="n.fill" :stroke="n.color" stroke-width="1.8" class="topo-server" />
              <!-- 顶部插槽 -->
              <line :x1="n.x - NODE_R + 6" :y1="n.y - NODE_R * 0.86 + 7" :x2="n.x + NODE_R - 6" :y2="n.y - NODE_R * 0.86 + 7"
                    :stroke="n.color" stroke-width="1.4" opacity="0.6" />
              <!-- 散热格栅 -->
              <line v-for="k in 3" :key="'g' + k"
                    :x1="n.x - NODE_R + 8" :y1="n.y - NODE_R * 0.86 + 6 + k * 4.6"
                    :x2="n.x + NODE_R - 16" :y2="n.y - NODE_R * 0.86 + 6 + k * 4.6"
                    :stroke="n.color" stroke-width="1" opacity="0.35" />
              <!-- 指示灯 -->
              <circle :cx="n.x + NODE_R - 10" :cy="n.y - 2" r="2.4" :fill="n.color" class="topo-led" />
              <circle :cx="n.x + NODE_R - 10" :cy="n.y + 5" r="2.4" :fill="n.color" opacity="0.4" />
              <!-- 底部状态条 -->
              <rect :x="n.x - NODE_R + 6" :y="n.y + NODE_R * 0.86 - 8" :width="NODE_R * 2 - 12" :height="3" rx="1.5"
                    :fill="n.color" opacity="0.5" />
              <text :x="n.x" :y="n.y + NODE_R * 0.86 + 16" text-anchor="middle" class="topo-node-label">{{ n.short }}</text>
              <text :x="n.x" :y="n.y + NODE_R * 0.86 + 29" text-anchor="middle" class="topo-node-count">{{ n.drawAgents.length }}/{{ n.agents.length }} agent</text>
            </g>

            <!-- 本机执行面节点（浏览器扩展在左、本地后台服务在右；圆形造型，与服务器机箱明显区分） -->
            <g
              v-for="n in localNodes"
              :key="n.id"
              class="topo-node is-local"
              :class="['st-' + n.state, { 'is-hot': hovered === n.id }]"
              @mouseenter="hovered = n.id"
            >
              <title>{{ n.title }}</title>
              <circle v-if="n.state !== 'offline'" :cx="n.x" :cy="n.y" :r="ACCESS_R + 5"
                      :stroke="n.color" stroke-width="1.4" fill="none" class="topo-ring" />
              <!-- 圆形主体 -->
              <circle :cx="n.x" :cy="n.y" :r="ACCESS_R"
                      :fill="n.fill" :stroke="n.color" stroke-width="1.8" class="topo-server" />
              <!-- 类型图标 -->
              <text :x="n.x" :y="n.y" text-anchor="middle" dominant-baseline="central"
                    class="topo-access-ico">{{ n.icon }}</text>
              <!-- 标签文字：顶部行在节点下方、底部行在节点上方，居中显示，避免被画布边缘裁切 -->
              <text :x="n.x" :y="n.labelAbove ? n.y - ACCESS_R - 16 : n.y + ACCESS_R + 16" :text-anchor="n.anchor" class="topo-node-label">{{ n.short }}</text>
              <text :x="n.x" :y="n.labelAbove ? n.y - ACCESS_R - 29 : n.y + ACCESS_R + 29" :text-anchor="n.anchor" class="topo-node-count">{{ n.sub }}</text>
            </g>

            <!-- 中心 master（与子节点同款服务器机箱，仅靠颜色/尺寸区分主次） -->
            <g class="topo-node is-center" :class="'st-' + model.center.state" @mouseenter="hovered = 'master'">
              <rect v-if="model.center.state !== 'offline'" :x="layout.center.x - CENTER_W / 2 - 5" :y="layout.center.y - CENTER_H / 2 - 5" :width="CENTER_W + 10" :height="CENTER_H + 10" rx="11"
                    :stroke="centerColor" stroke-width="1.4" fill="none" class="topo-ring" />
              <!-- 机箱主体 -->
              <rect :x="layout.center.x - CENTER_W / 2" :y="layout.center.y - CENTER_H / 2" :width="CENTER_W" :height="CENTER_H" rx="7"
                    :fill="centerFill" :stroke="centerColor" stroke-width="2.2" class="topo-server" filter="url(#topo-glow)" />
              <!-- 顶部插槽 -->
              <line :x1="layout.center.x - CENTER_W / 2 + 8" :y1="layout.center.y - CENTER_H / 2 + 9"
                    :x2="layout.center.x + CENTER_W / 2 - 8" :y2="layout.center.y - CENTER_H / 2 + 9"
                    :stroke="centerColor" stroke-width="1.6" opacity="0.7" />
              <!-- 散热格栅 -->
              <line v-for="k in 3" :key="'mg' + k"
                    :x1="layout.center.x - CENTER_W / 2 + 10" :y1="layout.center.y - CENTER_H / 2 + 8 + k * 5.4"
                    :x2="layout.center.x + CENTER_W / 2 - 20" :y2="layout.center.y - CENTER_H / 2 + 8 + k * 5.4"
                    :stroke="centerColor" stroke-width="1.2" opacity="0.4" />
              <!-- 指示灯 -->
              <circle :cx="layout.center.x + CENTER_W / 2 - 12" :cy="layout.center.y - 2" r="2.8" :fill="centerColor" class="topo-led" />
              <circle :cx="layout.center.x + CENTER_W / 2 - 12" :cy="layout.center.y + 6" r="2.8" :fill="centerColor" opacity="0.4" />
              <!-- 底部状态条 -->
              <rect :x="layout.center.x - CENTER_W / 2 + 8" :y="layout.center.y + CENTER_H / 2 - 9" :width="CENTER_W - 16" :height="3.5" rx="1.75"
                    :fill="centerColor" opacity="0.55" />
              <text :x="layout.center.x" :y="layout.center.y + CENTER_H / 2 + 18" text-anchor="middle" class="topo-center-label">MASTER</text>
              <text :x="layout.center.x" :y="layout.center.y + CENTER_H / 2 + 32" text-anchor="middle" class="topo-node-count">{{ model.center.drawAgents.length }}/{{ model.center.agents.length }} agent</text>
            </g>
          </svg>

          <!-- hover 详情卡 -->
          <div v-if="hoverInfo" class="topo-card" :style="{ left: hoverInfo.left + 'px', top: hoverInfo.top + 'px' }">
            <div class="topo-card-title">
              <span class="topo-dot" :style="{ background: hoverInfo.color }"></span>{{ hoverInfo.title }}
            </div>
            <div class="topo-card-sub">{{ hoverInfo.sub }}</div>
            <ul v-if="hoverInfo.agents.length" class="topo-card-list">
              <li v-for="a in hoverInfo.agents" :key="a.id">
                <span class="topo-dot" :style="{ background: agentColor(a.state) }"></span>
                <span class="topo-card-type">{{ a.type === 'code_agent' ? '💻' : '🤖' }}</span>
                <span class="topo-card-name">{{ a.name }}</span>
                <span class="topo-card-state" :style="{ color: agentColor(a.state) }">{{ AGENT_TEXT[a.state] || a.state }}</span>
              </li>
            </ul>
            <div v-else class="topo-card-empty">无 Agent</div>
          </div>
        </div>

        <!-- 图例 -->
        <div class="topo-legend">
          <div class="topo-legend-group">
            <span class="topo-legend-h">节点</span>
            <span class="topo-legend-item"><i class="topo-dot" style="background:#34d99b"></i>在线</span>
            <span class="topo-legend-item"><i class="topo-dot" style="background:#ff5d6c"></i>离线</span>
            <span class="topo-legend-item"><i class="topo-dot" style="background:#8a9bb0"></i>未知</span>
          </div>
          <div class="topo-legend-group">
            <span class="topo-legend-h">Agent</span>
            <span class="topo-legend-item"><i class="topo-dot" style="background:#20c8ff"></i>运行</span>
            <span class="topo-legend-item"><i class="topo-dot" style="background:#ffb347"></i>等待</span>
            <span class="topo-legend-item"><i class="topo-dot" style="background:#8a9bb0"></i>空闲</span>
            <span class="topo-legend-item"><i class="topo-dot" style="background:#ff5d6c"></i>停止</span>
            <span class="topo-legend-item topo-legend-shape">
              <svg width="20" height="18" viewBox="0 0 20 18">
                <line x1="10" y1="2" x2="10" y2="5" stroke="#20c8ff" stroke-width="1.2" />
                <circle cx="10" cy="1.5" r="1.3" fill="#20c8ff" />
                <rect x="5" y="5" width="10" height="8" rx="2.5" fill="#20c8ff" />
                <circle cx="8.2" cy="9" r="1.1" fill="#041018" />
                <circle cx="11.8" cy="9" r="1.1" fill="#041018" />
              </svg>普通
            </span>
            <span class="topo-legend-item topo-legend-shape">
              <svg width="20" height="18" viewBox="0 0 20 18">
                <line x1="10" y1="2" x2="10" y2="5" stroke="#20c8ff" stroke-width="1.2" />
                <circle cx="10" cy="1.5" r="1.3" fill="#20c8ff" />
                <rect x="5" y="5" width="10" height="8" rx="2.5" fill="#20c8ff" />
                <rect x="6.5" y="8" width="7" height="2" rx="1" fill="#041018" />
              </svg>代码
            </span>
          </div>
          <div class="topo-legend-group">
            <span class="topo-legend-h">接入端</span>
            <span class="topo-legend-item topo-legend-shape">
              <svg width="20" height="18" viewBox="0 0 20 18">
                <circle cx="10" cy="9" r="7" fill="rgba(8,18,30,0.95)" stroke="#34d99b" stroke-width="1.4" />
                <text x="10" y="12.4" text-anchor="middle" font-size="8">🧩</text>
              </svg>浏览器扩展
            </span>
            <span class="topo-legend-item topo-legend-shape">
              <svg width="20" height="18" viewBox="0 0 20 18">
                <circle cx="10" cy="9" r="7" fill="rgba(8,18,30,0.95)" stroke="#34d99b" stroke-width="1.4" />
                <text x="10" y="12.4" text-anchor="middle" font-size="8">🖥</text>
              </svg>后台服务
            </span>
          </div>
          <span class="topo-legend-hint">Esc 关闭</span>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { buildTopology, layoutTopology, layoutAgents, formatBrowserLabel } from './topology.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  nodes: { type: Array, default: () => [] },
  agents: { type: Array, default: () => [] },
  getStatusClass: { type: Function, default: () => 'running' },
  nodeDisplayNames: { type: Object, default: () => ({}) },
  // 接入的浏览器扩展会话（网关 /api/browser-ext/sessions，含 name / extension_version）
  extensionSessions: { type: Array, default: () => [] },
  // 接入的后台服务会话（网关 /api/daemon/sessions，含 name / platform / daemon_version）
  daemonSessions: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:visible', 'close'])

const W = 1200
const H = 640
const NODE_R = 30
// 主节点机箱尺寸（比子节点略大，同款造型）
const CENTER_W = 76
const CENTER_H = 66
const AGENT_R = 13
// 子节点 agent 环绕半径（较小，避免与相邻节点/其 agent 相撞）
const AGENT_RING = 62
// 中心 agent 环绕半径（略大，避开中心装饰环与 MASTER 标签）
const CENTER_AGENT_RING = 70
// agent 环外沿到画布边缘的预留（agent 半径 + 标签空间）
const AGENT_EDGE_PAD = AGENT_R + 24

const model = computed(() => buildTopology(props.nodes, props.agents, props.getStatusClass))
// 传入机箱尺寸：保证圆周半径足够大，节点机箱不与中心机箱相贴
// （否则正上方那条 master→节点连线会被两个机箱完全盖住）
const layout = computed(() => layoutTopology(model.value, W, H, {
  centerHalfH: CENTER_H / 2,
  nodeHalfH: NODE_R * 0.86,
  minGap: 14,
  // 缩小环形半径，让子节点更靠中间，给顶部/底部接入端（浏览器扩展/后台服务）
  // 留出更大间隙——移动端 SVG 会整体缩放，间隙不足时接入端会与子节点「挨着」。
  // 桌面端 0.34 → 0.26 后顶部间隙约 32px→83px，移动端(约0.31缩放)视觉约 10px→26px。
  radius: Math.min(W, H) * 0.26,
}))
const counts = computed(() => model.value.counts)
// 参与绘制的 agent（已停止的不绘制，仅作数据显示）
const agentLayout = computed(() =>
  layoutAgents(model.value, layout.value, {
    ring: AGENT_RING,
    centerRing: CENTER_AGENT_RING,
    agentRadius: AGENT_R,
    labelGap: 16,
    canvas: { width: W, height: H },
    edgePad: AGENT_EDGE_PAD,
  }),
)

const NODE_COLORS = { online: '#34d99b', offline: '#ff5d6c', unknown: '#8a9bb0' }
const AGENT_COLORS = { running: '#20c8ff', waiting: '#ffb347', idle: '#8a9bb0', stopped: '#ff5d6c' }
const AGENT_TEXT = { running: '运行中', waiting: '等待输入', idle: '空闲', stopped: '已停止' }

function nodeColor(state) {
  return NODE_COLORS[state] || NODE_COLORS.unknown
}
function agentColor(state) {
  return AGENT_COLORS[state] || AGENT_COLORS.idle
}
function agentFill(state) {
  const c = agentColor(state)
  return c + '33'
}
function agentShort(name) {
  const s = String(name || '')
  if (!s) return ''
  return s.length > 8 ? s.slice(0, 7) + '…' : s
}

const hovered = ref(null)
const bodyEl = ref(null)
const mouse = ref({ x: 0, y: 0 })

function shortLabel(id) {
  const custom = props.nodeDisplayNames && props.nodeDisplayNames[id]
  const s = String((custom && String(custom).trim()) || id || '')
  if (s === 'master') return 'master'
  return s.length > 10 ? s.slice(0, 9) + '…' : s
}

const nodePoints = computed(() => {
  const posMap = new Map(layout.value.nodes.map(p => [p.id, p]))
  return model.value.nodes.map(node => {
    const p = posMap.get(node.id) || { x: layout.value.center.x, y: layout.value.center.y }
    const color = nodeColor(node.state)
    return {
      id: node.id,
      x: p.x,
      y: p.y,
      state: node.state,
      color,
      fill: node.state === 'offline' ? 'rgba(255,93,108,0.14)' : 'rgba(8,18,30,0.95)',
      short: shortLabel(node.id),
      agents: node.agents,
      drawAgents: node.drawAgents || [],
    }
  })
})

const lines = computed(() =>
  nodePoints.value.map(n => ({
    id: n.id,
    x: n.x,
    y: n.y,
    state: n.state,
    hot: hovered.value === n.id,
  }))
)

// 接入端节点：浏览器扩展（上行）、后台服务（下行），各自水平方向均匀分布。
// 数据源均为网关会话列表（props.extensionSessions / props.daemonSessions），
// 名称取会话的 name，故这里展示的是「整个网络接入的」客户端，而非仅本机。
const LOCAL_NODE_R = NODE_R
// 距画布上/下边缘的垂直留白（留足空间，避免节点标签文字被画布边缘裁切）
const LOCAL_NODE_MARGIN = 56
// 接入端节点用圆形（普通节点是服务器机箱），半径略小于机箱半高以留出标签空间
const ACCESS_R = NODE_R * 0.67
// 同一行多个节点之间的水平间距（含机箱宽度）
const ACCESS_NODE_GAP = NODE_R * 1.72 + 30

// 单行节点的横向坐标：以 master 的 x 为中心均匀分布，并限制在画布内
function accessRowXs(count, centerX) {
  if (count <= 0) return []
  const total = (count - 1) * ACCESS_NODE_GAP
  const start = centerX - total / 2
  const minX = LOCAL_NODE_R + 22
  const maxX = Math.max(minX, W - LOCAL_NODE_R - 22)
  const xs = []
  for (let i = 0; i < count; i++) {
    xs.push(Math.min(Math.max(start + i * ACCESS_NODE_GAP, minX), maxX))
  }
  return xs
}

// 会话展示名：优先网关会话里的 name，缺失时按类型回退
function accessSessionName(session, fallback) {
  const name = String((session && session.name) || '').trim()
  return name || fallback
}

// 名称过长时截断（机箱下方标签宽度有限）
function accessShortName(name) {
  const s = String(name || '')
  if (s.length > 10) return s.slice(0, 9) + '…'
  return s
}

const localNodes = computed(() => {
  const cx = layout.value.center.x
  // 接入端放在环形子节点之外（更靠画布边缘），避免与子节点重叠：
  // 顶部接入端放在所有子节点上边缘之上、底部接入端放在所有子节点下边缘之下，
  // 并各自留出标签空间；同时不超出画布边缘留白。
  // 子节点是服务器机箱，取其机箱半高（NODE_R）作为环形子节点的上下边界
  const childTop = nodePoints.value.length
    ? Math.min(...nodePoints.value.map(n => n.y - NODE_R))
    : layout.value.center.y
  const childBottom = nodePoints.value.length
    ? Math.max(...nodePoints.value.map(n => n.y + NODE_R))
    : layout.value.center.y
  // 接入端尽量远离环形子节点（间隙加大），同时圆心不越出画布边缘留白。
  // ACCESS_GAP 是接入端圆心到子节点机箱边缘的目标距离；移动端 SVG 会整体缩放，
  // 间隙不足时接入端会与子节点「挨着」，故这里给足余量（配合缩小环形半径）。
  const ACCESS_GAP = 110
  const topY = Math.max(ACCESS_R, Math.min(LOCAL_NODE_MARGIN + ACCESS_R, childTop - ACCESS_GAP))
  const bottomY = Math.min(H - ACCESS_R, Math.max(H - LOCAL_NODE_MARGIN - ACCESS_R, childBottom + ACCESS_GAP))
  const extXs = accessRowXs(props.extensionSessions.length, cx)
  const daemonXs = accessRowXs(props.daemonSessions.length, cx)
  const nodes = []
  props.extensionSessions.forEach((s, i) => {
    const name = accessSessionName(s, '浏览器扩展')
    // 副标题展示「浏览器名 主版本 · 扩展版本」，让用户区分不同浏览器/设备
    const browserLabel = formatBrowserLabel(s && s.browser_info, s && s.extension_version)
    nodes.push({
      id: `ext-${s.session_id || i}`,
      x: extXs[i],
      y: topY,
      masterX: layout.value.center.x,
      masterY: layout.value.center.y,
      state: 'online',
      color: nodeColor('online'),
      fill: 'rgba(8,18,30,0.95)',
      short: accessShortName(name),
      sub: browserLabel || '浏览器扩展',
      icon: '🧩',
      // 顶部行节点靠上，标签文字在节点下方（朝中间），节点已推远故不与环形子节点相撞
      anchor: 'middle',
      labelAbove: false,
      title: `浏览器扩展 · ${name}${browserLabel ? ` · ${browserLabel}` : ''}`,
    })
  })
  props.daemonSessions.forEach((s, i) => {
    const name = accessSessionName(s, '后台服务')
    const platform = String((s && s.platform) || '').trim()
    const version = String((s && s.daemon_version) || '').trim()
    // daemon 上报的版本可能自带 v 前缀（如 v5.0.5），避免拼成 vv5.0.5
    const versionLabel = version ? (/^v/i.test(version) ? version : `v${version}`) : ''
    const detail = [platform, versionLabel].filter(Boolean).join(' · ')
    nodes.push({
      id: `daemon-${s.session_id || i}`,
      x: daemonXs[i],
      y: bottomY,
      masterX: layout.value.center.x,
      masterY: layout.value.center.y,
      state: 'online',
      color: nodeColor('online'),
      fill: 'rgba(8,18,30,0.95)',
      short: accessShortName(name),
      sub: detail || '后台服务',
      icon: '🖥',
      // 底部行节点靠下，标签文字在节点上方（朝中间），节点已推远故不与环形子节点相撞
      anchor: 'middle',
      labelAbove: true,
      title: `后台服务 · ${name}${detail ? ` · ${detail}` : ''}`,
    })
  })
  return nodes
})

// 直线连线：master → 各接入端节点，直接连接两点。
const localLinks = computed(() =>
  localNodes.value.map(n => ({
    id: n.id,
    d: `M ${n.masterX} ${n.masterY} L ${n.x} ${n.y}`,
    state: n.state,
    hot: hovered.value === n.id,
  }))
)

// 节点 -> agent 连线：每个 agent 连回其所属节点（master 连到中心）
const agentLinks = computed(() => {
  const posMap = new Map(layout.value.nodes.map(p => [p.id, p]))
  return agentLayout.value.agents
    .map(a => {
      const origin = a.nodeId === 'master' ? layout.value.center : posMap.get(a.nodeId)
      if (!origin) return null
      return { id: a.id, x1: origin.x, y1: origin.y, x2: a.x, y2: a.y, state: a.state }
    })
    .filter(Boolean)
})

const centerColor = computed(() => {
  const state = model.value.center.state
  if (state === 'offline') return '#ff5d6c'
  if (state === 'unknown') return '#8a9bb0'
  // 在线主节点用金色强调，与子节点（绿/蓝）区分
  return '#ffd75e'
})
const centerFill = computed(() => {
  const state = model.value.center.state
  if (state === 'offline') return 'rgba(255,93,108,0.85)'
  if (state === 'unknown') return 'rgba(138,155,176,0.8)'
  // 在线主节点：金色渐变填充
  return 'url(#topo-center-fill)'
})

const hoverInfo = computed(() => {
  const id = hovered.value
  if (!id) return null
  const isCenter = id === 'master'
  const node = isCenter ? model.value.center : model.value.nodes.find(n => n.id === id)
  if (!node) return null
  const color = nodeColor(node.state)
  const stateText = node.state === 'online' ? '在线' : node.state === 'offline' ? '离线' : '未知'
  return {
    title: node.id,
    sub: `${stateText} · ${node.agents.length} 个 Agent`,
    color,
    agents: node.agents,
    left: Math.min(Math.max(mouse.value.x + 14, 10), W - 210),
    top: Math.min(Math.max(mouse.value.y + 14, 10), H - 40),
  }
})

function onMove(e) {
  const el = bodyEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const svg = el.querySelector('svg')
  const scale = svg ? svg.clientWidth / W || 1 : 1
  mouse.value = {
    x: (e.clientX - rect.left) / scale,
    y: (e.clientY - rect.top) / scale,
  }
}

function close() {
  emit('update:visible', false)
  emit('close')
}

function onKeydown(e) {
  if (e.key === 'Escape' && props.visible) {
    e.stopPropagation()
    close()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown, true))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown, true))

defineExpose({ close })
</script>

<style scoped>
.topo-overlay {
  position: fixed;
  inset: 0;
  z-index: 2950;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4vh 20px;
  background: rgba(4, 8, 16, 0.6);
  backdrop-filter: blur(3px);
}
.topo-panel {
  width: 96vw;
  height: 92vh;
  max-width: 1600px;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius, 10px);
  box-shadow: 0 12px 44px rgba(0, 120, 190, 0.3);
  overflow: hidden;
}
.topo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
}
.topo-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.topo-title-ico {
  font-size: 16px;
}
.topo-sub {
  font-size: 11px;
  font-weight: 400;
  color: var(--color-text-secondary);
}
.topo-close {
  flex: none;
  width: 26px;
  height: 26px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-xs, 6px);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 12px;
}
.topo-close:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}
.topo-body {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.topo-svg {
  display: block;
  width: 100%;
  height: 100%;
}
/* 左上角统计卡片 */
.topo-stats {
  position: absolute;
  left: 14px;
  top: 14px;
  z-index: 3;
  min-width: 148px;
  padding: 10px 12px;
  background: rgba(8, 16, 28, 0.92);
  border: 1px solid rgba(32, 200, 255, 0.28);
  border-radius: var(--tile-radius-sm, 8px);
  box-shadow: 0 8px 24px rgba(0, 60, 100, 0.35);
  backdrop-filter: blur(4px);
  pointer-events: none;
  user-select: none;
}
.topo-stats-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--color-text-secondary, #8a9bb0);
  margin-bottom: 8px;
}
.topo-stats-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.topo-stats-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-primary, #e6f4ff);
}
.topo-stats-icon {
  flex: none;
  width: 14px;
  text-align: center;
  font-size: 10px;
  color: var(--stat-color, #8a9bb0);
}
.topo-stats-label {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
}
.topo-stats-value {
  flex: none;
  min-width: 20px;
  text-align: right;
  font-weight: 700;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  color: var(--stat-color, #e6f4ff);
}
.topo-stats-foot {
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.08));
  font-size: 10px;
  color: var(--color-text-secondary, #8a9bb0);
}
.topo-link {
  transition: stroke-width 0.15s ease;
}
.topo-link.is-flow {
  stroke-dasharray: 8 6;
  animation: topo-flow 1.2s linear infinite;
}
@keyframes topo-flow {
  to { stroke-dashoffset: -14; }
}
.topo-agent {
  cursor: default;
}
.topo-bot-head {
  opacity: 0.92;
}
.topo-goggle {
  opacity: 0.95;
}
.topo-agent-label {
  font-size: 10px;
  fill: var(--color-text-secondary, #8a9bb0);
  pointer-events: none;
}
.topo-ring {
  transform-box: fill-box;
  transform-origin: center;
  animation: topo-pulse 2.6s ease-out infinite;
}
@keyframes topo-pulse {
  0% { opacity: 0.7; transform: scale(1); }
  75% { opacity: 0; transform: scale(1.7); }
  100% { opacity: 0; transform: scale(1.7); }
}
.topo-node {
  cursor: default;
}
.topo-node.is-hot > .topo-server {
  filter: url(#topo-glow);
}
/* 本机执行面节点：不参与 hover 详情卡（无 agent），仅作状态展示 */
.topo-node.is-local {
  cursor: default;
}
.topo-node.is-local > .topo-node-label {
  font-size: 11px;
  font-weight: 600;
}
/* 接入端胶囊节点内的类型图标（🧩 浏览器扩展 / 🖥 后台服务） */
.topo-access-ico {
  font-size: 13px;
  pointer-events: none;
}
.topo-links-local .topo-link {
  stroke-linecap: round;
}
.topo-server {
  transition: filter 0.15s ease;
}
.topo-led {
  filter: drop-shadow(0 0 3px currentColor);
  animation: topo-led-blink 2.2s ease-in-out infinite;
}
@keyframes topo-led-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.topo-node-label {
  font-size: 11px;
  fill: var(--color-text-secondary, #8a9bb0);
  pointer-events: none;
}
.topo-node-count {
  font-size: 10px;
  fill: var(--color-text-secondary, #8a9bb0);
  opacity: 0.8;
  pointer-events: none;
}
.topo-center-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  fill: #3a2a00;
  pointer-events: none;
}
.topo-node.is-center > .topo-node-count {
  fill: #ffe89a;
  opacity: 0.9;
}
.topo-card {
  position: absolute;
  width: 190px;
  padding: 8px 10px;
  background: rgba(8, 16, 28, 0.96);
  border: 1px solid rgba(32, 200, 255, 0.3);
  border-radius: var(--tile-radius-sm, 8px);
  box-shadow: 0 8px 24px rgba(0, 60, 100, 0.4);
  pointer-events: none;
  z-index: 2;
}
.topo-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary, #e6f4ff);
  word-break: break-all;
}
.topo-card-sub {
  margin-top: 2px;
  font-size: 10px;
  color: var(--color-text-secondary, #8a9bb0);
}
.topo-card-list {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  max-height: 140px;
  overflow: hidden;
}
.topo-card-list li {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 2px 0;
}
.topo-card-type {
  flex: none;
  font-size: 11px;
}
.topo-card-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-primary, #e6f4ff);
}
.topo-card-state {
  flex: none;
  font-size: 10px;
}
.topo-card-empty {
  margin-top: 6px;
  font-size: 10px;
  color: var(--color-text-secondary, #8a9bb0);
}
.topo-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
  flex: none;
}
.topo-legend {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-top: 1px solid var(--color-border-subtle);
  font-size: 11px;
  color: var(--color-text-secondary);
}
.topo-legend-group {
  display: flex;
  align-items: center;
  gap: 10px;
}
.topo-legend-h {
  font-size: 10px;
  letter-spacing: 0.06em;
  opacity: 0.7;
}
.topo-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.topo-legend-shape {
  padding: 1px 6px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-xs, 6px);
  font-size: 10px;
}
.topo-legend-shape svg {
  display: block;
  flex: none;
}
.topo-legend-hint {
  margin-left: auto;
  font-size: 10px;
  opacity: 0.7;
}
.topo-fade-enter-active,
.topo-fade-leave-active {
  transition: opacity 0.16s ease;
}
.topo-fade-enter-from,
.topo-fade-leave-to {
  opacity: 0;
}
</style>
