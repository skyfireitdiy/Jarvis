<!-- 流水线编排 DAG 可视化视图（自绘 SVG，纯前端渲染）。
     - compact 模式：侧边栏内嵌（窄）
     - full 模式：浮层大图（宽）
     两者共用同一渲染逻辑，仅尺寸/密度不同。 -->
<template>
  <div class="orch-view" :class="mode === 'full' ? 'is-full' : 'is-compact'">
    <!-- 顶部 Tab：多流程切换 -->
    <div v-if="pipelines.length" class="orch-tabs">
      <button
        v-for="p in pipelines"
        :key="p.pipelineId"
        class="orch-tab"
        :class="{ active: p.pipelineId === activeId }"
        :title="p.orchestrationFile"
        @click="$emit('select', p.pipelineId)"
      >
        <span class="orch-tab-dot" :class="'fin-' + p.finalStatus"></span>
        <span class="orch-tab-name">{{ shortName(p) }}</span>
      </button>
      <button class="orch-expand" title="大图查看" @click="$emit('expand')">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="M6 2H2v4M10 14h4v-4M14 6V2h-4M2 10v4h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </div>

    <!-- 空态 -->
    <div v-if="!active" class="orch-empty">
      <svg width="42" height="42" viewBox="0 0 24 24" fill="none" opacity="0.5">
        <circle cx="5" cy="6" r="2.2" stroke="currentColor" stroke-width="1.3"/>
        <circle cx="19" cy="6" r="2.2" stroke="currentColor" stroke-width="1.3"/>
        <circle cx="12" cy="18" r="2.2" stroke="currentColor" stroke-width="1.3"/>
        <path d="M6.5 7.5 10.6 16M17.5 7.5 13.4 16M7 6h10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
      </svg>
      <div class="orch-empty-title">暂无编排流程</div>
      <div class="orch-empty-sub">运行带 flow 的流水线后，这里会实时展示 DAG 进度</div>
    </div>

    <template v-else>
      <!-- 统计卡片 -->
      <div class="orch-stats">
        <div class="orch-stat" :style="{ '--c': STATUS_COLORS.running }">
          <span class="orch-stat-v">{{ statCounts.running }}</span>
          <span class="orch-stat-l">运行中</span>
        </div>
        <div class="orch-stat" :style="{ '--c': STATUS_COLORS.completed }">
          <span class="orch-stat-v">{{ statCounts.completed }}</span>
          <span class="orch-stat-l">已完成</span>
        </div>
        <div class="orch-stat" :style="{ '--c': STATUS_COLORS.failed }">
          <span class="orch-stat-v">{{ statCounts.failed }}</span>
          <span class="orch-stat-l">失败</span>
        </div>
        <div class="orch-stat" :style="{ '--c': STATUS_COLORS.skipped }">
          <span class="orch-stat-v">{{ statCounts.skipped }}</span>
          <span class="orch-stat-l">跳过</span>
        </div>
        <div class="orch-stat orch-stat-wide" :style="{ '--c': '#7f8ea3' }">
          <span class="orch-stat-v">{{ elapsedText }}</span>
          <span class="orch-stat-l">耗时 · 并行 {{ active.maxWorkers || 1 }}</span>
        </div>
      </div>

      <!-- DAG 画布 -->
      <div class="orch-canvas" @mouseleave="hoverStage = ''">
        <svg :viewBox="`0 0 ${layout.width} ${layout.height}`" :width="layout.width" :height="layout.height" class="orch-svg">
          <defs>
            <filter id="orch-glow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="2.4" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <marker id="orch-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="rgba(120,150,190,0.7)" />
            </marker>
            <linearGradient id="orch-edge-flow" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="rgba(32,200,255,0)" />
              <stop offset="50%" stop-color="rgba(32,200,255,0.9)" />
              <stop offset="100%" stop-color="rgba(32,200,255,0)" />
            </linearGradient>
          </defs>

          <!-- 连线 -->
          <g class="orch-edges">
            <path
              v-for="(e, i) in layout.edges"
              :key="'E' + i"
              :d="edgePath(layout.positions[e.from], layout.positions[e.to])"
              class="orch-edge"
              :class="{ 'is-flow': edgeFlowing(e) }"
              fill="none"
              marker-end="url(#orch-arrow)"
            />
          </g>

          <!-- 节点 -->
          <g
            v-for="n in nodes"
            :key="n.stage"
            class="orch-node"
            :class="['st-' + n.status, { 'is-gate': n.gate, 'is-hover': hoverStage === n.stage, 'is-clickable': !!n.agentId }]"
            :transform="`translate(${layout.positions[n.stage].x},${layout.positions[n.stage].y})`"
            @mouseenter="hoverStage = n.stage"
            @click="onNodeClick(n)"
          >
            <rect
              class="orch-node-bg"
              :width="NODE_W"
              :height="NODE_H"
              rx="10"
              :filter="n.status === 'running' ? 'url(#orch-glow)' : ''"
            />
            <rect class="orch-node-accent" x="0" y="0" width="4" :height="NODE_H" rx="2" />
            <text class="orch-node-stage" x="14" y="24">{{ n.stage }}</text>
            <text class="orch-node-agent" x="14" y="42">{{ n.agent }}</text>
            <text v-if="n.gate" class="orch-node-gate" :x="NODE_W - 12" y="24" text-anchor="end">🚧</text>
            <text v-if="n.retryCount" class="orch-node-retry" :x="NODE_W - 12" y="42" text-anchor="end">↻{{ n.retryCount }}</text>
            <circle v-if="n.status === 'running'" class="orch-node-pulse" :cx="NODE_W - 16" cy="14" r="4" />
          </g>
        </svg>

        <!-- hover 详情 -->
        <div v-if="hoverNode" class="orch-tip" :style="tipStyle">
          <div class="orch-tip-stage">{{ hoverNode.stage }}</div>
          <div class="orch-tip-row"><span>Agent</span><b>{{ hoverNode.agent }}</b></div>
          <div class="orch-tip-row"><span>状态</span><b :style="{ color: statusColor(hoverNode.status) }">{{ statusLabel(hoverNode.status) }}</b></div>
          <div v-if="hoverNode.output" class="orch-tip-row"><span>产物</span><b>{{ hoverNode.output }}</b></div>
          <div v-if="hoverNode.dependsOn.length" class="orch-tip-row"><span>依赖</span><b>{{ hoverNode.dependsOn.join(', ') }}</b></div>
          <div v-if="hoverNode.error" class="orch-tip-row orch-tip-err"><span>错误</span><b>{{ hoverNode.error }}</b></div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { layoutDag, edgePath as buildEdgePath, LAYOUT } from './dagLayout.js'

