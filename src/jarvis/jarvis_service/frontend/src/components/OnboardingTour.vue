<template>
  <transition name="ob-fade">
    <div v-if="visible && currentStep" class="ob-root" @click.self="onSkip">
      <!-- 高亮遮罩：目标元素存在时用四个遮罩块挖出高亮区，否则整屏压暗 -->
      <template v-if="highlightRect">
        <div class="ob-mask" :style="maskStyle('top')"></div>
        <div class="ob-mask" :style="maskStyle('bottom')"></div>
        <div class="ob-mask" :style="maskStyle('left')"></div>
        <div class="ob-mask" :style="maskStyle('right')"></div>
        <div class="ob-ring" :style="ringStyle"></div>
      </template>
      <div v-else class="ob-mask ob-mask-full"></div>

      <!-- 引导气泡 -->
      <div class="ob-card" :class="{ 'ob-card-center': !highlightRect }" :style="cardStyle">
        <div class="ob-card-head">
          <span class="ob-icon">{{ currentStep.icon || '✨' }}</span>
          <div class="ob-head-text">
            <div class="ob-title">{{ currentStep.title }}</div>
            <div class="ob-progress">{{ stepIndex + 1 }} / {{ steps.length }}</div>
          </div>
          <button class="ob-close" type="button" title="关闭引导" @click="onSkip">✕</button>
        </div>

        <div class="ob-desc">{{ currentStep.desc }}</div>
        <div v-if="currentStep.hint" class="ob-hint">{{ currentStep.hint }}</div>

        <div class="ob-dots">
          <span
            v-for="(s, i) in steps"
            :key="s.id || i"
            class="ob-dot"
            :class="{ 'is-active': i === stepIndex, 'is-done': i < stepIndex }"
          ></span>
        </div>

        <div class="ob-actions">
          <button class="ob-btn ob-btn-ghost" type="button" @click="onSkip">跳过引导</button>
          <div class="ob-actions-right">
            <button
              class="ob-btn ob-btn-ghost"
              type="button"
              :disabled="stepIndex === 0"
              @click="prev"
            >上一步</button>
            <button v-if="!isLastStep" class="ob-btn ob-btn-primary" type="button" @click="next">
              下一步
            </button>
            <button v-else class="ob-btn ob-btn-primary" type="button" @click="onFinish">
              开始使用
            </button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  steps: { type: Array, default: () => [] },
  storageKey: { type: String, default: '' },
})

const emit = defineEmits(['update:visible', 'close', 'finish'])

const CARD_WIDTH = 360
const CARD_MARGIN = 16
const GAP = 14

const stepIndex = ref(0)
const highlightRect = ref(null)
const cardPosition = ref({ top: 0, left: 0 })

// 卡片宽度随视口收缩，避免窄屏下溢出（与 .ob-card-center 的 92vw 保持一致）
const cardWidth = computed(() => {
  const { width: vw } = viewportSize()
  const available = vw - CARD_MARGIN * 2
  if (available <= 0) return CARD_WIDTH
  return Math.min(CARD_WIDTH, available)
})

const currentStep = computed(() => props.steps[stepIndex.value] || null)
const isLastStep = computed(() => stepIndex.value >= props.steps.length - 1)

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function viewportSize() {
  return {
    width: window.innerWidth || document.documentElement.clientWidth || 0,
    height: window.innerHeight || document.documentElement.clientHeight || 0,
  }
}

// 查找当前步骤的目标元素：选择器缺失、未命中或不可见时返回 null（退化为居中卡片）
function resolveTargetElement() {
  const selector = currentStep.value?.target
  if (!selector) return null
  let el = null
  try {
    el = document.querySelector(selector)
  } catch (err) {
    return null
  }
  if (!el) return null
  const rect = el.getBoundingClientRect()
  if (!rect.width || !rect.height) return null
  return el
}

