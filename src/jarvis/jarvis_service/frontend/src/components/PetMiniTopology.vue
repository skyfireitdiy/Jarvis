<!-- 宠物旁的实时迷你网络拓扑（纯 SVG 自绘，点击展开大图） -->
<template>
  <div class="pt-mini" :style="{ left: x + 'px', top: y + 'px' }" @click="onOpen" :title="tip">
    <svg class="pt-mini-svg" :width="W" :height="H" :viewBox="`0 0 ${W} ${H}`">
      <defs>
        <radialGradient id="pt-mini-bg" cx="50%" cy="50%" r="65%">
          <stop offset="0%" stop-color="rgba(32,200,255,0.16)" />
          <stop offset="100%" stop-color="rgba(6,12,22,0.92)" />
        </radialGradient>
        <filter id="pt-mini-glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="1.6" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <rect x="0.5" y="0.5" :width="W - 1" :height="H - 1" rx="8" fill="url(#pt-mini-bg)" stroke="rgba(32,200,255,0.28)" />

      <!-- 连线：master -> 各节点 -->
      <line
        v-for="l in lines"
        :key="l.id"
        :x1="layout.center.x"
        :y1="layout.center.y"
        :x2="l.x"
        :y2="l.y"
        :stroke="l.color"
        :stroke-width="l.active ? 1.1 : 0.8"
        :stroke-dasharray="l.state === 'offline' ? '2 2' : ''"
        :opacity="l.state === 'offline' ? 0.4 : 0.75"
      />

      <!-- 中心节点 -->
      <g class="pt-mini-node is-center" :class="'st-' + model.center.state">
        <circle :cx="layout.center.x" :cy="layout.center.y" r="7.5" :fill="centerFill" filter="url(#pt-mini-glow)" />
        <circle :cx="layout.center.x" :cy="layout.center.y" r="7.5" :stroke="centerColor" stroke-width="1" fill="none" class="pt-pulse" />
        <text :x="layout.center.x" :y="layout.center.y + 2.6" text-anchor="middle" class="pt-mini-ico">★</text>
        <!-- center 上的 agent 小点（已停止的 agent 不绘制） -->
        <circle
          v-for="(a, ai) in centerDrawAgents.slice(0, 6)"
          :key="a.id"
          :cx="layout.center.x + 8 + (ai % 3) * 4"
          :cy="layout.center.y - 8 + Math.floor(ai / 3) * 4"
          r="1.6"
          :fill="agentColor(a.state)"
        />
      </g>

      <!-- 其余节点 -->
      <g
        v-for="n in nodePoints"
        :key="n.id"
        class="pt-mini-node"
        :class="'st-' + n.state"
      >
        <circle :cx="n.x" :cy="n.y" :stroke="n.color" :fill="n.fill" stroke-width="1" />
        <circle v-if="n.state !== 'offline'" :cx="n.x" :cy="n.y" r="5.5" :stroke="n.color" stroke-width="1" fill="none" class="pt-pulse" />
        <!-- 节点上的 agent 小点（已停止的 agent 不绘制） -->
        <circle
          v-for="(a, ai) in n.drawAgents.slice(0, 6)"
          :key="a.id"
          :cx="n.x + 6 + (ai % 3) * 4"
          :cy="n.y - 6 + Math.floor(ai / 3) * 4"
          r="1.6"
          :fill="agentColor(a.state)"
        />
      </g>
    </svg>

    <div class="pt-mini-badge" :class="{ 'is-wait': model.counts.waiting > 0 }">
      <span class="pt-mini-badge-dot"></span>{{ model.counts.agents }}
    </div>
    <div class="pt-mini-tip">{{ model.counts.online }}/{{ model.counts.nodes }} 在线<template v-if="model.counts.waiting > 0"> · {{ model.counts.waiting }} 等待</template></div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { buildTopology, layoutTopology } from './topology.js'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  agents: { type: Array, default: () => [] },
  getStatusClass: { type: Function, default: () => 'running' },
  x: { type: Number, default: 0 },
  y: { type: Number, default: 0 },
})

