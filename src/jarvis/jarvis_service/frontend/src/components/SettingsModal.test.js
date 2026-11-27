// SettingsModal 外观设置（壁纸 + 界面透明度）单元测试（vitest + @vue/test-utils + jsdom）
// 覆盖：
// 1. 壁纸区块渲染：预览图、选择/移除按钮
// 2. 透明度滑块渲染与初始值
// 3. 拖动滑块 emit update:uiOpacity（实时预览）与 saveUiOpacitySetting（松手持久化）
// 4. 选择图片后调用网关上传接口，成功 emit saveWallpaperSetting(url)
// 5. 上传失败时提示错误且不 emit
// 6. 移除壁纸调用 DELETE 接口并 emit 空 URL
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsModal from './SettingsModal.vue'

function makeFetchMock({ ok = true, body = { success: true, url: '/uploads/wallpaper/wallpaper.png' } } = {}) {
  return vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    json: async () => body,
  })
}

// 打开弹窗时会自动 GET /api/wallpaper 查询网关壁纸（跨终端发现）。
// 默认 mock 让该查询返回「网关无壁纸」，避免干扰上传/移除用例的调用计数。
function makeGatewayWallpaperMock({ url = '', wallpapers = null } = {}) {
  const list = wallpapers || (url ? [{ url, name: url.split('/').pop() }] : [])
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ success: true, url: url || null, wallpapers: list }),
  })
}
function mountModal(props = {}) {
  const fetchWithAuth = props.fetchWithAuth || makeGatewayWallpaperMock()
  const wrapper = mount(SettingsModal, {
    props: {
      visible: true,
      historyStorage: {
        getTotalCount: () => 0,
        getStorageInfo: () => ({ totalSizeFormatted: '0 B' }),
      },
      showToast: vi.fn(),
      ...props,
      fetchWithAuth,
    },
  })
  return wrapper
}
// 取出指定 HTTP 方法的调用（跳过弹窗打开时的 GET 查询）
function callsOfMethod(fetchWithAuth, method) {
  return fetchWithAuth.mock.calls.filter(([, options]) => (options?.method || 'GET') === method)
}

