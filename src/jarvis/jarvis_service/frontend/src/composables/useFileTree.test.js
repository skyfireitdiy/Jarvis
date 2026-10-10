// useFileTree 单元测试
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useFileTree } from './useFileTree.js'

// 构造 useFileTree 依赖注入 harness
function makeAgent({ id = 'agent-1', nodeId = 'node-1', workingDir = '/home/user/proj', virtual = false } = {}) {
  return { agent_id: id, node_id: nodeId, working_dir: workingDir, virtual }
}

function makeHarness({ agent = null, directoryItems = [], fetchImpl } = {}) {
  const agentList = ref(agent ? [agent] : [])
  const getVirtualWorkspaceAgent = vi.fn((agentId) => (agent && agent.agent_id === agentId ? agent : null))
  const resolveFileTreeAgent = vi.fn((agentId) => (agent && agent.agent_id === agentId ? agent : null))
  const resolveAgentForPath = vi.fn((_path) => (agent ? { agentId: agent.agent_id, agent } : null))
  const openWorkspaceFile = vi.fn()
  const setWorkspaceSidebarView = vi.fn()
  const removeWorkspaceDir = vi.fn()
  const fetchFileContent = vi.fn(async (path) => `content-of-${path}`)
  const fetchWithAuth = vi.fn(
    fetchImpl ||
      (async (url) => {
        const path = String(url).split('/').pop()
        if (path.startsWith('directories?')) {
          return { ok: true, json: async () => ({ success: true, data: { items: directoryItems } }) }
        }
        return { ok: true, json: async () => ({ success: true, data: {} }) }
      })
  )
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/node/${nodeId}/${path}`)
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const showToast = vi.fn()
  const showConfirm = vi.fn((msg, onOk) => onOk && onOk())
  const globalSearchFileGlob = ref('')
  const ensureWorkspaceSidebarFileTree = vi.fn()
  const api = useFileTree({
    agentList,
    getVirtualWorkspaceAgent,
    resolveFileTreeAgent,
    resolveAgentForPath,
    openWorkspaceFile,
    setWorkspaceSidebarView,
    removeWorkspaceDir,
    fetchFileContent,
    fetchWithAuth,
    buildNodeHttpUrl,
    getGatewayAddress,
    showToast,
    showConfirm,
    globalSearchFileGlob,
    ensureWorkspaceSidebarFileTree,
  })
  return {
    api,
    agentList,
    getVirtualWorkspaceAgent,
    resolveFileTreeAgent,
    resolveAgentForPath,
    openWorkspaceFile,
    setWorkspaceSidebarView,
    removeWorkspaceDir,
    fetchFileContent,
    fetchWithAuth,
    buildNodeHttpUrl,
    getGatewayAddress,
    showToast,
    showConfirm,
    globalSearchFileGlob,
    ensureWorkspaceSidebarFileTree,
  }
}

// 等待所有微任务/宏任务完成（内部 async 链）
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('useFileTree', () => {
  beforeEach(() => {
    // jsdom 中 CSS.escape 可能缺失，mock 掉避免 scrollFileTreeNodeIntoView 报错
    globalThis.CSS = globalThis.CSS || {}
    globalThis.CSS.escape = globalThis.CSS.escape || ((s) => s)
  })

  it('暴露预期接口', () => {
    const { api } = makeHarness()
    // 状态 ref
    expect(typeof api.fileTreeState).toBe('object')
    expect(typeof api.fileTreeExpanded).toBe('object')
    expect(typeof api.fileTreeLoading).toBe('object')
    expect(typeof api.expandedAgents).toBe('object')
    expect(typeof api.selectedAgentId).toBe('object')
    expect(typeof api.fileTreeSelectedPath).toBe('object')
    expect(typeof api.fileTreeSelectedAgentId).toBe('object')
    expect(typeof api.fileTreeContextMenu).toBe('object')
    expect(typeof api.fileTreeUploadInput).toBe('object')
    expect(typeof api.inputPrompt).toBe('object')
    expect(typeof api.fileTreeDropTargetPath).toBe('object')
    // 函数
    expect(typeof api.initFileTree).toBe('function')
    expect(typeof api.getVisibleFileTreeNodes).toBe('function')
    expect(typeof api.toggleAgentExpanded).toBe('function')
    expect(typeof api.handleFileTreeKeydown).toBe('function')
    expect(typeof api.runFileTreeContextAction).toBe('function')
    expect(typeof api.handleFileTreeDrop).toBe('function')
  })

  it('初始状态', () => {
    const { api } = makeHarness()
    expect(api.fileTreeState.value.size).toBe(0)
    expect(api.expandedAgents.value.size).toBe(0)
    expect(api.selectedAgentId.value).toBeNull()
    expect(api.fileTreeSelectedPath.value).toBeNull()
    expect(api.fileTreeSelectedAgentId.value).toBeNull()
    expect(api.fileTreeContextMenu.value.visible).toBe(false)
    expect(api.inputPrompt.value.visible).toBe(false)
    expect(api.fileTreeDropTargetPath.value).toBe('')
  })

  describe('initFileTree', () => {
    it('初始化状态并创建根节点', async () => {
      const agent = makeAgent()
      const { api, fetchWithAuth } = makeHarness({ agent })
      await api.initFileTree('agent-1', '/home/user/proj')
      expect(api.fileTreeState.value.has('agent-1')).toBe(true)
      expect(api.fileTreeExpanded.value.has('agent-1')).toBe(true)
      expect(api.fileTreeLoading.value.has('agent-1')).toBe(true)
      const roots = api.fileTreeState.value.get('agent-1')
      expect(roots.length).toBe(1)
      const root = roots[0]
      expect(root.name).toBe('proj')
      expect(root.path).toBe('/home/user/proj')
      expect(root.type).toBe('directory')
      expect(root.expanded).toBe(false)
      expect(fetchWithAuth).toHaveBeenCalled()
    })

    it('根目录加载子节点：文件节点无 children/loaded，目录节点有', async () => {
      const agent = makeAgent()
      const { api } = makeHarness({
        agent,
        directoryItems: [
          { name: 'main.js', path: '/home/user/proj/main.js', type: 'file' },
          { name: 'src', path: '/home/user/proj/src', type: 'directory' },
        ],
      })
      await api.initFileTree('agent-1', '/home/user/proj')
      const root = api.fileTreeState.value.get('agent-1')[0]
      expect(root.loaded).toBe(true)
      const fileNode = root.children.find((c) => c.name === 'main.js')
      expect(fileNode.type).toBe('file')
      expect(fileNode.children).toBeUndefined()
      expect(fileNode.loaded).toBeUndefined()
      const dirNode = root.children.find((c) => c.name === 'src')
      expect(dirNode.type).toBe('directory')
      expect(dirNode.children).toEqual([])
      expect(dirNode.loaded).toBe(false)
      expect(dirNode.expanded).toBe(false)
    })
  })

  describe('toggleNodeExpand（经 handleFileTreeNodeClick 触发）/ getVisibleFileTreeNodes', () => {
    it('展开未加载节点时加载子节点，再次调用收缩', async () => {
      const agent = makeAgent()
      const { api, fetchWithAuth } = makeHarness({
        agent,
        directoryItems: [{ name: 'src', path: '/home/user/proj/src', type: 'directory' }],
      })
      await api.initFileTree('agent-1', '/home/user/proj')
      // 根已由 initFileTree 加载；src 子目录尚未加载
      const root = api.fileTreeState.value.get('agent-1')[0]
      const srcNode = root.children.find((c) => c.name === 'src')
      expect(srcNode.loaded).toBe(false)
      const callsBefore = fetchWithAuth.mock.calls.length
      // 展开 src（内部调用 toggleNodeExpand → loadFileTreeNode）
      await api.handleFileTreeNodeClick('agent-1', srcNode)
      expect(srcNode.expanded).toBe(true)
      expect(api.fileTreeExpanded.value.get('agent-1').has(srcNode.path)).toBe(true)
      expect(fetchWithAuth.mock.calls.length).toBeGreaterThan(callsBefore) // 加载了子节点
      expect(srcNode.loaded).toBe(true)
      // 收缩
      await api.handleFileTreeNodeClick('agent-1', srcNode)
      expect(srcNode.expanded).toBe(false)
      expect(api.fileTreeExpanded.value.get('agent-1').has(srcNode.path)).toBe(false)
    })

    it('已加载节点再次展开不再请求后端', async () => {
      const agent = makeAgent()
      const { api, fetchWithAuth } = makeHarness({
        agent,
        directoryItems: [{ name: 'a.js', path: '/home/user/proj/a.js', type: 'file' }],
      })
      await api.initFileTree('agent-1', '/home/user/proj')
      const root = api.fileTreeState.value.get('agent-1')[0]
      await api.handleFileTreeNodeClick('agent-1', root)
      const callsAfterFirstExpand = fetchWithAuth.mock.calls.length
      await api.handleFileTreeNodeClick('agent-1', root) // 收缩
      await api.handleFileTreeNodeClick('agent-1', root) // 再展开（已 loaded）
      expect(fetchWithAuth.mock.calls.length).toBe(callsAfterFirstExpand)
    })

    it('getVisibleFileTreeNodes 按展开状态展平', async () => {
      const agent = makeAgent()
      const { api } = makeHarness({
        agent,
        directoryItems: [
          { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' },
          { name: 'src', path: '/home/user/proj/src', type: 'directory' },
        ],
      })
      await api.initFileTree('agent-1', '/home/user/proj')
      const root = api.fileTreeState.value.get('agent-1')[0]
      // 折叠时只有根
      expect(api.getVisibleFileTreeNodes('agent-1').map((x) => x.node.path)).toEqual(['/home/user/proj'])
      // 展开根后出现子节点
      await api.handleFileTreeNodeClick('agent-1', root)
      const visible = api.getVisibleFileTreeNodes('agent-1').map((x) => x.node.path)
      expect(visible).toEqual(['/home/user/proj', '/home/user/proj/a.js', '/home/user/proj/src'])
      // 深度：根 0，子节点 1
      const depths = api.getVisibleFileTreeNodes('agent-1').map((x) => x.depth)
      expect(depths).toEqual([0, 1, 1])
    })
  })

  describe('getFileTypeIcon', () => {
    it('目录返回文件夹 SVG', () => {
      const { api } = makeHarness()
      const icon = api.getFileTypeIcon({ name: 'src', path: '/x/src', type: 'directory' })
      expect(icon).toContain('<svg')
    })
    it('按扩展名映射图标', () => {
      const { api } = makeHarness()
      expect(api.getFileTypeIcon({ name: 'main.js', path: '/x/main.js', type: 'file' })).toContain('/file-icons/javascript.svg')
      expect(api.getFileTypeIcon({ name: 'app.py', path: '/x/app.py', type: 'file' })).toContain('/file-icons/python.svg')
      expect(api.getFileTypeIcon({ name: 'readme.md', path: '/x/readme.md', type: 'file' })).toContain('/file-icons/markdown.svg')
    })
    it('未知扩展名回退通用文件图标', () => {
      const { api } = makeHarness()
      expect(api.getFileTypeIcon({ name: 'unknown.zzz', path: '/x/unknown.zzz', type: 'file' })).toContain('/file-icons/document.svg')
    })
    it('按完整文件名匹配（.gitignore）', () => {
      const { api } = makeHarness()
      expect(api.getFileTypeIcon({ name: '.gitignore', path: '/x/.gitignore', type: 'file' })).toContain('/file-icons/git.svg')
    })
  })

  describe('handleFileTreeNodeClick / selectFileTreeNode', () => {
    it('点击目录切换展开', async () => {
      const agent = makeAgent()
      const { api } = makeHarness({ agent })
      await api.initFileTree('agent-1', '/home/user/proj')
      const root = api.fileTreeState.value.get('agent-1')[0]
      await api.handleFileTreeNodeClick('agent-1', root)
      expect(root.expanded).toBe(true)
    })
    it('点击文件打开工作区文件', async () => {
      const agent = makeAgent()
      const { api, openWorkspaceFile } = makeHarness({ agent })
      const fileNode = { name: 'main.js', path: '/home/user/proj/main.js', type: 'file' }
      await api.handleFileTreeNodeClick('agent-1', fileNode)
      expect(openWorkspaceFile).toHaveBeenCalledWith('/home/user/proj/main.js', 'agent-1')
    })
    it('selectFileTreeNode 记录光标选中', () => {
      const { api } = makeHarness()
      api.selectFileTreeNode('agent-1', { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' })
      expect(api.fileTreeSelectedAgentId.value).toBe('agent-1')
      expect(api.fileTreeSelectedPath.value).toBe('/home/user/proj/a.js')
    })
  })

  describe('toggleAgentExpanded', () => {
    it('展开 Agent 并初始化文件树', async () => {
      const agent = makeAgent()
      const { api } = makeHarness({ agent })
      api.toggleAgentExpanded('agent-1')
      expect(api.selectedAgentId.value).toBe('agent-1')
      expect(api.expandedAgents.value.has('agent-1')).toBe(true)
      await flush()
      expect(api.fileTreeState.value.has('agent-1')).toBe(true)
    })
    it('再次调用收缩 Agent', () => {
      const agent = makeAgent()
      const { api } = makeHarness({ agent })
      api.toggleAgentExpanded('agent-1')
      api.toggleAgentExpanded('agent-1')
      expect(api.expandedAgents.value.has('agent-1')).toBe(false)
    })
  })

  describe('toggleStoppedNodeCollapse / isStoppedNodeCollapsed', () => {
    it('切换折叠状态', () => {
      const { api } = makeHarness()
      expect(api.isStoppedNodeCollapsed('n1')).toBe(false)
      api.toggleStoppedNodeCollapse('n1')
      expect(api.isStoppedNodeCollapsed('n1')).toBe(true)
      api.toggleStoppedNodeCollapse('n1')
      expect(api.isStoppedNodeCollapsed('n1')).toBe(false)
    })
  })

  describe('handleFileTreeKeydown', () => {
    it('ArrowDown 移动光标到下一个可见节点', async () => {
      const agent = makeAgent()
      const { api } = makeHarness({
        agent,
        directoryItems: [
          { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' },
          { name: 'b.js', path: '/home/user/proj/b.js', type: 'file' },
        ],
      })
      await api.initFileTree('agent-1', '/home/user/proj')
      const root = api.fileTreeState.value.get('agent-1')[0]
      await api.handleFileTreeNodeClick('agent-1', root)
      // 初始无选中 → ArrowDown 选中第一个可见节点（根）
      const evt = { key: 'ArrowDown', preventDefault: vi.fn() }
      await api.handleFileTreeKeydown(evt, 'agent-1')
      expect(evt.preventDefault).toHaveBeenCalled()
      expect(api.fileTreeSelectedPath.value).toBe('/home/user/proj')
      // 再按 ArrowDown → 选中 a.js
      const evt2 = { key: 'ArrowDown', preventDefault: vi.fn() }
      await api.handleFileTreeKeydown(evt2, 'agent-1')
      expect(api.fileTreeSelectedPath.value).toBe('/home/user/proj/a.js')
    })
    it('Enter 打开选中的文件', async () => {
      const agent = makeAgent()
      const { api, openWorkspaceFile } = makeHarness({
        agent,
        directoryItems: [{ name: 'a.js', path: '/home/user/proj/a.js', type: 'file' }],
      })
      await api.initFileTree('agent-1', '/home/user/proj')
      const root = api.fileTreeState.value.get('agent-1')[0]
      await api.handleFileTreeNodeClick('agent-1', root)
      api.selectFileTreeNode('agent-1', { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' })
      const evt = { key: 'Enter', preventDefault: vi.fn() }
      await api.handleFileTreeKeydown(evt, 'agent-1')
      expect(evt.preventDefault).toHaveBeenCalled()
      expect(openWorkspaceFile).toHaveBeenCalledWith('/home/user/proj/a.js', 'agent-1')
    })
  })

  describe('inputPrompt', () => {
    it('confirmInputPrompt 校验失败时保留弹窗', () => {
      const { api } = makeHarness()
      api.inputPrompt.value = {
        visible: true,
        title: 't',
        label: 'l',
        placeholder: 'p',
        value: '',
        error: '',
        onConfirm: () => '名称不能为空',
      }
      api.confirmInputPrompt()
      expect(api.inputPrompt.value.visible).toBe(true)
      expect(api.inputPrompt.value.error).toBe('名称不能为空')
    })
    it('confirmInputPrompt 成功时关闭弹窗', () => {
      const { api } = makeHarness()
      const onConfirm = vi.fn(() => null)
      api.inputPrompt.value = {
        visible: true,
        title: 't',
        label: 'l',
        placeholder: 'p',
        value: 'x',
        error: '',
        onConfirm,
      }
      api.confirmInputPrompt()
      expect(onConfirm).toHaveBeenCalledWith('x')
      expect(api.inputPrompt.value.visible).toBe(false)
    })
    it('cancelInputPrompt 关闭弹窗', () => {
      const { api } = makeHarness()
      api.inputPrompt.value = { ...api.inputPrompt.value, visible: true, onConfirm: () => null }
      api.cancelInputPrompt()
      expect(api.inputPrompt.value.visible).toBe(false)
    })
  })

  describe('openFileTreeContextMenu', () => {
    it('在视口内弹出菜单并记录坐标', () => {
      const { api } = makeHarness()
      const agent = makeAgent()
      const event = { clientX: 100, clientY: 100 }
      api.openFileTreeContextMenu(agent, null, event)
      expect(api.fileTreeContextMenu.value.visible).toBe(true)
      expect(api.fileTreeContextMenu.value.agentId).toBe('agent-1')
      expect(api.fileTreeContextMenu.value.node).toBeNull()
      expect(api.fileTreeContextMenu.value.x).toBe(100)
      expect(api.fileTreeContextMenu.value.y).toBe(100)
    })
    it('无 agent 或 event 时不弹出', () => {
      const { api } = makeHarness()
      api.openFileTreeContextMenu(null, null, { clientX: 0, clientY: 0 })
      api.openFileTreeContextMenu(makeAgent(), null, null)
      expect(api.fileTreeContextMenu.value.visible).toBe(false)
    })
  })

  describe('fileTreeContextActions', () => {
    it('根节点（无 node）时仅 Agent 级动作可用', () => {
      const { api } = makeHarness({ agent: makeAgent() })
      api.openFileTreeContextMenu(makeAgent(), null, { clientX: 0, clientY: 0 })
      const actions = api.fileTreeContextActions.value
      const ids = actions.filter((a) => a.enabled).map((a) => a.id)
      // 无 node：新建/查找/刷新/上传/复制路径/相对路径可用；下载/复制/剪切/重命名/删除不可用
      expect(ids).toContain('new-file')
      expect(ids).toContain('refresh')
      expect(ids).toContain('upload')
      expect(ids).toContain('copy-path')
      expect(ids).not.toContain('download')
      expect(ids).not.toContain('copy')
      expect(ids).not.toContain('rename')
      expect(ids).not.toContain('delete')
    })
    it('文件节点时下载/复制/剪切/重命名/删除可用', () => {
      const { api } = makeHarness({ agent: makeAgent() })
      const fileNode = { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' }
      api.openFileTreeContextMenu(makeAgent(), fileNode, { clientX: 0, clientY: 0 })
      const actions = api.fileTreeContextActions.value
      const ids = actions.filter((a) => a.enabled).map((a) => a.id)
      expect(ids).toContain('download')
      expect(ids).toContain('copy')
      expect(ids).toContain('cut')
      expect(ids).toContain('rename')
      expect(ids).toContain('delete')
    })
  })

  describe('runFileTreeContextAction', () => {
    it('新建文件：打开输入弹窗，确认后调用后端并刷新', async () => {
      const agent = makeAgent()
      const { api, fetchWithAuth, showToast, openWorkspaceFile } = makeHarness({ agent })
      api.openFileTreeContextMenu(agent, null, { clientX: 0, clientY: 0 })
      const action = api.fileTreeContextActions.value.find((a) => a.id === 'new-file')
      await api.runFileTreeContextAction(action)
      expect(api.inputPrompt.value.visible).toBe(true)
      expect(api.inputPrompt.value.title).toContain('新建文件')
      // 确认
      api.inputPrompt.value.value = 'hello.txt'
      api.confirmInputPrompt()
      await flush()
      // 创建请求
      const createCall = fetchWithAuth.mock.calls.find((c) => String(c[0]).includes('file-create'))
      expect(createCall).toBeTruthy()
      const body = JSON.parse(createCall[1].body)
      expect(body.path).toBe('/home/user/proj/hello.txt')
      expect(body.kind).toBe('file')
      expect(openWorkspaceFile).toHaveBeenCalledWith('/home/user/proj/hello.txt', 'agent-1')
      expect(showToast).toHaveBeenCalledWith('文件已创建', 'success')
    })
    it('新建文件：名称为空时校验失败', async () => {
      const agent = makeAgent()
      const { api, fetchWithAuth } = makeHarness({ agent })
      api.openFileTreeContextMenu(agent, null, { clientX: 0, clientY: 0 })
      const action = api.fileTreeContextActions.value.find((a) => a.id === 'new-file')
      await api.runFileTreeContextAction(action)
      api.inputPrompt.value.value = '   '
      api.confirmInputPrompt()
      expect(api.inputPrompt.value.visible).toBe(true)
      expect(api.inputPrompt.value.error).toBe('名称不能为空')
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })
    it('删除文件：确认后调用后端并刷新', async () => {
      const agent = makeAgent()
      const { api, fetchWithAuth, showToast, showConfirm } = makeHarness({ agent })
      const fileNode = { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' }
      api.openFileTreeContextMenu(agent, fileNode, { clientX: 0, clientY: 0 })
      const action = api.fileTreeContextActions.value.find((a) => a.id === 'delete')
      await api.runFileTreeContextAction(action)
      expect(showConfirm).toHaveBeenCalled()
      await flush()
      const deleteCall = fetchWithAuth.mock.calls.find((c) => String(c[0]).includes('file-delete'))
      expect(deleteCall).toBeTruthy()
      const body = JSON.parse(deleteCall[1].body)
      expect(body.path).toBe('/home/user/proj/a.js')
      expect(showToast).toHaveBeenCalledWith('已删除', 'success')
    })
    it('复制路径：调用剪贴板并提示', async () => {
      const agent = makeAgent()
      const { api, showToast } = makeHarness({ agent })
      const fileNode = { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' }
      api.openFileTreeContextMenu(agent, fileNode, { clientX: 0, clientY: 0 })
      // mock navigator.clipboard
      const writeText = vi.fn().mockResolvedValue(undefined)
      Object.defineProperty(globalThis.navigator, 'clipboard', { value: { writeText }, configurable: true })
      const action = api.fileTreeContextActions.value.find((a) => a.id === 'copy-path')
      await api.runFileTreeContextAction(action)
      expect(writeText).toHaveBeenCalledWith('/home/user/proj/a.js')
      expect(showToast).toHaveBeenCalledWith('路径已复制', 'success')
    })
    it('remove-dir：调用 removeWorkspaceDir', async () => {
      const agent = makeAgent({ virtual: true })
      const { api, removeWorkspaceDir } = makeHarness({ agent })
      api.openFileTreeContextMenu(agent, null, { clientX: 0, clientY: 0 })
      const action = api.fileTreeContextActions.value.find((a) => a.id === 'remove-dir')
      expect(action.enabled).toBe(true)
      await api.runFileTreeContextAction(action)
      expect(removeWorkspaceDir).toHaveBeenCalledWith('agent-1')
    })
    it('find-in-folder：设置搜索 glob 并切换搜索视图', async () => {
      const agent = makeAgent()
      const { api, globalSearchFileGlob, setWorkspaceSidebarView } = makeHarness({ agent })
      const dirNode = { name: 'src', path: '/home/user/proj/src', type: 'directory' }
      api.openFileTreeContextMenu(agent, dirNode, { clientX: 0, clientY: 0 })
      const action = api.fileTreeContextActions.value.find((a) => a.id === 'find-in-folder')
      await api.runFileTreeContextAction(action)
      expect(globalSearchFileGlob.value).toBe('src/**')
      expect(setWorkspaceSidebarView).toHaveBeenCalledWith('search')
    })
  })

  describe('拖拽', () => {
    it('handleFileTreeDragStart 记录源节点', () => {
      const agent = makeAgent()
      const { api } = makeHarness({ agent })
      const fileNode = { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' }
      const event = { dataTransfer: { effectAllowed: '', setData: vi.fn() } }
      api.handleFileTreeDragStart(event, 'agent-1', fileNode)
      expect(event.dataTransfer.effectAllowed).toBe('copyMove')
      expect(event.dataTransfer.setData).toHaveBeenCalledWith('text/plain', '/home/user/proj/a.js')
    })
    it('handleFileTreeDragOver 拒绝非法目标（自身/源所在目录/子孙目录）', () => {
      const agent = makeAgent()
      const { api } = makeHarness({ agent })
      const dirNode = { name: 'src', path: '/home/user/proj/src', type: 'directory' }
      const startEvent = { dataTransfer: { effectAllowed: '', setData: vi.fn() } }
      api.handleFileTreeDragStart(startEvent, 'agent-1', dirNode)
      // 不能拖到自己
      const selfEvent = { preventDefault: vi.fn(), dataTransfer: { dropEffect: '' } }
      api.handleFileTreeDragOver(selfEvent, '/home/user/proj/src')
      expect(selfEvent.preventDefault).not.toHaveBeenCalled()
      expect(api.fileTreeDropTargetPath.value).toBe('')
      // 不能拖到源所在目录
      const parentEvent = { preventDefault: vi.fn(), dataTransfer: { dropEffect: '' } }
      api.handleFileTreeDragOver(parentEvent, '/home/user/proj')
      expect(parentEvent.preventDefault).not.toHaveBeenCalled()
      // 目录不能拖进自己的子孙目录
      const childEvent = { preventDefault: vi.fn(), dataTransfer: { dropEffect: '' } }
      api.handleFileTreeDragOver(childEvent, '/home/user/proj/src/sub')
      expect(childEvent.preventDefault).not.toHaveBeenCalled()
    })
    it('handleFileTreeDragOver 合法目标高亮并设置 dropEffect', () => {
      const agent = makeAgent()
      const { api } = makeHarness({ agent })
      const fileNode = { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' }
      const startEvent = { dataTransfer: { effectAllowed: '', setData: vi.fn() } }
      api.handleFileTreeDragStart(startEvent, 'agent-1', fileNode)
      const overEvent = { preventDefault: vi.fn(), dataTransfer: { dropEffect: '' }, ctrlKey: true }
      api.handleFileTreeDragOver(overEvent, '/home/user/proj/src')
      expect(overEvent.preventDefault).toHaveBeenCalled()
      expect(overEvent.dataTransfer.dropEffect).toBe('copy')
      expect(api.fileTreeDropTargetPath.value).toBe('/home/user/proj/src')
      // 离开清除高亮
      api.handleFileTreeDragLeave('/home/user/proj/src')
      expect(api.fileTreeDropTargetPath.value).toBe('')
    })
    it('handleFileTreeDragEnd 清理拖拽状态', () => {
      const agent = makeAgent()
      const { api } = makeHarness({ agent })
      const fileNode = { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' }
      const startEvent = { dataTransfer: { effectAllowed: '', setData: vi.fn() } }
      api.handleFileTreeDragStart(startEvent, 'agent-1', fileNode)
      api.handleFileTreeDragEnd()
      expect(api.fileTreeDropTargetPath.value).toBe('')
    })
  })

  describe('复制粘贴', () => {
    it('复制文件后粘贴到另一目录（调用 file-rename 为移动 / file-write 为复制）', async () => {
      const agent = makeAgent()
      const { api, fetchWithAuth, fetchFileContent, showToast } = makeHarness({ agent })
      // 复制：通过右键菜单 copy
      const fileNode = { name: 'a.js', path: '/home/user/proj/a.js', type: 'file' }
      api.openFileTreeContextMenu(agent, fileNode, { clientX: 0, clientY: 0 })
      const copyAction = api.fileTreeContextActions.value.find((a) => a.id === 'copy')
      await api.runFileTreeContextAction(copyAction)
      expect(fetchFileContent).toHaveBeenCalledWith('/home/user/proj/a.js', 'agent-1')
      expect(showToast).toHaveBeenCalledWith('已复制，可在目标目录粘贴', 'success')
      // 粘贴到 src 目录
      const dirNode = { name: 'src', path: '/home/user/proj/src', type: 'directory' }
      api.openFileTreeContextMenu(agent, dirNode, { clientX: 0, clientY: 0 })
      const pasteAction = api.fileTreeContextActions.value.find((a) => a.id === 'paste')
      expect(pasteAction.enabled).toBe(true)
      await api.runFileTreeContextAction(pasteAction)
      await flush()
      const writeCall = fetchWithAuth.mock.calls.find((c) => String(c[0]).includes('file-write'))
      expect(writeCall).toBeTruthy()
      const body = JSON.parse(writeCall[1].body)
      expect(body.path).toBe('/home/user/proj/src/a.js')
      expect(body.content).toBe('content-of-/home/user/proj/a.js')
    })
  })
})
