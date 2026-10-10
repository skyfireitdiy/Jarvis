// usePlugins 单元测试
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { usePlugins } from './usePlugins.js'

// 构造 usePlugins 依赖注入 harness
function makeHarness({ exts = [], workspaceSidebarViewValue = 'agents' } = {}) {
  const workspaceSidebarView = ref(workspaceSidebarViewValue)
  const fetchPluginExtensions = vi.fn(async () => exts)
  const loadExtensionComponent = vi.fn(async () => ({}))
  const fetchWithAuth = vi.fn()
  const getHttpProtocol = vi.fn(() => 'http')
  const hasAuthToken = vi.fn(() => true)
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const api = usePlugins({
    workspaceSidebarView,
    fetchPluginExtensions,
    loadExtensionComponent,
    fetchWithAuth,
    getHttpProtocol,
    hasAuthToken,
    getGatewayAddress,
  })
  return {
    api,
    workspaceSidebarView,
    fetchPluginExtensions,
    loadExtensionComponent,
    fetchWithAuth,
    getHttpProtocol,
    hasAuthToken,
    getGatewayAddress,
  }
}

// 构造一个扩展项
function makeExt({ id = 'ext-1', extType = 'sidebar_views', title = '扩展1' } = {}) {
  return { nodeId: 'master', plugin: 'demo', extType, id, title, entry: 'index.js', url: 'http://x' }
}

describe('usePlugins', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('初始状态：扩展清单为空，各过滤列表为空', () => {
    const { api } = makeHarness()
    expect(api.pluginExtensions.value).toEqual([])
    expect(api.pluginAdminTabs.value).toEqual([])
    expect(api.pluginSidebarViews.value).toEqual([])
    expect(api.pluginToolPanels.value).toEqual([])
  })

  it('loadPluginExtensionsForUi 加载扩展清单并写入 pluginExtensions', async () => {
    const exts = [makeExt({ id: 'a', extType: 'admin_tabs' }), makeExt({ id: 'b', extType: 'sidebar_views' })]
    const { api, fetchPluginExtensions, getGatewayAddress } = makeHarness({ exts })
    await api.loadPluginExtensionsForUi()
    expect(fetchPluginExtensions).toHaveBeenCalledTimes(1)
    expect(fetchPluginExtensions).toHaveBeenCalledWith({
      fetchWithAuth: expect.any(Function),
      nodeId: 'master',
      baseUrl: '127.0.0.1:8000',
      getHttpProtocol: expect.any(Function),
    })
    expect(api.pluginExtensions.value).toEqual(exts)
  })

  it('loadPluginExtensionsForUi 无 token 时直接返回，不请求', async () => {
    const { api, hasAuthToken, fetchPluginExtensions } = makeHarness()
    hasAuthToken.mockReturnValue(false)
    await api.loadPluginExtensionsForUi()
    expect(fetchPluginExtensions).not.toHaveBeenCalled()
  })

  it('按扩展点类型过滤', () => {
    const exts = [
      makeExt({ id: 'a', extType: 'admin_tabs' }),
      makeExt({ id: 'b', extType: 'sidebar_views' }),
      makeExt({ id: 'c', extType: 'tool_panels' }),
    ]
    const { api, workspaceSidebarView } = makeHarness({ exts })
    // 手动写入（模拟 loadPluginExtensionsForUi 结果）
    api.pluginExtensions.value = exts
    expect(api.pluginAdminTabs.value.map(e => e.id)).toEqual(['a'])
    expect(api.pluginSidebarViews.value.map(e => e.id)).toEqual(['b'])
    expect(api.pluginToolPanels.value.map(e => e.id)).toEqual(['c'])
    // workspaceSidebarTitle 对普通 view 走 WORKSPACE_SIDEBAR_TITLES
    workspaceSidebarView.value = 'git'
    expect(api.workspaceSidebarTitle.value).toBe('Git')
    workspaceSidebarView.value = 'unknown'
    expect(api.workspaceSidebarTitle.value).toBe('目录树')
  })

  it('isPluginSidebarView / isPluginToolView 判断', () => {
    const { api } = makeHarness()
    expect(api.isPluginSidebarView('plugin:foo')).toBe(true)
    expect(api.isPluginSidebarView('plugin-tool:foo')).toBe(false)
    expect(api.isPluginSidebarView('agents')).toBe(false)
    expect(api.isPluginToolView('plugin-tool:foo')).toBe(true)
    expect(api.isPluginToolView('plugin:foo')).toBe(false)
    expect(api.isPluginToolView(null)).toBe(false)
  })

  it('pluginSidebarTitle / pluginToolPanelTitle 映射', () => {
    const exts = [makeExt({ id: 's1', extType: 'sidebar_views', title: '侧边扩展' }), makeExt({ id: 't1', extType: 'tool_panels', title: '工具面板' })]
    const { api } = makeHarness({ exts })
    api.pluginExtensions.value = exts
    expect(api.pluginSidebarTitle('plugin:s1')).toBe('侧边扩展')
    expect(api.pluginSidebarTitle('plugin:none')).toBe('')
    expect(api.pluginToolPanelTitle('plugin-tool:t1')).toBe('工具面板')
    expect(api.pluginToolPanelTitle('plugin-tool:none')).toBe('')
  })

  it('workspaceSidebarTitle 对插件 view 走动态标题', () => {
    const exts = [makeExt({ id: 's1', extType: 'sidebar_views', title: '侧边扩展' })]
    const { api, workspaceSidebarView } = makeHarness({ exts })
    api.pluginExtensions.value = exts
    workspaceSidebarView.value = 'plugin:s1'
    expect(api.workspaceSidebarTitle.value).toBe('侧边扩展')
  })

  it('activePluginSidebarComp 对插件 view 返回缓存组件（同一实例）', () => {
    const exts = [makeExt({ id: 's1', extType: 'sidebar_views', title: '侧边扩展' })]
    const { api, workspaceSidebarView, loadExtensionComponent } = makeHarness({ exts })
    api.pluginExtensions.value = exts
    workspaceSidebarView.value = 'plugin:s1'
    const comp1 = api.activePluginSidebarComp.value
    expect(comp1).toBeTruthy()
    // 再次访问应命中缓存，同一实例
    const comp2 = api.activePluginSidebarComp.value
    expect(comp1).toBe(comp2)
    // 非插件 view 返回 null
    workspaceSidebarView.value = 'agents'
    expect(api.activePluginSidebarComp.value).toBe(null)
  })

  it('activePluginToolPanelComp 对 tool_panel view 返回组件，与 sidebar 缓存 key 隔离', () => {
    const exts = [
      makeExt({ id: 'x', extType: 'sidebar_views', title: '侧边' }),
      makeExt({ id: 'x', extType: 'tool_panels', title: '工具' }),
    ]
    const { api, workspaceSidebarView } = makeHarness({ exts })
    api.pluginExtensions.value = exts
    workspaceSidebarView.value = 'plugin:x'
    const sidebarComp = api.activePluginSidebarComp.value
    workspaceSidebarView.value = 'plugin-tool:x'
    const toolComp = api.activePluginToolPanelComp.value
    // 两个缓存 key 不同（plugin:x vs plugin-tool:x），组件实例不同
    expect(sidebarComp).not.toBe(toolComp)
    expect(api.activePluginToolPanelComp.value).toBe(toolComp)
  })
})