function computeCardPosition(rect) {
  const { width: vw, height: vh } = viewportSize()
  const width = cardWidth.value
  const placement = currentStep.value?.placement || 'auto'
  const cardHeight = 240
  let top
  let left

  if (placement === 'top' || (placement === 'auto' && rect.top > cardHeight + GAP)) {
    top = rect.top - cardHeight - GAP
  } else if (placement === 'bottom' || (placement === 'auto' && vh - rect.bottom > cardHeight + GAP)) {
    top = rect.bottom + GAP
  } else {
    top = clamp(rect.top, CARD_MARGIN, Math.max(CARD_MARGIN, vh - cardHeight - CARD_MARGIN))
  }

  if (placement === 'left' && rect.left > width + GAP) {
    left = rect.left - width - GAP
  } else if (placement === 'right' && vw - rect.right > width + GAP) {
    left = rect.right + GAP
  } else {
    left = rect.left + rect.width / 2 - width / 2
  }

  return {
    top: clamp(top, CARD_MARGIN, Math.max(CARD_MARGIN, vh - cardHeight - CARD_MARGIN)),
    left: clamp(left, CARD_MARGIN, Math.max(CARD_MARGIN, vw - width - CARD_MARGIN)),
  }
}

function refreshLayout() {
  if (!props.visible || !currentStep.value) {
    highlightRect.value = null
    return
  }
  const el = resolveTargetElement()
  if (!el) {
    highlightRect.value = null
    return
  }
  const rect = el.getBoundingClientRect()
  highlightRect.value = {
    top: rect.top,
    left: rect.left,
    width: rect.width,
    height: rect.height,
    bottom: rect.bottom,
    right: rect.right,
  }
  cardPosition.value = computeCardPosition(rect)
}

const maskStyle = (side) => {
  const rect = highlightRect.value
  if (!rect) return {}
  const { width: vw, height: vh } = viewportSize()
  if (side === 'top') return { top: '0px', left: '0px', width: '100%', height: `${Math.max(rect.top, 0)}px` }
  if (side === 'bottom') {
    return { top: `${rect.bottom}px`, left: '0px', width: '100%', height: `${Math.max(vh - rect.bottom, 0)}px` }
  }
  if (side === 'left') {
    return { top: `${rect.top}px`, left: '0px', width: `${Math.max(rect.left, 0)}px`, height: `${rect.height}px` }
  }
  return {
    top: `${rect.top}px`,
    left: `${rect.right}px`,
    width: `${Math.max(vw - rect.right, 0)}px`,
    height: `${rect.height}px`,
  }
}

const ringStyle = computed(() => {
  const rect = highlightRect.value
  if (!rect) return {}
  return {
    top: `${rect.top - 4}px`,
    left: `${rect.left - 4}px`,
    width: `${rect.width + 8}px`,
    height: `${rect.height + 8}px`,
  }
})

const cardStyle = computed(() => {
  if (!highlightRect.value) return {}
  return {
    top: `${cardPosition.value.top}px`,
    left: `${cardPosition.value.left}px`,
    width: `${cardWidth.value}px`,
  }
})

// 跳过当前步骤中不可见的目标：连续向前查找第一个可展示的步骤
function findVisibleStepIndex(from) {
  for (let i = from; i < props.steps.length; i++) {
    const step = props.steps[i]
    if (!step?.target) return i
    let el = null
    try {
      el = document.querySelector(step.target)
    } catch (err) {
      el = null
    }
    if (el) {
      const rect = el.getBoundingClientRect()
      if (rect.width && rect.height) return i
    }
  }
  return props.steps.length - 1
}

function next() {
  if (isLastStep.value) {
    onFinish()
    return
  }
  stepIndex.value = findVisibleStepIndex(stepIndex.value + 1)
  nextTick(refreshLayout)
}

function prev() {
  if (stepIndex.value === 0) return
  stepIndex.value = findVisibleStepIndex(stepIndex.value - 1)
  nextTick(refreshLayout)
}

function close() {
  emit('update:visible', false)
  emit('close')
}

function onSkip() {
  close()
}

function onFinish() {
  if (props.storageKey) {
    try {
      localStorage.setItem(props.storageKey, '1')
    } catch (err) {
      /* 隐私模式下写入失败可忽略 */
    }
  }
  emit('update:visible', false)
  emit('finish')
}

function onKeydown(event) {
  if (!props.visible) return
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    onSkip()
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    next()
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    prev()
  }
}

function onViewportChange() {
  refreshLayout()
}

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      stepIndex.value = findVisibleStepIndex(0)
      nextTick(refreshLayout)
    } else {
      highlightRect.value = null
    }
  },
  { immediate: true }
)

watch(stepIndex, () => {
  nextTick(refreshLayout)
})

