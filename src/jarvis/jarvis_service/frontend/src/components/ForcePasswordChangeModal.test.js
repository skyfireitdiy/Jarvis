// ForcePasswordChangeModal 组件单元测试（vitest + @vue/test-utils + jsdom）
// 覆盖：visible 控制渲染、必填/一致性校验、合法输入 emit submit、loading 禁用按钮
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ForcePasswordChangeModal from './ForcePasswordChangeModal.vue'

function mountModal(props = {}) {
  return mount(ForcePasswordChangeModal, {
    props: { visible: true, ...props },
  })
}

async function fillAndSubmit(wrapper, pwd, confirm) {
  const inputs = wrapper.findAll('input')
  await inputs[0].setValue(pwd)
  await inputs[1].setValue(confirm)
  await wrapper.find('.force-pwd-submit').trigger('click')
}

describe('ForcePasswordChangeModal 渲染', () => {
  it('visible=false 时不渲染弹窗', () => {
    const wrapper = mountModal({ visible: false })
    expect(wrapper.find('.force-pwd-overlay').exists()).toBe(false)
  })

  it('visible=true 时渲染遮罩、标题与提交按钮', () => {
    const wrapper = mountModal()
    expect(wrapper.find('.force-pwd-overlay').exists()).toBe(true)
    expect(wrapper.find('.force-pwd-header h2').text()).toContain('密码')
    expect(wrapper.find('.force-pwd-submit').exists()).toBe(true)
  })

  it('没有关闭按钮（强制改密不可跳过）', () => {
    const wrapper = mountModal()
    expect(wrapper.find('.force-pwd-header .close-btn').exists()).toBe(false)
  })

  it('errorMessage 属性会渲染错误提示', () => {
    const wrapper = mountModal({ errorMessage: '旧密码错误' })
    expect(wrapper.find('.force-pwd-error').text()).toContain('旧密码错误')
  })
})

describe('ForcePasswordChangeModal 校验与提交', () => {
  it('新密码为空时不 emit，并提示', async () => {
    const wrapper = mountModal()
    await fillAndSubmit(wrapper, '', '')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.force-pwd-error').text()).toContain('不能为空')
  })

  it('两次密码不一致时不 emit，并提示', async () => {
    const wrapper = mountModal()
    await fillAndSubmit(wrapper, 'abc123', 'abc124')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.force-pwd-error').text()).toContain('不一致')
  })

  it('合法输入 emit submit 且携带 new_password', async () => {
    const wrapper = mountModal()
    await fillAndSubmit(wrapper, 'abc123', 'abc123')
    const events = wrapper.emitted('submit')
    expect(events).toBeTruthy()
    expect(events[0][0]).toEqual({ new_password: 'abc123' })
  })

  it('loading=true 时提交按钮禁用', () => {
    const wrapper = mountModal({ loading: true })
    expect(wrapper.find('.force-pwd-submit').attributes('disabled')).toBeDefined()
  })
})
