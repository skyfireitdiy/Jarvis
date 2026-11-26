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

function mountModal(props = {}) {
  return mount(SettingsModal, {
    props: {
      visible: true,
      historyStorage: {
        getTotalCount: () => 0,
        getStorageInfo: () => ({ totalSizeFormatted: '0 B' }),
      },
      fetchWithAuth: makeFetchMock(),
      showToast: vi.fn(),
      ...props,
    },
  })
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

    expect(fetchWithAuth).toHaveBeenCalledTimes(1)
    const [url, options] = fetchWithAuth.mock.calls[0]
    expect(url).toContain('/api/wallpaper/upload')
    expect(options.method).toBe('POST')
    expect(wrapper.emitted('saveWallpaperSetting')?.at(-1)).toEqual([
      '/uploads/wallpaper/wallpaper.png',
    ])
  })

  it('非图片类型直接提示错误且不发起请求', async () => {
    const fetchWithAuth = makeFetchMock()
    const showToast = vi.fn()
    const wrapper = mountModal({ fetchWithAuth, showToast })
    const file = new File(['x'], 'a.txt', { type: 'text/plain' })
    const input = wrapper.find('.wallpaper-file-input')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await new Promise((r) => setTimeout(r, 20))

    expect(fetchWithAuth).not.toHaveBeenCalled()
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

    expect(showToast).toHaveBeenCalledWith('Permission denied: file:upload', 'error')
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

    const [url, options] = fetchWithAuth.mock.calls[0]
    expect(url).toContain('/api/wallpaper')
    expect(options.method).toBe('DELETE')
    expect(wrapper.emitted('saveWallpaperSetting')?.at(-1)).toEqual([''])
  })
})