const props = defineProps({
  // [{ pipelineId, orchestrationFile, stages: Map, stageOrder: [], startedAt, finishedAt, finalStatus, maxWorkers, ... }]
  pipelines: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
  mode: { type: String, default: 'compact' }, // compact | full
})

const emit = defineEmits(['select', 'jump-agent', 'expand'])

const NODE_W = LAYOUT.NODE_W
const NODE_H = LAYOUT.NODE_H

const STATUS_COLORS = {
  pending: '#5a6b80',
  running: '#20c8ff',
  completed: '#37d67a',
  failed: '#ff5d6c',
  skipped: 'rgba(140,160,185,0.55)',
}

const hoverStage = ref('')

const active = computed(() => {
  if (!props.pipelines.length) return null
  return props.pipelines.find((p) => p.pipelineId === props.activeId) || props.pipelines[0]
})

const nodes = computed(() => {
  if (!active.value) return []
  const st = active.value
  const order = st.stageOrder && st.stageOrder.length ? st.stageOrder : [...st.stages.keys()]
  return order.map((s) => st.stages.get(s)).filter(Boolean)
})

const layout = computed(() => layoutDag(nodes.value))

const statCounts = computed(() => {
  const c = { running: 0, completed: 0, failed: 0, skipped: 0 }
  for (const n of nodes.value) {
    if (c[n.status] !== undefined) c[n.status] += 1
  }
  return c
})