const W = 96
const H = 96

const model = computed(() => buildTopology(props.nodes, props.agents, props.getStatusClass))
const layout = computed(() => layoutTopology(model.value, W, H))

const NODE_COLORS = {
  online: '#34d99b',
  offline: '#ff5d6c',
  unknown: '#8a9bb0',
}

function nodeColor(state) {
  return NODE_COLORS[state] || NODE_COLORS.unknown
}

const AGENT_COLORS = {
  running: '#20c8ff',
  waiting: '#ffb347',
  idle: '#8a9bb0',
  stopped: '#ff5d6c',
}

function agentColor(state) {
  return AGENT_COLORS[state] || AGENT_COLORS.idle
}

const centerDrawAgents = computed(() => model.value.center.drawAgents || [])

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
      fill: node.state === 'offline' ? 'rgba(255,93,108,0.16)' : 'rgba(8,18,30,0.95)',
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
    color: n.color,
    active: n.agents.length > 0,
  }))
)

const centerColor = computed(() => nodeColor(model.value.center.state))
const centerFill = computed(() =>
  model.value.center.state === 'offline' ? 'rgba(255,93,108,0.9)' : 'rgba(32,200,255,0.92)'
)

const tip = computed(() => {
  const c = model.value.counts
  const parts = [`节点 ${c.online}/${c.nodes} 在线`, `Agent ${c.agents} 个`]
  if (c.waiting > 0) parts.push(`${c.waiting} 个等待输入`)
  return parts.join(' · ') + '\n点击查看网络拓扑'
})

const emit = defineEmits(['open'])

function onOpen() {
  emit('open')
}
</script>

<style scoped>
.pt-mini {
  position: fixed;
  z-index: 901;
  width: 96px;
  height: 96px;
  cursor: pointer;
  user-select: none;
  transition: transform 0.18s ease;
}
.pt-mini:hover {
  transform: scale(1.06);
}
.pt-mini-svg {
  display: block;
  overflow: visible;
  filter: drop-shadow(0 4px 14px rgba(0, 90, 140, 0.35));
}
.pt-mini-node text.pt-mini-ico {
  font-size: 6px;
  fill: #04222f;
  pointer-events: none;
}
.pt-pulse {
  transform-box: fill-box;
  transform-origin: center;
  animation: pt-pulse 2.2s ease-out infinite;
}
@keyframes pt-pulse {
  0% { opacity: 0.8; transform: scale(1); }
  70% { opacity: 0; transform: scale(2.1); }
  100% { opacity: 0; transform: scale(2.1); }
}
.pt-mini-badge {
  position: absolute;
  right: -4px;
  top: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  display: flex;
  align-items: center;
  gap: 3px;
  border-radius: 9px;
  background: rgba(8, 18, 30, 0.92);
  border: 1px solid rgba(32, 200, 255, 0.4);
  color: var(--color-text-primary, #e6f4ff);
  font-size: 10px;
  font-weight: 600;
}
.pt-mini-badge.is-wait {
  border-color: rgba(255, 179, 71, 0.7);
  color: #ffb347;
}
.pt-mini-badge-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #34d99b;
  box-shadow: 0 0 6px #34d99b;
}
.pt-mini-badge.is-wait .pt-mini-badge-dot {
  background: #ffb347;
  box-shadow: 0 0 6px #ffb347;
  animation: pt-blink 1s ease-in-out infinite;
}
@keyframes pt-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.pt-mini-tip {
  position: absolute;
  left: 50%;
  bottom: -18px;
  transform: translateX(-50%);
  white-space: nowrap;
  font-size: 9px;
  color: var(--color-text-secondary, #8a9bb0);
  opacity: 0;
  transition: opacity 0.18s ease;
  pointer-events: none;
}
.pt-mini:hover .pt-mini-tip {
  opacity: 1;
}
</style>
