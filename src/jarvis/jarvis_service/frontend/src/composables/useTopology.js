// 网络拓扑 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 8），保持行为完全一致：
// - 状态：topologyExtensionSessions / topologyDaemonSessions / showTopologyOverlay
// - 接入端会话轮询：refreshTopologyAccessSessions / startTopologyAccessPolling / stopTopologyAccessPolling
// - 弹窗控制：openTopologyOverlay / closeTopologyOverlay
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - fetchBrowserExtensionSessions / fetchDaemonSessions：会话查询函数（App.vue 定义）
//
// 注意：topologyExtensionSessions / topologyDaemonSessions 同时被 App.vue 的
// refreshManageCapabilities（manage 域）写入，故这两个 ref 由本 composable 返回，
// App.vue 解构后共享写入。
import { ref } from 'vue'
export function useTopology({
  fetchBrowserExtensionSessions,
  fetchDaemonSessions,
}) {
  // —— 网络拓扑大图中的「接入端」会话列表 ——
  // 浏览器扩展 / 后台服务（daemon）均取网关会话列表：可能有多台设备/多个浏览器接入，
  // 每个会话在拓扑图中渲染为一个节点并显示其 name（用户配置的终端名）。
  // 非管理员只能看到自己的会话（网关侧限制），管理员可见全部。
  const topologyExtensionSessions = ref([])
  const topologyDaemonSessions = ref([])
  let topologyAccessTimer = null
  async function refreshTopologyAccessSessions() {
    const [extSessions, daemonSessions] = await Promise.all([
      fetchBrowserExtensionSessions(),
      fetchDaemonSessions(),
    ])
    topologyExtensionSessions.value = Array.isArray(extSessions) ? extSessions : []
    topologyDaemonSessions.value = Array.isArray(daemonSessions) ? daemonSessions : []
  }
  function startTopologyAccessPolling() {
    if (topologyAccessTimer) return
    refreshTopologyAccessSessions()
    topologyAccessTimer = setInterval(refreshTopologyAccessSessions, 5000)
  }
  function stopTopologyAccessPolling() {
    if (topologyAccessTimer) {
      clearInterval(topologyAccessTimer)
      topologyAccessTimer = null
    }
  }
  const showTopologyOverlay = ref(false) // 网络拓扑大图浮层
  // 打开网络拓扑大图（点击宠物旁迷你图或右键菜单触发）
  function openTopologyOverlay() {
    showTopologyOverlay.value = true
    startTopologyAccessPolling()
  }
  // 关闭网络拓扑大图：停止接入端会话轮询，避免后台空转
  function closeTopologyOverlay() {
    showTopologyOverlay.value = false
    stopTopologyAccessPolling()
  }

  return {
    topologyExtensionSessions,
    topologyDaemonSessions,
    refreshTopologyAccessSessions,
    startTopologyAccessPolling,
    stopTopologyAccessPolling,
    showTopologyOverlay,
    openTopologyOverlay,
    closeTopologyOverlay,
  }
}