describe('SettingsModal 外观设置 - 渲染', () => {
  it('渲染壁纸区块与透明度滑块', () => {
    const wrapper = mountModal()
    expect(wrapper.text()).toContain('工作区壁纸')
    expect(wrapper.text()).toContain('界面透明度')
    expect(wrapper.find('.wallpaper-actions').exists()).toBe(true)
    expect(wrapper.find('.opacity-slider').exists()).toBe(true)
  })

  it('未设置壁纸时预览区显示占位文案', () => {
    const wrapper = mountModal({ wallpaperUrl: '' })
    const preview = wrapper.find('.wallpaper-preview')
    expect(preview.classes()).toContain('empty')
    expect(preview.text()).toContain('未设置壁纸')
    expect(preview.find('img').exists()).toBe(false)
  })

  it('已设置壁纸时渲染预览图，并把相对路径拼成网关绝对地址', () => {
    const wrapper = mountModal({
      wallpaperUrl: '/uploads/wallpaper/wallpaper.png',
      gatewayUrl: '127.0.0.1:8000',
      getHttpProtocol: () => 'http',
    })
    const img = wrapper.find('.wallpaper-preview img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('http://127.0.0.1:8000/uploads/wallpaper/wallpaper.png')
  })

  it('透明度滑块采用传入的初始值', () => {
    const wrapper = mountModal({ uiOpacity: 45 })
    expect(wrapper.find('.opacity-slider').element.value).toBe('45')
    expect(wrapper.find('.opacity-value').text()).toBe('45%')
  })

  it('透明度低于下限时被归一化到 20', () => {
    const wrapper = mountModal({ uiOpacity: 5 })
    expect(wrapper.find('.opacity-value').text()).toBe('20%')
  })
})

describe('SettingsModal 外观设置 - 透明度交互', () => {
  it('拖动滑块实时 emit update:uiOpacity，松手 emit saveUiOpacitySetting', async () => {
    const wrapper = mountModal({ uiOpacity: 100 })
    const slider = wrapper.find('.opacity-slider')
    await slider.setValue('60')
    expect(wrapper.emitted('update:uiOpacity')?.at(-1)).toEqual([60])
    await slider.trigger('change')
    expect(wrapper.emitted('saveUiOpacitySetting')?.at(-1)).toEqual([60])
  })
})

describe('SettingsModal 外观设置 - 壁纸上传与移除', () => {
  beforeEach(() => {
    // jsdom 未实现 FileReader.readAsDataURL，这里补一个最小实现
    class FakeFileReader {
      readAsDataURL() {
        this.result = 'data:image/png;base64,iVBORw0KGgo='
        setTimeout(() => this.onload && this.onload(), 0)
      }
    }
    globalThis.FileReader = FakeFileReader
  })

  it('选择图片后调用上传接口并 emit 返回的 URL', async () => {
    const fetchWithAuth = makeFetchMock()
    const wrapper = mountModal({ fetchWithAuth })
    const file = new File([new Uint8Array([1, 2, 3])], 'a.png', { type: 'image/png' })
    const input = wrapper.find('.wallpaper-file-input')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    // 等待 FileReader 回调 + fetch 完成
    await new Promise((r) => setTimeout(r, 20))
    await wrapper.vm.$nextTick()

    const uploadCalls = callsOfMethod(fetchWithAuth, 'POST')
    expect(uploadCalls).toHaveLength(1)
    const [url, options] = uploadCalls[0]
    expect(url).toContain('/api/wallpaper/upload')
    expect(options.method).toBe('POST')
    expect(wrapper.emitted('saveWallpaperSetting')?.at(-1)).toEqual([
      '/uploads/wallpaper/wallpaper.png',
    ])
  })

  it('一次选择多个文件时逐个上传，并启用最后一张', async () => {
    let seq = 0
    const fetchWithAuth = vi.fn().mockImplementation(async (url) => {
      if (String(url).includes('/api/wallpaper/upload')) {
        seq += 1
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            url: `/uploads/wallpaper/wallpaper_${seq}.png`,
          }),
        }
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          url: '/uploads/wallpaper/wallpaper_2.png',
          wallpapers: [
            { url: '/uploads/wallpaper/wallpaper_2.png' },
            { url: '/uploads/wallpaper/wallpaper_1.png' },
          ],
        }),
      }
    })
    const wrapper = mountModal({ fetchWithAuth, wallpaperUrl: '' })
    await new Promise((r) => setTimeout(r, 20))
    const files = [
      new File([new Uint8Array([1])], 'a.png', { type: 'image/png' }),
      new File([new Uint8Array([2])], 'b.png', { type: 'image/png' }),
    ]
    const input = wrapper.find('.wallpaper-file-input')
    expect(input.attributes('multiple')).toBeDefined()
    Object.defineProperty(input.element, 'files', { value: files, configurable: true })
    await input.trigger('change')
    await new Promise((r) => setTimeout(r, 30))

    expect(callsOfMethod(fetchWithAuth, 'POST')).toHaveLength(2)
    expect(wrapper.emitted('saveWallpaperSetting')?.at(-1)).toEqual([
      '/uploads/wallpaper/wallpaper_2.png',
    ])
    // 上传后壁纸库列表刷新为 2 张
    expect(wrapper.findAll('.wallpaper-thumb')).toHaveLength(2)
  })

  it('非图片类型直接提示错误且不发起请求', async () => {
    const fetchWithAuth = makeFetchMock()
    const showToast = vi.fn()
    // 本机已有壁纸，避免弹窗打开时的自动发现流程 emit saveWallpaperSetting 干扰断言
    const wrapper = mountModal({
      fetchWithAuth,
      showToast,
      wallpaperUrl: '/uploads/wallpaper/wallpaper.png',
    })
    const file = new File(['x'], 'a.txt', { type: 'text/plain' })
    const input = wrapper.find('.wallpaper-file-input')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await new Promise((r) => setTimeout(r, 20))

    expect(callsOfMethod(fetchWithAuth, 'POST')).toHaveLength(0)
    expect(showToast).toHaveBeenCalled()
    expect(wrapper.emitted('saveWallpaperSetting')).toBeFalsy()
  })

  it('上传失败时提示错误且不 emit', async () => {
    const fetchWithAuth = makeFetchMock({
      ok: false,
      body: { success: false, error: { message: 'Permission denied: file:upload' } },
    })
    const showToast = vi.fn()
    const wrapper = mountModal({ fetchWithAuth, showToast })
    const file = new File([new Uint8Array([1])], 'a.png', { type: 'image/png' })
    const input = wrapper.find('.wallpaper-file-input')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await new Promise((r) => setTimeout(r, 20))

    // 多选上传时错误提示带文件名前缀
    expect(showToast).toHaveBeenCalledWith('「a.png」Permission denied: file:upload', 'error')
    expect(wrapper.emitted('saveWallpaperSetting')).toBeFalsy()
  })

  it('点击移除壁纸调用 DELETE 接口并 emit 空 URL', async () => {
    const fetchWithAuth = makeFetchMock({ body: { success: true, removed: true } })
    const wrapper = mountModal({
      fetchWithAuth,
      wallpaperUrl: '/uploads/wallpaper/wallpaper.png',
    })
    const removeBtn = wrapper
      .findAll('.wallpaper-actions button')
      .find((b) => b.text().includes('移除壁纸'))
    await removeBtn.trigger('click')
    await new Promise((r) => setTimeout(r, 20))

    const deleteCalls = callsOfMethod(fetchWithAuth, 'DELETE')
    expect(deleteCalls).toHaveLength(1)
    const [url, options] = deleteCalls[0]
    expect(url).toContain('/api/wallpaper')
    expect(options.method).toBe('DELETE')
    expect(wrapper.emitted('saveWallpaperSetting')?.at(-1)).toEqual([''])
  })
})

