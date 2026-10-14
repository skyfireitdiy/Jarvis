// UserAgreementModal 组件单元测试（vitest + @vue/test-utils + jsdom）
// 覆盖：visible 控制渲染、协议内容展示、同意按钮 emit、无关闭按钮（不同意不能关闭）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import UserAgreementModal from './UserAgreementModal.vue'

function mountModal(props = {}) {
  return mount(UserAgreementModal, {
    props: { visible: true, ...props },
  })
}

describe('UserAgreementModal 渲染', () => {
  it('visible=false 时不渲染弹窗', () => {
    const wrapper = mountModal({ visible: false })
    expect(wrapper.find('.user-agreement-overlay').exists()).toBe(false)
  })

  it('visible=true 时渲染遮罩、标题与同意按钮', () => {
    const wrapper = mountModal()
    expect(wrapper.find('.user-agreement-overlay').exists()).toBe(true)
    expect(wrapper.find('.user-agreement-header h2').text()).toBe('用户协议')
    expect(wrapper.find('.user-agreement-agree').text()).toContain('同意并继续')
  })

  it('渲染「高权限 Agent 系统」警告', () => {
    const wrapper = mountModal()
    expect(wrapper.find('.user-agreement-warning').text()).toContain('较高权限')
    expect(wrapper.find('.user-agreement-warning').text()).toContain('Agent 系统')
  })

  it('渲染协议条款列表（6 条）', () => {
    const wrapper = mountModal()
    const items = wrapper.findAll('.user-agreement-list li')
    expect(items.length).toBeGreaterThanOrEqual(6)
  })

  it('没有关闭按钮（不同意则不能关闭弹窗）', () => {
    const wrapper = mountModal()
    expect(wrapper.find('.user-agreement-header .close-btn').exists()).toBe(false)
    expect(wrapper.find('.user-agreement-close').exists()).toBe(false)
  })
})

describe('UserAgreementModal 交互', () => {
  it('点击同意按钮 emit agree', async () => {
    const wrapper = mountModal()
    await wrapper.find('.user-agreement-agree').trigger('click')
    expect(wrapper.emitted('agree')).toHaveLength(1)
  })
})
