// 插件前端扩展 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 8），保持行为完全一致：
// - 状态：pluginExtensions / pluginAdminTabs / pluginSidebarViews / pluginToolPanels
// - 标题映射：pluginSidebarTitle / pluginToolPanelTitle / WORKSPACE_SIDEBAR_TITLES / workspaceSidebarTitle
// - 加载：loadPluginExtensionsForUi / resolvePluginExtensionComponent
// - 判断：isPluginSidebarView / isPluginToolView
// - 异步组件缓存与激活：pluginSidebarCompCache / activePluginSidebarComp / activePluginToolPanelComp
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - workspaceSidebarView：侧边栏当前 view 的 ref（App.vue 创建，早于本 composable 调用点）
// - fetchPluginExtensions / loadExtensionComponent：插件扩展加载器（外部模块导入后传入）
// - fetchWithAuth / getHttpProtocol / hasAuthToken / getGatewayAddress：网关访问函数
import { computed, defineAsyncComponent, ref } from 'vue'
export function usePlugins({
  workspaceSidebarView,
  fetchPluginExtensions,
  loadExtensionComponent,
  fetchWithAuth,
  getHttpProtocol,
  hasAuthToken,
  getGatewayAddress,
}) {
  // 插件前端扩展清单（方案2）：从各插件 config.yaml 的 frontend 声明解析而来。
  // 每项：{ nodeId, plugin, extType, id, title, entry, url }
  const pluginExtensions = ref([])
  // 按扩展点类型过滤
  const pluginAdminTabs = computed(() => pluginExtensions.value.filter(e => e.extType === 'admin_tabs'))
  const pluginSidebarViews = computed(() => pluginExtensions.value.filter(e => e.extType === 'sidebar_views'))
  const pluginToolPanels = computed(() => pluginExtensions.value.filter(e => e.extType === 'tool_panels'))
  // 动态侧边栏 view 的标题映射：view 名 = `plugin:${id}`
  function pluginSidebarTitle(view) {
    const ext = pluginSidebarViews.value.find(e => `plugin:${e.id}` === view)
    return ext ? ext.title : ''
  }
  // tool_panels 扩展点复用侧边栏渲染：view 名 = `plugin-tool:${id}`
  function pluginToolPanelTitle(view) {
    const ext = pluginToolPanels.value.find(e => `plugin-tool:${e.id}` === view)
    return ext ? ext.title : ''
  }
  // 侧边栏标题：按当前 view 映射；插件动态 view 走 pluginSidebarTitle / pluginToolPanelTitle
  const WORKSPACE_SIDEBAR_TITLES = {
    search: '全局搜索',
    git: 'Git',
    agents: 'Agent 列表',
    manage: '增强能力清单',
    timers: '定时任务',
    plugins: '插件管理',
    orchestration: '编排查看',
  }
  const workspaceSidebarTitle = computed(() => {
    const view = workspaceSidebarView.value
    if (isPluginSidebarView(view)) return pluginSidebarTitle(view)
    if (isPluginToolView(view)) return pluginToolPanelTitle(view)
    return WORKSPACE_SIDEBAR_TITLES[view] || '目录树'
  })
  // 加载插件扩展清单（登录后调用）；失败静默，不影响主界面
  async function loadPluginExtensionsForUi() {
    if (!hasAuthToken()) return
    const { host, port } = getGatewayAddress()
    const exts = await fetchPluginExtensions({
      fetchWithAuth,
      nodeId: 'master',
      baseUrl: `${host}:${port}`,
      getHttpProtocol,
    })
    pluginExtensions.value = exts
  }
  // 异步加载插件扩展组件（供侧边栏/管理面板渲染）
  function resolvePluginExtensionComponent(ext) {
    return loadExtensionComponent(ext, { fetchWithAuth, getHttpProtocol })
  }
  // 判断某个侧边栏 view 是否为插件扩展 view
  function isPluginSidebarView(view) {
    return typeof view === 'string' && view.startsWith('plugin:')
  }
  // 判断某个侧边栏 view 是否为插件 tool_panel 扩展 view
  function isPluginToolView(view) {
    return typeof view === 'string' && view.startsWith('plugin-tool:')
  }
  // 缓存插件侧边栏的异步组件实例，避免 computed 每次返回新的 defineAsyncComponent。
  // 若每次返回新实例，Vue 重渲染 <component :is> 时会视为不同组件反复卸载/重载，
  // 导致插件组件"先渲染正常、随后被清空为空"。
  const pluginSidebarCompCache = new Map()
  // 当前激活的插件侧边栏 view 对应的异步组件（用于 <component :is> 渲染）
  const activePluginSidebarComp = computed(() => {
    const view = workspaceSidebarView.value
    if (!isPluginSidebarView(view)) return null
    const ext = pluginSidebarViews.value.find(e => `plugin:${e.id}` === view)
    if (!ext) return null
    if (!pluginSidebarCompCache.has(ext.id)) {
      pluginSidebarCompCache.set(ext.id, defineAsyncComponent(() => resolvePluginExtensionComponent(ext)))
    }
    return pluginSidebarCompCache.get(ext.id)
  })
  // 当前激活的插件 tool_panel view 对应的异步组件（复用 pluginSidebarCompCache 缓存，
  // 但用 plugin-tool: 前缀作 key，避免与同名 sidebar_views 扩展互相覆盖）
  const activePluginToolPanelComp = computed(() => {
    const view = workspaceSidebarView.value
    if (!isPluginToolView(view)) return null
    const ext = pluginToolPanels.value.find(e => `plugin-tool:${e.id}` === view)
    if (!ext) return null
    const cacheKey = `plugin-tool:${ext.id}`
    if (!pluginSidebarCompCache.has(cacheKey)) {
      pluginSidebarCompCache.set(cacheKey, defineAsyncComponent(() => resolvePluginExtensionComponent(ext)))
    }
    return pluginSidebarCompCache.get(cacheKey)
  })

  return {
    pluginExtensions,
    pluginAdminTabs,
    pluginSidebarViews,
    pluginToolPanels,
    pluginSidebarTitle,
    pluginToolPanelTitle,
    WORKSPACE_SIDEBAR_TITLES,
    workspaceSidebarTitle,
    loadPluginExtensionsForUi,
    resolvePluginExtensionComponent,
    isPluginSidebarView,
    isPluginToolView,
    pluginSidebarCompCache,
    activePluginSidebarComp,
    activePluginToolPanelComp,
  }
}