const elapsedText = computed(() => {
  const st = active.value
  if (!st) return '—'
  const end = st.finishedAt || Date.now()
  const sec = Math.max(0, Math.round((end - st.startedAt) / 1000))
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m${s}s`
})

const hoverNode = computed(() => nodes.value.find((n) => n.stage === hoverStage.value) || null)

const tipStyle = computed(() => {
  const n = hoverNode.value
  if (!n) return {}
  const pos = layout.value.positions[n.stage]
  return { left: `${pos.x + NODE_W + 10}px`, top: `${pos.y}px` }
})

function shortName(p) {
  const f = p.orchestrationFile || p.pipelineId
  const base = f.split('/').pop() || p.pipelineId
  return base.replace(/\.(ya?ml)$/, '')
}

function edgeFlowing(e) {
  const from = active.value?.stages.get(e.from)
  const to = active.value?.stages.get(e.to)
  return from?.status === 'completed' && (to?.status === 'running' || to?.status === 'pending')
}

function statusColor(s) {
  return STATUS_COLORS[s] || '#7f8ea3'
}

function statusLabel(s) {
  return { pending: '待执行', running: '运行中', completed: '已完成', failed: '失败', skipped: '已跳过' }[s] || s
}

function edgePath(a, b) {
  if (!a || !b) return ''
  return buildEdgePath(a, b)
}

function onNodeClick(n) {
  if (n.agentId) emit('jump-agent', n.agentId)
}
</script>

<style scoped>
.orch-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: linear-gradient(180deg, rgba(10, 16, 26, 0.96), rgba(6, 10, 18, 0.98));
  color: #d8e2f0;
  overflow: hidden;
}

/* Tabs */
.orch-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(90, 120, 160, 0.22);
  overflow-x: auto;
  flex: 0 0 auto;
}
.orch-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 8px;
  border: 1px solid rgba(90, 120, 160, 0.28);
  background: rgba(20, 30, 46, 0.7);
  color: #9db0c8;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.orch-tab:hover { border-color: rgba(32, 200, 255, 0.5); color: #d8e2f0; }
.orch-tab.active {
  border-color: rgba(32, 200, 255, 0.75);
  background: rgba(32, 200, 255, 0.12);
  color: #eaf6ff;
  box-shadow: 0 0 12px rgba(32, 200, 255, 0.25);
}
.orch-tab-dot { width: 7px; height: 7px; border-radius: 50%; background: #5a6b80; flex: 0 0 auto; }
.orch-tab-dot.fin-completed { background: #37d67a; box-shadow: 0 0 6px #37d67a; }
.orch-tab-dot.fin-preview { background: #9db0c8; }
.orch-tab-dot.fin-failed { background: #ff5d6c; box-shadow: 0 0 6px #ff5d6c; }
.orch-tab-dot.fin-gate_blocked { background: #f0b429; box-shadow: 0 0 6px #f0b429; }
.orch-tab-dot.fin-running { background: #20c8ff; box-shadow: 0 0 6px #20c8ff; animation: orch-blink 1.2s ease-in-out infinite; }
.orch-expand {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px; height: 26px;
  border-radius: 7px;
  border: 1px solid rgba(90, 120, 160, 0.28);
  background: rgba(20, 30, 46, 0.7);
  color: #9db0c8;
  cursor: pointer;
  flex: 0 0 auto;
}
.orch-expand:hover { color: #20c8ff; border-color: rgba(32, 200, 255, 0.5); }

/* Empty */
.orch-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #7f8ea3;
  padding: 24px;
  text-align: center;
}
.orch-empty-title { font-size: 14px; color: #9db0c8; }
.orch-empty-sub { font-size: 12px; opacity: 0.8; }

/* Stats */
.orch-stats {
  display: flex;
  gap: 8px;
  padding: 10px;
  flex: 0 0 auto;
  overflow-x: auto;
}
.orch-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 58px;
  padding: 6px 10px;
  border-radius: 10px;
  background: rgba(18, 26, 40, 0.8);
  border: 1px solid color-mix(in srgb, var(--c) 40%, transparent);
  box-shadow: inset 0 0 14px color-mix(in srgb, var(--c) 12%, transparent);
}
.orch-stat-v { font-size: 17px; font-weight: 600; color: var(--c); }
.orch-stat-l { font-size: 10px; color: #8b9cb3; white-space: nowrap; }
.orch-stat-wide { min-width: 96px; }

/* Canvas */
.orch-canvas {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px;
}
.orch-svg { display: block; }

/* Edges */
.orch-edge {
  stroke: rgba(120, 150, 190, 0.45);
  stroke-width: 1.6;
}
.orch-edge.is-flow {
  stroke: #20c8ff;
  stroke-width: 2;
  stroke-dasharray: 8 8;
  animation: orch-dash 0.9s linear infinite;
}

/* Nodes */
.orch-node-bg {
  fill: rgba(22, 32, 48, 0.95);
  stroke: rgba(90, 120, 160, 0.4);
  stroke-width: 1.2;
  transition: all 0.18s;
}
.orch-node-accent { fill: #5a6b80; }
.orch-node-stage { fill: #eaf2ff; font-size: 13px; font-weight: 600; }
.orch-node-agent { fill: #8b9cb3; font-size: 10.5px; }
.orch-node-gate { font-size: 12px; }
.orch-node-retry { fill: #f0b429; font-size: 10px; }
.orch-node-pulse { fill: #20c8ff; animation: orch-pulse 1.1s ease-in-out infinite; }
.orch-node.is-clickable { cursor: pointer; }
.orch-node.is-hover .orch-node-bg { stroke-width: 2; }
.orch-node:hover .orch-node-bg { filter: brightness(1.15); }

/* Status colors */
.orch-node.st-pending .orch-node-accent { fill: #5a6b80; }
.orch-node.st-running .orch-node-bg { stroke: #20c8ff; }
.orch-node.st-running .orch-node-accent { fill: #20c8ff; }
.orch-node.st-completed .orch-node-bg { stroke: #37d67a; }
.orch-node.st-completed .orch-node-accent { fill: #37d67a; }
.orch-node.st-failed .orch-node-bg { stroke: #ff5d6c; }
.orch-node.st-failed .orch-node-accent { fill: #ff5d6c; }
.orch-node.st-skipped { opacity: 0.55; }
.orch-node.st-skipped .orch-node-bg { stroke-dasharray: 5 4; }
.orch-node.st-skipped .orch-node-accent { fill: rgba(140, 160, 185, 0.55); }
.orch-node.is-gate .orch-node-bg { stroke: #f0b429; }

/* Tooltip */
.orch-tip {
  position: absolute;
  z-index: 5;
  min-width: 160px;
  max-width: 260px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(12, 18, 28, 0.97);
  border: 1px solid rgba(32, 200, 255, 0.35);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5);
  font-size: 11px;
  pointer-events: none;
}
.orch-tip-stage { font-size: 12px; font-weight: 600; color: #eaf2ff; margin-bottom: 5px; }
.orch-tip-row { display: flex; gap: 8px; line-height: 1.7; }
.orch-tip-row span { color: #7f8ea3; flex: 0 0 34px; }
.orch-tip-row b { color: #c6d4e6; font-weight: 500; word-break: break-all; }
.orch-tip-err b { color: #ff8a94; }

@keyframes orch-dash { to { stroke-dashoffset: -16; } }
@keyframes orch-pulse { 0%, 100% { opacity: 1; r: 4; } 50% { opacity: 0.35; r: 5.5; } }
@keyframes orch-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
</style>
