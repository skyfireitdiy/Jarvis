// useGitView 单元测试
// 覆盖：Git 视图状态（提交历史/分支/详情/diff/范围选择/补丁下载）、目标 Agent 解析、
// diff pane 多实例管理（Monaco DiffEditor mock）、提交右键菜单与复制、展示工具函数。
// mock monaco-editor（jsdom 无法加载 worker），与 useTerminal.test.js mock xterm 同风格。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useGitView } from './useGitView.js'

// ---- mock monaco-editor（用 vi.hoisted 让工厂可引用，且测试内可访问同一实例）----
const { monacoMock, MockDiffEditor, MockModel } = vi.hoisted(() => {
  class MockModel {
    constructor(text, language) {
      this.text = text
      this.language = language
      this._disposed = false
    }
    isDisposed() { return this._disposed }
    dispose() { this._disposed = true }
    getValue() { return this.text }
  }
  class MockDiffEditor {
    constructor(container, options) {
      this.container = container
      this.options = options
      this.models = null
      this._disposed = false
      this._layoutCount = 0
      this._updateOptions = []
      this._goToDiff = null
      this._focused = false
    }
    setModel(models) { this.models = models }
    updateOptions(opts) { this._updateOptions.push(opts) }
    layout() { this._layoutCount += 1 }
    dispose() { this._disposed = true }
    getContainerDomNode() { return this.container }
    goToDiff(target) { this._goToDiff = target }
    focus() { this._focused = true }
  }
  const monacoMock = {
    editor: {
      createDiffEditor: vi.fn(),
      createModel: vi.fn(),
    },
  }
  return { monacoMock, MockDiffEditor, MockModel }
})

vi.mock('monaco-editor/esm/vs/editor/editor.main.js', () => monacoMock)

// ---- mock 全局环境 ----
function setupGlobals() {
  // requestAnimationFrame（jsdom 默认有，但用 setTimeout 保证测试可控）
  globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 0)
  // 下载补丁用到的 DOM API
  // jsdom 自带 createObjectURL stub 但会读 blob._bytes 抛错，强制覆盖为可控 mock
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  globalThis.URL.revokeObjectURL = vi.fn()
}

// 刷新所有微任务（async 函数多层 await 时用）
async function flushPromises() {
  for (let i = 0; i < 20; i++) {
    await Promise.resolve()
  }
}

// 构造 useGitView 依赖注入 harness
function makeHarness(overrides = {}) {
  // —— 直传依赖（定义在调用点之前）——
  const EDITOR_FONT_FAMILY = "'Consolas', monospace"
  const buildNodeHttpUrl = vi.fn((host, port, nodeId, path) => `http://${host}:${port}/api/node/${nodeId}/${path}`)
  const fetchWithAuth = vi.fn()
  const getGatewayAddress = vi.fn(() => ({ host: '127.0.0.1', port: '8000' }))
  const getLanguageExtension = vi.fn((ext) => ext || 'plaintext')
  const getLanguageFromFilename = vi.fn((path) => (path ? path.split('.').pop() : ''))
  const windowWidth = ref(1200)
  const activeWorkspaceSessionId = ref(null)
  const ensurePaneForView = vi.fn(() => null)
  const findWorkspacePaneById = vi.fn((node, paneId) => {
    if (!node) return null
    if (node.type === 'leaf') return node.id === paneId ? node : null
    for (const child of node.children || []) {
      const found = findWorkspacePaneById(child, paneId)
      if (found) return found
    }
    return null
  })
  const gitCustomDir = ref(null)
  const persistWorkspacePaneLayout = vi.fn()
  const resolveDiffContainer = vi.fn(() => null)
  const scheduleWorkspaceLayout = vi.fn()
  const showWorkspacePanel = ref(false)
  const workspacePaneTree = ref({ type: 'leaf', id: 'pane-main', view: 'file' })
  const workspaceSidebarView = ref('git')
  const diffContainerRefs = ref(new Map())
  const diffEditorViews = new Map()
  const openWorkspaceFile = vi.fn(async () => {})
  const activePane = ref(null)
  const getPanePanel = vi.fn(() => null)

  // —— getter 注入依赖（定义在调用点之后）——
  const effectiveGitAgentId = ref(null)
  const agentList = ref([])
  const showToast = vi.fn()
  const viewDiff = vi.fn()
  const copyTextToClipboard = vi.fn(async () => {})
  const getPanelAgent = vi.fn(() => null)
  const getCurrentAgentOrNull = vi.fn(() => null)

  const api = useGitView({
    EDITOR_FONT_FAMILY,
    buildNodeHttpUrl,
    fetchWithAuth,
    getGatewayAddress,
    getLanguageExtension,
    getLanguageFromFilename,
    windowWidth,
    activeWorkspaceSessionId,
    ensurePaneForView,
    findWorkspacePaneById,
    gitCustomDir,
    persistWorkspacePaneLayout,
    resolveDiffContainer,
    scheduleWorkspaceLayout,
    showWorkspacePanel,
    workspacePaneTree,
    workspaceSidebarView,
    diffContainerRefs,
    diffEditorViews,
    openWorkspaceFile,
    activePane,
    getPanePanel,
    // getter 注入（useGitView 内部以 xxx() 二次求值）
    effectiveGitAgentId: () => effectiveGitAgentId,
    agentList: () => agentList,
    showToast: () => showToast,
    viewDiff: () => viewDiff,
    copyTextToClipboard: () => copyTextToClipboard,
    getPanelAgent: () => getPanelAgent,
    getCurrentAgentOrNull: () => getCurrentAgentOrNull,
    ...overrides,
  })

  return {
    api,
    EDITOR_FONT_FAMILY,
    buildNodeHttpUrl,
    fetchWithAuth,
    getGatewayAddress,
    getLanguageExtension,
    getLanguageFromFilename,
    windowWidth,
    activeWorkspaceSessionId,
    ensurePaneForView,
    findWorkspacePaneById,
    gitCustomDir,
    persistWorkspacePaneLayout,
    resolveDiffContainer,
    scheduleWorkspaceLayout,
    showWorkspacePanel,
    workspacePaneTree,
    workspaceSidebarView,
    diffContainerRefs,
    diffEditorViews,
    openWorkspaceFile,
    activePane,
    getPanePanel,
    effectiveGitAgentId,
    agentList,
    showToast,
    viewDiff,
    copyTextToClipboard,
    getPanelAgent,
    getCurrentAgentOrNull,
  }
}