onMounted(() => {
  window.addEventListener('keydown', onKeydown, true)
  window.addEventListener('resize', onViewportChange)
  window.addEventListener('scroll', onViewportChange, true)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown, true)
  window.removeEventListener('resize', onViewportChange)
  window.removeEventListener('scroll', onViewportChange, true)
})
</script>

<style scoped>
.ob-root {
  position: fixed;
  inset: 0;
  z-index: 9000;
}

.ob-mask {
  position: fixed;
  background: rgba(4, 8, 16, 0.72);
  pointer-events: auto;
}

.ob-mask-full {
  inset: 0;
}

.ob-ring {
  position: fixed;
  border: 1px solid var(--color-accent, #20c8ff);
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(32, 200, 255, 0.35), 0 0 24px rgba(32, 200, 255, 0.35);
  pointer-events: none;
  transition: top 0.18s ease, left 0.18s ease, width 0.18s ease, height 0.18s ease;
}

.ob-card {
  position: fixed;
  background: rgba(9, 16, 28, 0.96);
  border: 1px solid var(--color-border-subtle, rgba(32, 200, 255, 0.15));
  border-radius: var(--tile-radius, 10px);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(32, 200, 255, 0.08);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: 16px 18px;
  color: var(--color-text-primary, #d6e4f0);
  box-sizing: border-box;
}

.ob-card-center {
  top: 50%;
  left: 50%;
  width: min(360px, calc(100vw - 32px));
  transform: translate(-50%, -50%);
}

.ob-card-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.ob-icon {
  font-size: 20px;
  line-height: 1.2;
  flex: none;
}

.ob-head-text {
  flex: 1;
  min-width: 0;
}

.ob-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-accent, #20c8ff);
}

.ob-progress {
  margin-top: 2px;
  font-size: 11px;
  color: var(--color-text-secondary, #8ba3b8);
}

.ob-close {
  flex: none;
  background: transparent;
  border: none;
  color: var(--color-text-secondary, #8ba3b8);
  font-size: 13px;
  cursor: pointer;
  padding: 2px 4px;
  line-height: 1;
}

.ob-close:hover {
  color: var(--color-text-primary, #d6e4f0);
}

.ob-desc {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--color-text-primary, #d6e4f0);
}

.ob-hint {
  margin-top: 8px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-secondary, #8ba3b8);
  background: rgba(32, 200, 255, 0.06);
  border-left: 2px solid var(--color-accent, #20c8ff);
  border-radius: 4px;
}

.ob-dots {
  display: flex;
  gap: 6px;
  margin-top: 14px;
}

.ob-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(139, 163, 184, 0.35);
  transition: background 0.18s ease, transform 0.18s ease;
}

.ob-dot.is-done {
  background: rgba(32, 200, 255, 0.45);
}

.ob-dot.is-active {
  background: var(--color-accent, #20c8ff);
  transform: scale(1.3);
}

.ob-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 16px;
}

.ob-actions-right {
  display: flex;
  gap: 8px;
}

.ob-btn {
  padding: 7px 14px;
  font-size: 12px;
  font-family: inherit;
  border-radius: var(--tile-radius-xs, 6px);
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, filter 0.18s ease;
}

.ob-btn-ghost {
  background: transparent;
  border: 1px solid var(--color-border-subtle, rgba(32, 200, 255, 0.15));
  color: var(--color-text-secondary, #8ba3b8);
}

.ob-btn-ghost:hover:not(:disabled) {
  color: var(--color-text-primary, #d6e4f0);
  border-color: var(--color-accent, #20c8ff);
}

.ob-btn-ghost:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ob-btn-primary {
  background: var(--gradient-accent, linear-gradient(135deg, #20c8ff 0%, #36ff7c 100%));
  border: none;
  color: #060911;
  font-weight: 700;
}

.ob-btn-primary:hover {
  filter: brightness(1.08);
}

.ob-fade-enter-active,
.ob-fade-leave-active {
  transition: opacity 0.18s ease;
}

.ob-fade-enter-from,
.ob-fade-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {
  .ob-card {
    padding: 14px 14px;
  }

  .ob-card-center {
    width: min(360px, calc(100vw - 32px));
  }
}

@media (prefers-reduced-motion: reduce) {
  .ob-ring,
  .ob-dot,
  .ob-fade-enter-active,
  .ob-fade-leave-active {
    transition: none;
  }
}
</style>