describe('SettingsModal 外观设置 - 跨终端发现网关壁纸', () => {
  it('本机未设置壁纸时，打开弹窗自动拉取网关壁纸并启用', async () => {
    const fetchWithAuth = makeGatewayWallpaperMock({ url: '/uploads/wallpaper/wallpaper.png' })
    const wrapper = mountModal({ fetchWithAuth, wallpaperUrl: '' })
    await new Promise((r) => setTimeout(r, 20))
    await wrapper.vm.$nextTick()

    const [url] = fetchWithAuth.mock.calls[0]
    expect(url).toContain('/api/wallpaper')
    expect(wrapper.emitted('saveWallpaperSetting')?.at(-1)).toEqual([
      '/uploads/wallpaper/wallpaper.png',
    ])
    const img = wrapper.find('.wallpaper-preview img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('http://127.0.0.1:8000/uploads/wallpaper/wallpaper.png')
  })

  it('本机已设置壁纸时，自动拉取不会覆盖本机设置', async () => {
    const fetchWithAuth = makeGatewayWallpaperMock({ url: '/uploads/wallpaper/other.png' })
    const wrapper = mountModal({
      fetchWithAuth,
      wallpaperUrl: '/uploads/wallpaper/mine.png',
    })
    await new Promise((r) => setTimeout(r, 20))
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('saveWallpaperSetting')).toBeFalsy()
    // 本机与网关当前壁纸不一致时给出提示
    expect(wrapper.text()).toContain('本机壁纸与网关当前壁纸不一致')
  })

  it('网关无壁纸时提示「尚未保存任何壁纸」', async () => {
    const wrapper = mountModal({ wallpaperUrl: '' })
    await new Promise((r) => setTimeout(r, 20))
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('网关尚未保存任何壁纸')
  })

  it('渲染网关壁纸库缩略图，点击缩略图切换当前壁纸', async () => {
    const fetchWithAuth = makeGatewayWallpaperMock({
      wallpapers: [
        { url: '/uploads/wallpaper/wallpaper_2.png' },
        { url: '/uploads/wallpaper/wallpaper_1.png' },
      ],
    })
    const wrapper = mountModal({
      fetchWithAuth,
      wallpaperUrl: '/uploads/wallpaper/wallpaper_2.png',
    })
    await new Promise((r) => setTimeout(r, 20))
    await wrapper.vm.$nextTick()

    const thumbs = wrapper.findAll('.wallpaper-thumb')
    expect(thumbs).toHaveLength(2)
    // 当前壁纸高亮
    expect(thumbs[0].classes()).toContain('active')

    await thumbs[1].trigger('click')
    expect(wrapper.emitted('saveWallpaperSetting')?.at(-1)).toEqual([
      '/uploads/wallpaper/wallpaper_1.png',
    ])
  })

  it('点击缩略图上的删除按钮只删除该张壁纸', async () => {
    const fetchWithAuth = vi.fn().mockImplementation(async (url, options) => {
      if ((options?.method || 'GET') === 'DELETE') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            removed: true,
            url: '/uploads/wallpaper/wallpaper_2.png',
            wallpapers: [{ url: '/uploads/wallpaper/wallpaper_2.png' }],
          }),
        }
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          url: '/uploads/wallpaper/wallpaper_2.png',
          wallpapers: [
            { url: '/uploads/wallpaper/wallpaper_2.png' },
            { url: '/uploads/wallpaper/wallpaper_1.png' },
          ],
        }),
      }
    })
    const wrapper = mountModal({
      fetchWithAuth,
      wallpaperUrl: '/uploads/wallpaper/wallpaper_1.png',
    })
    await new Promise((r) => setTimeout(r, 20))
    await wrapper.vm.$nextTick()

    const removeBtn = wrapper.findAll('.wallpaper-thumb-remove')[1]
    await removeBtn.trigger('click')
    await new Promise((r) => setTimeout(r, 30))

    const deleteCalls = callsOfMethod(fetchWithAuth, 'DELETE')
    expect(deleteCalls).toHaveLength(1)
    expect(deleteCalls[0][0]).toContain('url=%2Fuploads%2Fwallpaper%2Fwallpaper_1.png')
    // 删掉的是当前壁纸，自动切到剩余第一张
    expect(wrapper.emitted('saveWallpaperSetting')?.at(-1)).toEqual([
      '/uploads/wallpaper/wallpaper_2.png',
    ])
  })

  it('点击「使用网关壁纸」按钮启用网关壁纸', async () => {
    const fetchWithAuth = makeGatewayWallpaperMock({ url: '/uploads/wallpaper/wallpaper.png' })
    const wrapper = mountModal({ fetchWithAuth, wallpaperUrl: '' })
    await new Promise((r) => setTimeout(r, 20))
    const btn = wrapper
      .findAll('.wallpaper-actions button')
      .find((b) => b.text().includes('使用网关壁纸'))
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await new Promise((r) => setTimeout(r, 20))
    expect(callsOfMethod(fetchWithAuth, 'GET').length).toBeGreaterThanOrEqual(2)
  })

  it('调用网关接口前先回填 token（getToken）', async () => {
    const getToken = vi.fn()
    const fetchWithAuth = makeGatewayWallpaperMock({ url: '' })
    mountModal({ fetchWithAuth, getToken, wallpaperUrl: '' })
    await new Promise((r) => setTimeout(r, 20))
    expect(getToken).toHaveBeenCalled()
  })
})