// 构造一个合法 Agent（与后端返回结构一致）
function makeAgent(id, workingDir = '/home/user/project') {
  return { agent_id: id, name: `Agent ${id}`, node_id: 'node-1', working_dir: workingDir }
}

// 构造一个合法 commit
function makeCommit(hash, subject = 'fix bug', refs = ['HEAD', 'main']) {
  return {
    hash,
    subject,
    refs,
    author: 'Alice',
    email: 'alice@example.com',
    date: '2024-01-01 12:00:00',
    body: '',
  }
}

beforeEach(() => {
  setupGlobals()
  monacoMock.editor.createDiffEditor.mockReset()
  monacoMock.editor.createModel.mockReset()
  monacoMock.editor.createDiffEditor.mockImplementation((container, options) => new MockDiffEditor(container, options))
  monacoMock.editor.createModel.mockImplementation((text, language) => new MockModel(text, language))
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useGitView', () => {
  it('暴露预期接口', () => {
    const { api } = makeHarness()
    // refs / computed
    expect(typeof api.gitLog).toBe('object')
    expect(typeof api.gitLogLoading).toBe('object')
    expect(typeof api.gitLogError).toBe('object')
    expect(typeof api.gitLogHasMore).toBe('object')
    expect(typeof api.gitLogTotal).toBe('object')
    expect(typeof api.gitBranches).toBe('object')
    expect(typeof api.gitTags).toBe('object')
    expect(typeof api.gitCurrentBranch).toBe('object')
    expect(typeof api.gitSelectedCommit).toBe('object')
    expect(typeof api.gitRangeSelectMode).toBe('object')
    expect(typeof api.gitSelectedCommits).toBe('object')
    expect(typeof api.gitPatchLoading).toBe('object')
    expect(typeof api.gitCommitFiles).toBe('object')
    expect(typeof api.gitCommitDetailLoading).toBe('object')
    expect(typeof api.gitSelectedFile).toBe('object')
    expect(typeof api.gitDiffText).toBe('object')
    expect(typeof api.gitDiffLoading).toBe('object')
    expect(typeof api.gitDiffError).toBe('object')
    expect(typeof api.gitDiffTruncated).toBe('object')
    expect(typeof api.gitDiffSideBySide).toBe('object')
    expect(typeof api.gitDiffShowFull).toBe('object')
    expect(typeof api.pluginSidebarWorkingDir).toBe('object')
    expect(typeof api.pluginActiveAgentInfo).toBe('object')
    expect(typeof api.gitCommitContextMenu).toBe('object')
    expect(typeof api.gitCommitInfoModal).toBe('object')
    // 常量
    expect(api.GIT_LOG_PAGE_SIZE).toBe(100)
    // 函数
    for (const fn of [
      'isNarrowGitDiffViewport', 'getGitTargetAgent', 'getGitTargetNodeId', 'getGitWorkingDir',
      'callGitApi', 'fetchGitLog', 'fetchGitBranches', 'refreshGitView', 'toggleGitCommitDetail',
      'enterGitRangeSelect', 'exitGitRangeSelect', 'toggleGitRangeSelect', 'downloadGitPatch',
      'viewGitTargetDiff', 'onDiffTitleClick', 'onOpenDiffFileFromMessage', 'viewGitFileDiff',
      'ensureGitDiffFullText', 'layoutGitDiffEditor', 'disposeDiffEditorForPane',
      'disposeAllDiffEditors', 'ensureDiffEditorForPane', 'renderDiffForPane', 'loadDiffForPane',
      'togglePaneDiffSideBySide', 'togglePaneDiffShowFull', 'navigatePaneDiff', 'closePaneDiff',
      'scheduleDiffLayout', 'gitRefClass', 'gitFileStatus', 'formatGitRelativeTime', 'shortGitHash',
      'closeGitCommitContextMenu', 'openGitCommitContextMenu', 'copyGitCommit', 'copyGitCommitId',
      'formatGitCommitInfo', 'formatGitCommitTooltip', 'showGitCommitInfoModal',
    ]) {
      expect(typeof api[fn]).toBe('function')
    }
  })

  it('初始状态：空列表、未加载、无错误', () => {
    const { api } = makeHarness()
    expect(api.gitLog.value).toEqual([])
    expect(api.gitLogLoading.value).toBe(false)
    expect(api.gitLogError.value).toBe('')
    expect(api.gitLogHasMore.value).toBe(false)
    expect(api.gitLogTotal.value).toBe(null)
    expect(api.gitBranches.value).toEqual([])
    expect(api.gitTags.value).toEqual([])
    expect(api.gitCurrentBranch.value).toBe('')
    expect(api.gitSelectedCommit.value).toBe(null)
    expect(api.gitRangeSelectMode.value).toBe(false)
    expect(api.gitSelectedCommits.value).toEqual(new Set())
    expect(api.gitPatchLoading.value).toBe(false)
    expect(api.gitCommitFiles.value).toEqual([])
    expect(api.gitCommitDetailLoading.value).toBe(false)
    expect(api.gitSelectedFile.value).toBe(null)
    expect(api.gitDiffText.value).toBe('')
    expect(api.gitDiffLoading.value).toBe(false)
    expect(api.gitDiffError.value).toBe('')
    expect(api.gitDiffTruncated.value).toBe(false)
    expect(api.gitDiffShowFull.value).toBe(false)
    expect(api.gitCommitContextMenu.value).toEqual({ visible: false, x: 0, y: 0, commit: null })
    expect(api.gitCommitInfoModal.value).toBe(null)
  })

  describe('getGitTargetAgent / getGitTargetNodeId / getGitWorkingDir', () => {
    it('无 Git 目标 Agent 时返回 null / 空', () => {
      const { api } = makeHarness()
      expect(api.getGitTargetAgent()).toBe(null)
      expect(api.getGitTargetNodeId()).toBe('')
      expect(api.getGitWorkingDir()).toBe('')
    })
    it('按 effectiveGitAgentId 找到目标 Agent', () => {
      const { api, effectiveGitAgentId, agentList } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a'), makeAgent('a2', '/work/b')]
      effectiveGitAgentId.value = 'a2'
      expect(api.getGitTargetAgent().agent_id).toBe('a2')
      expect(api.getGitTargetNodeId()).toBe('node-1')
      expect(api.getGitWorkingDir()).toBe('/work/b')
    })
    it('找不到 Agent 时回退空', () => {
      const { api, effectiveGitAgentId, agentList } = makeHarness()
      agentList.value = [makeAgent('a1')]
      effectiveGitAgentId.value = 'nonexistent'
      expect(api.getGitTargetAgent()).toBe(null)
      expect(api.getGitTargetNodeId()).toBe('')
      expect(api.getGitWorkingDir()).toBe('')
    })
    it('自定义 Git 目录优先于 Agent', () => {
      const { api, effectiveGitAgentId, agentList, gitCustomDir } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      gitCustomDir.value = { nodeId: 'custom-node', path: '/custom/path' }
      expect(api.getGitTargetNodeId()).toBe('custom-node')
      expect(api.getGitWorkingDir()).toBe('/custom/path')
    })
  })

  describe('pluginSidebarWorkingDir / pluginActiveAgentInfo', () => {
    it('pluginSidebarWorkingDir 跟随工作目录', () => {
      const { api, effectiveGitAgentId, agentList } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      expect(api.pluginSidebarWorkingDir.value).toBe('/work/a')
    })
    it('pluginActiveAgentInfo 返回 Agent 信息（无 Agent 时 null）', () => {
      const { api, effectiveGitAgentId, agentList } = makeHarness()
      expect(api.pluginActiveAgentInfo.value).toBe(null)
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      expect(api.pluginActiveAgentInfo.value).toEqual({
        agentId: 'a1',
        agentName: 'Agent a1',
        workingDir: '/work/a',
      })
    })
  })

  describe('isNarrowGitDiffViewport', () => {
    it('窗口宽度 <= 768 为窄屏', () => {
      const { api, windowWidth } = makeHarness()
      windowWidth.value = 768
      expect(api.isNarrowGitDiffViewport()).toBe(true)
      windowWidth.value = 769
      expect(api.isNarrowGitDiffViewport()).toBe(false)
    })
  })

  describe('callGitApi', () => {
    it('构造请求并解析成功响应', async () => {
      const { api, fetchWithAuth, buildNodeHttpUrl, getGatewayAddress, effectiveGitAgentId, agentList } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { commits: [] } }),
      })
      const data = await api.callGitApi('git/log', { path: '/work/a' })
      expect(getGatewayAddress).toHaveBeenCalled()
      expect(buildNodeHttpUrl).toHaveBeenCalledWith('127.0.0.1', '8000', 'node-1', 'git/log')
      const [url, opts] = fetchWithAuth.mock.calls[0]
      expect(url).toBe('http://127.0.0.1:8000/api/node/node-1/git/log')
      expect(opts.method).toBe('POST')
      expect(JSON.parse(opts.body)).toEqual({ path: '/work/a', node_id: 'node-1' })
      expect(data).toEqual({ commits: [] })
    })
    it('无目标节点时回退 master', async () => {
      const { api, fetchWithAuth } = makeHarness()
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: {} }),
      })
      await api.callGitApi('git/log', {})
      const [url] = fetchWithAuth.mock.calls[0]
      expect(url).toContain('/master/git/log')
    })
    it('失败响应抛出错误', async () => {
      const { api, fetchWithAuth } = makeHarness()
      fetchWithAuth.mockResolvedValue({
        ok: false,
        json: async () => ({ success: false, error: { message: '权限不足' } }),
      })
      await expect(api.callGitApi('git/log', {})).rejects.toThrow('权限不足')
    })
    it('无 message 时用通用文案', async () => {
      const { api, fetchWithAuth } = makeHarness()
      fetchWithAuth.mockResolvedValue({
        ok: false,
        json: async () => ({ success: false, error: {} }),
      })
      await expect(api.callGitApi('git/log', {})).rejects.toThrow('Git 请求失败')
    })
  })

  describe('fetchGitLog', () => {
    it('无工作目录时置错误并清空列表', async () => {
      const { api } = makeHarness()
      await api.fetchGitLog()
      expect(api.gitLogError.value).toBe('当前 Agent 没有工作目录')
      expect(api.gitLog.value).toEqual([])
      expect(api.gitLogTotal.value).toBe(null)
    })
    it('成功拉取提交列表（非追加）', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { commits: [makeCommit('abc123')], has_more: true, total: 150 } }),
      })
      await api.fetchGitLog()
      expect(api.gitLog.value).toEqual([makeCommit('abc123')])
      expect(api.gitLogHasMore.value).toBe(true)
      expect(api.gitLogTotal.value).toBe(150)
      expect(api.gitLogLoading.value).toBe(false)
      expect(api.gitLogError.value).toBe('')
      // 校验请求体：limit=100, skip=0
      const [, opts] = fetchWithAuth.mock.calls[0]
      expect(JSON.parse(opts.body)).toMatchObject({ path: '/work/a', limit: 100, skip: 0 })
    })
    it('追加模式：skip=现有长度且合并', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      api.gitLog.value = [makeCommit('old1')]
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { commits: [makeCommit('new1')], has_more: false } }),
      })
      await api.fetchGitLog(true)
      const [, opts] = fetchWithAuth.mock.calls[0]
      expect(JSON.parse(opts.body)).toMatchObject({ skip: 1 })
      expect(api.gitLog.value).toEqual([makeCommit('old1'), makeCommit('new1')])
      expect(api.gitLogHasMore.value).toBe(false)
    })
    it('失败时记录错误并清空（非追加）', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      fetchWithAuth.mockResolvedValue({
        ok: false,
        json: async () => ({ success: false, error: { message: '网络错误' } }),
      })
      await api.fetchGitLog()
      expect(api.gitLogError.value).toBe('网络错误')
      expect(api.gitLog.value).toEqual([])
      expect(api.gitLogTotal.value).toBe(null)
      expect(api.gitLogLoading.value).toBe(false)
    })
    it('失败时保留已有列表（追加模式）', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      api.gitLog.value = [makeCommit('old1')]
      fetchWithAuth.mockRejectedValue(new Error('超时'))
      await api.fetchGitLog(true)
      expect(api.gitLogError.value).toBe('超时')
      expect(api.gitLog.value).toEqual([makeCommit('old1')])
    })
  })

  describe('fetchGitBranches', () => {
    it('成功拉取分支/tag/当前分支', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { branches: ['main', 'dev'], tags: ['v1.0'], current: 'dev' } }),
      })
      await api.fetchGitBranches()
      expect(api.gitBranches.value).toEqual(['main', 'dev'])
      expect(api.gitTags.value).toEqual(['v1.0'])
      expect(api.gitCurrentBranch.value).toBe('dev')
    })
    it('无工作目录时静默返回', async () => {
      const { api, fetchWithAuth } = makeHarness()
      await api.fetchGitBranches()
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })
    it('失败时清空分支信息（不抛错）', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      api.gitBranches.value = ['stale']
      fetchWithAuth.mockRejectedValue(new Error('boom'))
      await api.fetchGitBranches()
      expect(api.gitBranches.value).toEqual([])
      expect(api.gitTags.value).toEqual([])
      expect(api.gitCurrentBranch.value).toBe('')
    })
  })

  describe('refreshGitView', () => {
    it('重置详情状态并同时拉取历史与分支', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      api.gitSelectedCommit.value = 'abc'
      api.gitCommitFiles.value = [{ file_path: 'x' }]
      api.gitSelectedFile.value = 'x'
      api.gitDiffText.value = 'old'
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { commits: [], has_more: false } }),
      })
      await api.refreshGitView()
      expect(api.gitSelectedCommit.value).toBe(null)
      expect(api.gitCommitFiles.value).toEqual([])
      expect(api.gitSelectedFile.value).toBe(null)
      expect(api.gitDiffText.value).toBe('')
      expect(api.gitDiffError.value).toBe('')
      expect(fetchWithAuth).toHaveBeenCalledTimes(2) // git/log + git/branches
    })
  })

  describe('toggleGitCommitDetail', () => {
    it('再次点击同一提交时收起', async () => {
      const { api, effectiveGitAgentId, agentList } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      api.gitSelectedCommit.value = 'abc'
      api.gitCommitFiles.value = [{ file_path: 'x' }]
      api.gitSelectedFile.value = 'x'
      api.gitDiffText.value = 'old'
      await api.toggleGitCommitDetail(makeCommit('abc'))
      expect(api.gitSelectedCommit.value).toBe(null)
      expect(api.gitCommitFiles.value).toEqual([])
      expect(api.gitSelectedFile.value).toBe(null)
      expect(api.gitDiffText.value).toBe('')
    })
    it('展开提交详情：拉取文件变更列表', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { files: [{ file_path: 'a.py', additions: 1, deletions: 0 }] } }),
      })
      await api.toggleGitCommitDetail(makeCommit('abc'))
      expect(api.gitSelectedCommit.value).toBe('abc')
      expect(api.gitCommitFiles.value).toEqual([{ file_path: 'a.py', additions: 1, deletions: 0 }])
      expect(api.gitCommitDetailLoading.value).toBe(false)
    })
    it('无工作目录时展开但不请求', async () => {
      const { api, fetchWithAuth } = makeHarness()
      await api.toggleGitCommitDetail(makeCommit('abc'))
      expect(api.gitSelectedCommit.value).toBe('abc')
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })
    it('拉取失败时记录错误', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      fetchWithAuth.mockRejectedValue(new Error('detail fail'))
      await api.toggleGitCommitDetail(makeCommit('abc'))
      expect(api.gitDiffError.value).toBe('detail fail')
      expect(api.gitCommitDetailLoading.value).toBe(false)
    })
  })

  describe('范围选择 enter/exit/toggle', () => {
    it('enterGitRangeSelect 清空已选并退出详情', () => {
      const { api } = makeHarness()
      api.gitRangeSelectMode.value = false
      api.gitSelectedCommit.value = 'abc'
      api.gitCommitFiles.value = [{ file_path: 'x' }]
      api.gitSelectedFile.value = 'x'
      api.gitDiffText.value = 'old'
      api.enterGitRangeSelect()
      expect(api.gitRangeSelectMode.value).toBe(true)
      expect(api.gitSelectedCommits.value).toEqual(new Set())
      expect(api.gitSelectedCommit.value).toBe(null)
      expect(api.gitCommitFiles.value).toEqual([])
      expect(api.gitSelectedFile.value).toBe(null)
      expect(api.gitDiffText.value).toBe('')
    })
    it('exitGitRangeSelect 清空已选', () => {
      const { api } = makeHarness()
      api.gitRangeSelectMode.value = true
      api.gitSelectedCommits.value = new Set(['abc'])
      api.exitGitRangeSelect()
      expect(api.gitRangeSelectMode.value).toBe(false)
      expect(api.gitSelectedCommits.value).toEqual(new Set())
    })
    it('toggleGitRangeSelect 切换选中状态并触发响应式更新', () => {
      const { api } = makeHarness()
      api.toggleGitRangeSelect(makeCommit('abc'))
      expect(api.gitSelectedCommits.value.has('abc')).toBe(true)
      api.toggleGitRangeSelect(makeCommit('abc'))
      expect(api.gitSelectedCommits.value.has('abc')).toBe(false)
      api.toggleGitRangeSelect(makeCommit('def'))
      expect(api.gitSelectedCommits.value).toEqual(new Set(['def']))
    })
  })

  describe('downloadGitPatch', () => {
    it('无工作目录时直接返回', async () => {
      const { api, fetchWithAuth } = makeHarness()
      await api.downloadGitPatch()
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })
    it('未选提交时 toast 提示', async () => {
      const { api, effectiveGitAgentId, agentList, showToast } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      await api.downloadGitPatch()
      expect(showToast).toHaveBeenCalledWith('请先选择至少一个提交', 'error')
    })
    it('单个 commit 下载 .patch', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth, showToast } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      api.gitSelectedCommits.value = new Set(['abc'])
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { format: 'patch', filename: 'abc.patch', content: 'diff --git a/x b/x' } }),
      })
      await api.downloadGitPatch()
      const [, opts] = fetchWithAuth.mock.calls[0]
      expect(JSON.parse(opts.body)).toMatchObject({ path: '/work/a', commits: ['abc'] })
      expect(showToast).toHaveBeenCalledWith('已下载 abc.patch', 'success')
      expect(api.gitPatchLoading.value).toBe(false)
    })
    it('多个 commit 下载 tar.gz（base64 解码）', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth, showToast } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      api.gitSelectedCommits.value = new Set(['abc', 'def'])
      const base64 = btoa('binary-data')
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { format: 'tar.gz', filename: 'patch.tar.gz', content_base64: base64 } }),
      })
      await api.downloadGitPatch()
      expect(showToast).toHaveBeenCalledWith('已下载 patch.tar.gz', 'success')
      expect(api.gitPatchLoading.value).toBe(false)
    })
    it('数据无效时 toast 错误', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth, showToast } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      api.gitSelectedCommits.value = new Set(['abc'])
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: {} }),
      })
      await api.downloadGitPatch()
      expect(showToast).toHaveBeenCalledWith('补丁数据无效', 'error')
    })
  })

  describe('viewGitTargetDiff', () => {
    it('无目标 Agent 时 toast 提示', () => {
      const { api, showToast } = makeHarness()
      api.viewGitTargetDiff()
      expect(showToast).toHaveBeenCalledWith('请先选择 Git 目标 Agent', 'error')
    })
    it('有目标 Agent 时调用 viewDiff（getter 二次求值）', () => {
      const { api, effectiveGitAgentId, agentList, viewDiff } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      api.viewGitTargetDiff()
      expect(viewDiff).toHaveBeenCalledWith(makeAgent('a1', '/work/a'))
    })
  })

  describe('onDiffTitleClick', () => {
    it('无 filePath 时直接返回', async () => {
      const { api, openWorkspaceFile } = makeHarness()
      await api.onDiffTitleClick({}, { diff: {} })
      expect(openWorkspaceFile).not.toHaveBeenCalled()
    })
    it('相对路径拼接工作目录后打开', async () => {
      const { api, effectiveGitAgentId, agentList, openWorkspaceFile } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      const event = { preventDefault: vi.fn(), stopPropagation: vi.fn() }
      await api.onDiffTitleClick(event, { diff: { filePath: 'src/x.py' } })
      expect(event.preventDefault).toHaveBeenCalled()
      expect(event.stopPropagation).toHaveBeenCalled()
      expect(openWorkspaceFile).toHaveBeenCalledWith('/work/a/src/x.py', 'a1')
    })
    it('绝对路径直接打开', async () => {
      const { api, effectiveGitAgentId, agentList, openWorkspaceFile } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      await api.onDiffTitleClick({ preventDefault: vi.fn(), stopPropagation: vi.fn() }, { diff: { filePath: '/abs/x.py' } })
      expect(openWorkspaceFile).toHaveBeenCalledWith('/abs/x.py', 'a1')
    })
    it('无工作目录时直接返回', async () => {
      const { api, openWorkspaceFile } = makeHarness()
      await api.onDiffTitleClick({ preventDefault: vi.fn(), stopPropagation: vi.fn() }, { diff: { filePath: 'src/x.py' } })
      expect(openWorkspaceFile).not.toHaveBeenCalled()
    })
  })

  describe('onOpenDiffFileFromMessage', () => {
    it('无 filePath 时直接返回', async () => {
      const { api, openWorkspaceFile } = makeHarness()
      await api.onOpenDiffFileFromMessage('')
      expect(openWorkspaceFile).not.toHaveBeenCalled()
    })
    it('按会话 Agent 工作目录拼接并打开', async () => {
      const { api, activePane, getPanePanel, getPanelAgent, openWorkspaceFile } = makeHarness()
      const pane = { view: 'session', sessionPanelId: 'panel-1' }
      activePane.value = pane
      getPanePanel.mockReturnValue({ id: 'panel-1' })
      getPanelAgent.mockReturnValue(makeAgent('a1', '/work/a'))
      await api.onOpenDiffFileFromMessage('src/x.py')
      expect(openWorkspaceFile).toHaveBeenCalledWith('/work/a/src/x.py', 'a1')
    })
    it('无会话 Agent 时回退 Git 目标工作目录', async () => {
      const { api, effectiveGitAgentId, agentList, openWorkspaceFile } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      await api.onOpenDiffFileFromMessage('src/x.py')
      expect(openWorkspaceFile).toHaveBeenCalledWith('/work/a/src/x.py', 'a1')
    })
    it('绝对路径直接打开', async () => {
      const { api, openWorkspaceFile } = makeHarness()
      await api.onOpenDiffFileFromMessage('/abs/x.py')
      expect(openWorkspaceFile).toHaveBeenCalledWith('/abs/x.py', null)
    })
  })

  describe('viewGitFileDiff', () => {
    it('无工作目录时直接返回', async () => {
      const { api, fetchWithAuth } = makeHarness()
      await api.viewGitFileDiff('abc', 'x.py')
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })
    it('有 diff pane 时复用并加载（ensurePaneForView 返回 paneId）', async () => {
      const { api, effectiveGitAgentId, agentList, ensurePaneForView, fetchWithAuth, workspacePaneTree, resolveDiffContainer } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: null }
      workspacePaneTree.value = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      ensurePaneForView.mockReturnValue('pane-diff')
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { diff: '--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n', truncated: false } }),
      })
      await api.viewGitFileDiff('abc', 'x.py')
      expect(api.gitSelectedFile.value).toBe('x.py')
      expect(ensurePaneForView).toHaveBeenCalledWith('diff')
      expect(diffPane.view).toBe('diff')
      expect(diffPane.diff).toBeTruthy()
      expect(diffPane.diff.commitHash).toBe('abc')
      expect(diffPane.diff.filePath).toBe('x.py')
      expect(diffPane.diff.loading).toBe(false)
      expect(diffPane.diff.error).toBe('')
      expect(monacoMock.editor.createDiffEditor).toHaveBeenCalled()
    })
    it('未分割且原地创建时走 leaf 路径', async () => {
      const { api, effectiveGitAgentId, agentList, ensurePaneForView, fetchWithAuth, workspacePaneTree, resolveDiffContainer } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      const leaf = { type: 'leaf', id: 'pane-main', view: 'file' }
      workspacePaneTree.value = leaf
      ensurePaneForView.mockReturnValue(null)
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { diff: '--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n', truncated: false } }),
      })
      await api.viewGitFileDiff('abc', 'x.py')
      expect(leaf.view).toBe('diff')
      expect(leaf.diff).toBeTruthy()
      expect(leaf.diff.commitHash).toBe('abc')
      expect(monacoMock.editor.createDiffEditor).toHaveBeenCalled()
    })
  })

  describe('diff pane 多实例管理', () => {
    function makeSplitTree() {
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: null }
      const tree = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      return { tree, diffPane }
    }

    it('ensureDiffEditorForPane 创建并缓存 DiffEditor', () => {
      const { api, resolveDiffContainer, diffEditorViews } = makeHarness()
      const container = { isConnected: true }
      resolveDiffContainer.mockReturnValue(container)
      const entry = api.ensureDiffEditorForPane('pane-x')
      expect(entry).toBeTruthy()
      expect(entry.editor).toBeTruthy()
      expect(monacoMock.editor.createDiffEditor).toHaveBeenCalledWith(container, expect.objectContaining({ theme: 'blueDark', readOnly: true }))
      expect(diffEditorViews.get('pane-x')).toBe(entry)
      // 再次调用返回同一实例
      expect(api.ensureDiffEditorForPane('pane-x')).toBe(entry)
    })
    it('容器被替换时销毁重建', () => {
      const { api, resolveDiffContainer, diffEditorViews } = makeHarness()
      const container1 = { isConnected: true }
      const container2 = { isConnected: true }
      resolveDiffContainer.mockReturnValueOnce(container1).mockReturnValueOnce(container2)
      const entry1 = api.ensureDiffEditorForPane('pane-x')
      const entry2 = api.ensureDiffEditorForPane('pane-x')
      expect(entry1.editor._disposed).toBe(true)
      expect(entry2.editor).not.toBe(entry1.editor)
    })
    it('disposeDiffEditorForPane 释放实例与 model', () => {
      const { api, resolveDiffContainer, diffEditorViews } = makeHarness()
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      const entry = api.ensureDiffEditorForPane('pane-x')
      const model = new MockModel('a', 'py')
      entry.originalModel = model
      entry.modifiedModel = new MockModel('b', 'py')
      api.disposeDiffEditorForPane('pane-x')
      expect(model.isDisposed()).toBe(true)
      expect(entry.editor._disposed).toBe(true)
      expect(diffEditorViews.has('pane-x')).toBe(false)
    })
    it('disposeAllDiffEditors 释放所有实例并清空容器', () => {
      const { api, resolveDiffContainer, diffEditorViews, diffContainerRefs } = makeHarness()
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      api.ensureDiffEditorForPane('pane-1')
      api.ensureDiffEditorForPane('pane-2')
      diffContainerRefs.value.set('pane-1', { isConnected: true })
      diffContainerRefs.value.set('pane-2', { isConnected: true })
      api.disposeAllDiffEditors()
      expect(diffEditorViews.size).toBe(0)
      expect(diffContainerRefs.value.size).toBe(0)
    })
    it('renderDiffForPane 渲染 model（无容器时轮询后放弃）', async () => {
      const { api, resolveDiffContainer } = makeHarness()
      resolveDiffContainer.mockReturnValue(null)
      await api.renderDiffForPane('pane-x')
      expect(monacoMock.editor.createModel).not.toHaveBeenCalled()
    })
    it('renderDiffForPane 用 parseUnifiedDiff 还原两侧文本', async () => {
      const { api, resolveDiffContainer, workspacePaneTree, getLanguageExtension, getLanguageFromFilename, diffEditorViews } = makeHarness()
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: { commitHash: 'abc', filePath: 'x.py', diffText: '--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n', sideBySide: true, showFull: false } }
      workspacePaneTree.value = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      const container = { isConnected: true }
      resolveDiffContainer.mockReturnValue(container)
      await api.renderDiffForPane('pane-diff')
      expect(monacoMock.editor.createModel).toHaveBeenCalled()
      const entry = diffEditorViews.get('pane-diff')
      expect(entry.originalModel.getValue()).toBe('old')
      expect(entry.modifiedModel.getValue()).toBe('new')
      expect(entry.editor.models).toEqual({ original: entry.originalModel, modified: entry.modifiedModel })
      expect(entry.editor._updateOptions.some(o => 'renderSideBySide' in o)).toBe(true)
      expect(entry.editor._layoutCount).toBeGreaterThan(0)
    })
    it('renderDiffForPane 渲染失败时记录错误', async () => {
      const { api, resolveDiffContainer, workspacePaneTree } = makeHarness()
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: { commitHash: 'abc', filePath: 'x.py', diffText: 'x', sideBySide: true, showFull: false } }
      workspacePaneTree.value = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      monacoMock.editor.createModel.mockImplementation(() => { throw new Error('model fail') })
      await api.renderDiffForPane('pane-diff')
      expect(diffPane.diff.error).toContain('diff 渲染失败')
    })
    it('loadDiffForPane 拉取 diff 并渲染', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth, workspacePaneTree, resolveDiffContainer } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: null }
      workspacePaneTree.value = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { diff: '--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n', truncated: false } }),
      })
      await api.loadDiffForPane('pane-diff', 'abc', 'x.py')
      expect(diffPane.diff).toBeTruthy()
      expect(diffPane.diff.commitHash).toBe('abc')
      expect(diffPane.diff.loading).toBe(false)
      expect(diffPane.diff.error).toBe('')
      expect(diffPane.diff.diffText).toContain('@@')
      expect(monacoMock.editor.createDiffEditor).toHaveBeenCalled()
    })
    it('loadDiffForPane 失败时记录错误', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth, workspacePaneTree } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: null }
      workspacePaneTree.value = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      fetchWithAuth.mockRejectedValue(new Error('diff fail'))
      await api.loadDiffForPane('pane-diff', 'abc', 'x.py')
      expect(diffPane.diff.loading).toBe(false)
      expect(diffPane.diff.error).toBe('diff fail')
    })
    it('togglePaneDiffSideBySide 切换并更新编辑器', () => {
      const { api, workspacePaneTree, resolveDiffContainer, diffEditorViews } = makeHarness()
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: { commitHash: 'abc', filePath: 'x.py', sideBySide: true, showFull: false } }
      workspacePaneTree.value = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      const entry = api.ensureDiffEditorForPane('pane-diff')
      api.togglePaneDiffSideBySide('pane-diff')
      expect(diffPane.diff.sideBySide).toBe(false)
      expect(entry.editor._updateOptions.some(o => o.renderSideBySide === false)).toBe(true)
    })
    it('navigatePaneDiff 调用 goToDiff', () => {
      const { api, resolveDiffContainer, diffEditorViews } = makeHarness()
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      const entry = api.ensureDiffEditorForPane('pane-diff')
      api.navigatePaneDiff('pane-diff', 'prev')
      expect(entry.editor._goToDiff).toBe('previous')
      api.navigatePaneDiff('pane-diff', 'next')
      expect(entry.editor._goToDiff).toBe('next')
    })
    it('closePaneDiff 释放实例并回到 empty', async () => {
      const { api, workspacePaneTree, resolveDiffContainer, diffEditorViews, persistWorkspacePaneLayout, scheduleWorkspaceLayout } = makeHarness()
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: { commitHash: 'abc', filePath: 'x.py' } }
      workspacePaneTree.value = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      api.ensureDiffEditorForPane('pane-diff')
      api.closePaneDiff('pane-diff')
      expect(diffPane.view).toBe('empty')
      expect(diffPane.diff).toBe(null)
      expect(diffEditorViews.has('pane-diff')).toBe(false)
      expect(persistWorkspacePaneLayout).toHaveBeenCalled()
      await nextTick()
      expect(scheduleWorkspaceLayout).toHaveBeenCalled()
    })
    it('layoutGitDiffEditor 只 layout 已连接实例', () => {
      const { api, resolveDiffContainer, diffEditorViews } = makeHarness()
      const connected = { isConnected: true }
      const disconnected = { isConnected: false }
      resolveDiffContainer.mockImplementation((paneId) => (paneId === 'c' ? connected : disconnected))
      const entryC = api.ensureDiffEditorForPane('c')
      const entryD = api.ensureDiffEditorForPane('d')
      api.layoutGitDiffEditor()
      expect(entryC.editor._layoutCount).toBeGreaterThan(0)
      expect(entryD.editor._layoutCount).toBe(0)
    })
    it('scheduleDiffLayout 用 rAF 合并 layout', async () => {
      const { api, resolveDiffContainer, diffEditorViews } = makeHarness()
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      const entry = api.ensureDiffEditorForPane('c')
      api.scheduleDiffLayout()
      api.scheduleDiffLayout() // 合并：第二次调用不重复调度
      await new Promise((r) => setTimeout(r, 5))
      expect(entry.editor._layoutCount).toBeGreaterThan(0)
    })
  })

  describe('ensureGitDiffFullText', () => {
    it('无工作目录时返回 null', async () => {
      const { api, fetchWithAuth } = makeHarness()
      const result = await api.ensureGitDiffFullText('abc', 'x.py')
      expect(result).toBe(null)
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })
    it('拉取两侧全文并缓存', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { content: 'full text', truncated: false } }),
      })
      const result = await api.ensureGitDiffFullText('abc', 'x.py')
      expect(result).toEqual({ oldText: 'full text', newText: 'full text', truncated: false })
      // 第二次调用命中缓存，不再请求
      fetchWithAuth.mockClear()
      const result2 = await api.ensureGitDiffFullText('abc', 'x.py')
      expect(result2).toEqual(result)
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })
    it('父版本请求失败按空文件处理', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      fetchWithAuth
        .mockResolvedValueOnce({ ok: true, json: async () => ({ success: true, data: { content: 'new', truncated: false } }) })
        .mockRejectedValueOnce(new Error('NOT_FOUND'))
      const result = await api.ensureGitDiffFullText('abc', 'x.py')
      expect(result).toEqual({ oldText: '', newText: 'new', truncated: false })
    })
  })

  describe('togglePaneDiffShowFull', () => {
    it('切到全文：拉取全文并更新编辑器', async () => {
      const { api, effectiveGitAgentId, agentList, fetchWithAuth, workspacePaneTree, resolveDiffContainer, diffEditorViews } = makeHarness()
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: { commitHash: 'abc', filePath: 'x.py', diffText: '--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n', sideBySide: true, showFull: false, truncated: false } }
      workspacePaneTree.value = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      const entry = api.ensureDiffEditorForPane('pane-diff')
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { content: 'FULL', truncated: false } }),
      })
      await api.togglePaneDiffShowFull('pane-diff')
      expect(diffPane.diff.showFull).toBe(true)
      expect(diffPane.diff.loading).toBe(false)
      expect(entry.oldText).toBe('FULL')
      expect(entry.newText).toBe('FULL')
      expect(monacoMock.editor.createModel).toHaveBeenCalled()
    })
    it('切回仅上下文：清空全文缓存变量', async () => {
      const { api, workspacePaneTree, resolveDiffContainer, diffEditorViews } = makeHarness()
      const diffPane = { type: 'leaf', id: 'pane-diff', view: 'diff', diff: { commitHash: 'abc', filePath: 'x.py', diffText: '--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n', sideBySide: true, showFull: true, truncated: false } }
      workspacePaneTree.value = { type: 'split', direction: 'row', ratio: 0.5, children: [
        { type: 'leaf', id: 'pane-main', view: 'file' },
        diffPane,
      ] }
      resolveDiffContainer.mockReturnValue({ isConnected: true })
      const entry = api.ensureDiffEditorForPane('pane-diff')
      entry.oldText = 'OLD'
      entry.newText = 'NEW'
      await api.togglePaneDiffShowFull('pane-diff')
      expect(diffPane.diff.showFull).toBe(false)
      expect(entry.oldText).toBe('')
      expect(entry.newText).toBe('')
    })
  })

  describe('展示工具函数', () => {
    it('gitRefClass 区分 HEAD/tag/分支', () => {
      const { api } = makeHarness()
      expect(api.gitRefClass('HEAD -> main')).toBe('git-ref-head')
      expect(api.gitRefClass('tag: v1.0')).toBe('git-ref-tag')
      expect(api.gitRefClass('main')).toBe('git-ref-branch')
    })
    it('gitFileStatus 由增删行数推断', () => {
      const { api } = makeHarness()
      expect(api.gitFileStatus({ additions: 1, deletions: 0 })).toBe('A')
      expect(api.gitFileStatus({ additions: 0, deletions: 1 })).toBe('D')
      expect(api.gitFileStatus({ additions: 1, deletions: 1 })).toBe('M')
      expect(api.gitFileStatus({})).toBe('M')
    })
    it('formatGitRelativeTime 各档位', () => {
      const { api } = makeHarness()
      const now = Date.now()
      expect(api.formatGitRelativeTime(new Date(now - 30 * 1000).toISOString())).toBe('刚刚')
      expect(api.formatGitRelativeTime(new Date(now - 5 * 60 * 1000).toISOString())).toBe('5 分钟前')
      expect(api.formatGitRelativeTime(new Date(now - 3 * 3600 * 1000).toISOString())).toBe('3 小时前')
      expect(api.formatGitRelativeTime(new Date(now - 5 * 86400 * 1000).toISOString())).toBe('5 天前')
      expect(api.formatGitRelativeTime(new Date(now - 2 * 30 * 86400 * 1000).toISOString())).toBe('2 个月前')
      expect(api.formatGitRelativeTime(new Date(now - 2 * 365 * 86400 * 1000).toISOString())).toBe('2 年前')
      expect(api.formatGitRelativeTime('invalid')).toBe('')
    })
    it('shortGitHash 取前 7 位', () => {
      const { api } = makeHarness()
      expect(api.shortGitHash('abcdef1234567890')).toBe('abcdef1')
      expect(api.shortGitHash('')).toBe('')
      expect(api.shortGitHash(null)).toBe('')
    })
  })

  describe('提交右键菜单', () => {
    it('openGitCommitContextMenu 打开并收敛边界', () => {
      const { api } = makeHarness()
      window.innerWidth = 1000
      window.innerHeight = 800
      api.openGitCommitContextMenu(makeCommit('abc'), { clientX: 900, clientY: 750 })
      expect(api.gitCommitContextMenu.value.visible).toBe(true)
      expect(api.gitCommitContextMenu.value.x).toBe(780) // 1000-220
      expect(api.gitCommitContextMenu.value.y).toBe(680) // 800-120
      expect(api.gitCommitContextMenu.value.commit.hash).toBe('abc')
    })
    it('closeGitCommitContextMenu 关闭', () => {
      const { api } = makeHarness()
      api.gitCommitContextMenu.value = { visible: true, x: 0, y: 0, commit: makeCommit('abc') }
      api.closeGitCommitContextMenu()
      expect(api.gitCommitContextMenu.value.visible).toBe(false)
    })
    it('copyGitCommit 复制完整信息并 toast', async () => {
      const { api, copyTextToClipboard, showToast } = makeHarness()
      api.gitCommitContextMenu.value = { visible: true, x: 0, y: 0, commit: makeCommit('abc') }
      await api.copyGitCommit(makeCommit('abc'))
      expect(copyTextToClipboard).toHaveBeenCalledWith(api.formatGitCommitInfo(makeCommit('abc')))
      expect(showToast).toHaveBeenCalledWith('已复制 commit 信息')
      expect(api.gitCommitContextMenu.value.visible).toBe(false)
    })
    it('copyGitCommit 复制失败 toast 错误', async () => {
      const { api, copyTextToClipboard, showToast } = makeHarness()
      copyTextToClipboard.mockRejectedValue(new Error('clipboard fail'))
      await api.copyGitCommit(makeCommit('abc'))
      expect(showToast).toHaveBeenCalledWith('复制失败', 'error')
    })
    it('copyGitCommitId 复制 hash', async () => {
      const { api, copyTextToClipboard, showToast } = makeHarness()
      await api.copyGitCommitId(makeCommit('abc'))
      expect(copyTextToClipboard).toHaveBeenCalledWith('abc')
      expect(showToast).toHaveBeenCalledWith('已复制 commit ID')
    })
    it('formatGitCommitInfo 组装完整信息', () => {
      const { api } = makeHarness()
      const commit = makeCommit('abc123', 'fix bug', ['HEAD', 'main'])
      commit.body = 'body text'
      const info = api.formatGitCommitInfo(commit)
      expect(info).toContain('commit abc123')
      expect(info).toContain('refs: HEAD, main')
      expect(info).toContain('Author: Alice <alice@example.com>')
      expect(info).toContain('Date:   2024-01-01 12:00:00')
      expect(info).toContain('fix bug')
      expect(info).toContain('body text')
    })
    it('formatGitCommitTooltip 无 commit 时返回空串', () => {
      const { api } = makeHarness()
      expect(api.formatGitCommitTooltip(null)).toBe('')
      expect(api.formatGitCommitTooltip(makeCommit('abc'))).toContain('commit abc')
    })
    it('showGitCommitInfoModal 设置/关闭', () => {
      const { api } = makeHarness()
      api.showGitCommitInfoModal(makeCommit('abc'))
      expect(api.gitCommitInfoModal.value.hash).toBe('abc')
      // 原行为：commit 为空时直接 return，不重置弹窗
      api.showGitCommitInfoModal(null)
      expect(api.gitCommitInfoModal.value.hash).toBe('abc')
    })
  })

  describe('watch(activeWorkspaceSessionId)', () => {
    it('Git 视图且面板可见时刷新', async () => {
      const { api, activeWorkspaceSessionId, showWorkspacePanel, workspaceSidebarView, effectiveGitAgentId, agentList, fetchWithAuth } = makeHarness()
      showWorkspacePanel.value = true
      workspaceSidebarView.value = 'git'
      agentList.value = [makeAgent('a1', '/work/a')]
      effectiveGitAgentId.value = 'a1'
      fetchWithAuth.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { commits: [], has_more: false } }),
      })
      activeWorkspaceSessionId.value = 'session-2'
      await nextTick()
      await flushPromises()
      expect(fetchWithAuth).toHaveBeenCalled()
    })
    it('非 Git 视图时不刷新', async () => {
      const { api, activeWorkspaceSessionId, showWorkspacePanel, workspaceSidebarView, fetchWithAuth } = makeHarness()
      showWorkspacePanel.value = true
      workspaceSidebarView.value = 'files'
      activeWorkspaceSessionId.value = 'session-2'
      await nextTick()
      await flushPromises()
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })
    it('面板不可见时不刷新', async () => {
      const { api, activeWorkspaceSessionId, showWorkspacePanel, workspaceSidebarView, fetchWithAuth } = makeHarness()
      showWorkspacePanel.value = false
      workspaceSidebarView.value = 'git'
      activeWorkspaceSessionId.value = 'session-2'
      await nextTick()
      await flushPromises()
      expect(fetchWithAuth).not.toHaveBeenCalled()
    })
  })
})
