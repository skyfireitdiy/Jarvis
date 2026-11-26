// 标签栏横向滚动 组合式函数（VS Code 式体验）。
//
// 目标：标签数量超出可视宽度时，不再出现「右侧标签被裁掉且点不到」的问题。
// 提供三件事：
// 1) 鼠标滚轮 → 横向滚动（无需按 Shift；已到边界时把滚动交还给外层，避免滚动被吞掉）
// 2) 溢出检测：hiddenLeft / hiddenRight 表示左右是否还有被隐藏的标签
// 3) 激活标签自动滚入可视区（scrollActiveIntoView），避免激活的标签藏在视野外
//
// 用法：
//   const { stripRef, hiddenLeft, hiddenRight, onWheel, updateOverflow, scrollByStep, scrollActiveIntoView } = useTabStripScroll()
//   <div ref="stripRef" @wheel="onWheel" @scroll="updateOverflow"> ... </div>
// 标签元素需带 data-tab-key="<key>"，激活标签需带 .active（或通过 activeKey 参数传入）。
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'

// 每次点击箭头滚动的像素（约 2 个标签宽度）
const SCROLL_STEP = 160

export function useTabStripScroll(options = {}) {
  const { activeKey = null } = options
  const stripRef = ref(null)
  const hiddenLeft = ref(false)
  const hiddenRight = ref(false)

  // 依据 scrollLeft / scrollWidth / clientWidth 计算左右溢出状态
  function updateOverflow() {
    const el = stripRef.value
    if (!el) {
      hiddenLeft.value = false
      hiddenRight.value = false
      return
    }
    const maxScroll = el.scrollWidth - el.clientWidth
    // 1px 容差：避免亚像素取整导致箭头常驻
    hiddenLeft.value = el.scrollLeft > 1
    hiddenRight.value = maxScroll > 1 && el.scrollLeft < maxScroll - 1
  }

  // 鼠标滚轮 → 横向滚动；垂直滚轮也映射为横向（VS Code 行为）
  function onWheel(event) {
    const el = stripRef.value
    if (!el) return
    const maxScroll = el.scrollWidth - el.clientWidth
    if (maxScroll <= 0) return // 未溢出：不拦截，交给外层
    // 优先取纵向滚动量（普通鼠标滚轮），触控板横向手势取 deltaX
    const delta = Math.abs(event.deltaY) > Math.abs(event.deltaX) ? event.deltaY : event.deltaX
    if (!delta) return
    const next = Math.max(0, Math.min(maxScroll, el.scrollLeft + delta))
    if (next === el.scrollLeft) return // 已到边界：不拦截，允许外层滚动
    event.preventDefault()
    el.scrollLeft = next
    updateOverflow()
  }

  // 箭头按钮：按固定步长滚动
  function scrollByStep(direction) {
    const el = stripRef.value
    if (!el) return
    const maxScroll = el.scrollWidth - el.clientWidth
    const next = Math.max(0, Math.min(maxScroll, el.scrollLeft + direction * SCROLL_STEP))
    el.scrollTo({ left: next, behavior: 'smooth' })
    // smooth 滚动结束后再刷新溢出状态
    setTimeout(updateOverflow, 220)
  }

  // 把当前激活标签滚入可视区（尽量居中，靠近边界时贴边）
  function scrollActiveIntoView() {
    const el = stripRef.value
    if (!el) return
    const key = typeof activeKey === 'function' ? activeKey() : activeKey
    let target = null
    if (key != null) {
      target = el.querySelector(`[data-tab-key="${CSS.escape(String(key))}"]`)
    }
    if (!target) target = el.querySelector('.active')
    if (!target) return
    const elRect = el.getBoundingClientRect()
    const tabRect = target.getBoundingClientRect()
    if (tabRect.left < elRect.left) {
      el.scrollLeft -= elRect.left - tabRect.left + 8
    } else if (tabRect.right > elRect.right) {
      el.scrollLeft += tabRect.right - elRect.right + 8
    }
    updateOverflow()
  }

  // 尺寸变化（窗口缩放 / 分屏拖拽 / 标签增删）时重算溢出
  let resizeObserver = null
  onMounted(() => {
    updateOverflow()
    nextTick(updateOverflow)
    if (typeof ResizeObserver !== 'undefined' && stripRef.value) {
      resizeObserver = new ResizeObserver(() => updateOverflow())
      resizeObserver.observe(stripRef.value)
    }
  })
  onBeforeUnmount(() => {
    if (resizeObserver) {
      resizeObserver.disconnect()
      resizeObserver = null
    }
  })

  return {
    stripRef,
    hiddenLeft,
    hiddenRight,
    onWheel,
    updateOverflow,
    scrollByStep,
    scrollActiveIntoView,
  }
}
