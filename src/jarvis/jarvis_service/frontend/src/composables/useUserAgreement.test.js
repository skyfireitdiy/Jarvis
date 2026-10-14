// useUserAgreement 单元测试
// 覆盖：初始状态、hasAccepted 读取、agree 持久化、localStorage 不可用降级
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useUserAgreement, AGREEMENT_STORAGE_KEY } from './useUserAgreement.js'

// 内存版 localStorage mock
const store = {}
const localStorageMock = {
  getItem: vi.fn((k) => (k in store ? store[k] : null)),
  setItem: vi.fn((k, v) => { store[k] = String(v) }),
  removeItem: vi.fn((k) => { delete store[k] }),
  clear: vi.fn(() => { for (const k in store) delete store[k] }),
}
vi.stubGlobal('localStorage', localStorageMock)

beforeEach(() => {
  localStorageMock.clear()
  localStorageMock.getItem.mockClear()
  localStorageMock.setItem.mockClear()
})

describe('useUserAgreement 初始状态', () => {
  it('默认不弹协议、未同意', () => {
    const { showAgreement, agreed } = useUserAgreement()
    expect(showAgreement.value).toBe(false)
    expect(agreed.value).toBe(false)
  })
})

describe('useUserAgreement hasAccepted', () => {
  it('localStorage 无标记时返回 false', () => {
    const { hasAccepted } = useUserAgreement()
    expect(hasAccepted()).toBe(false)
  })

  it('localStorage 有标记（1）时返回 true', () => {
    store[AGREEMENT_STORAGE_KEY] = '1'
    const { hasAccepted } = useUserAgreement()
    expect(hasAccepted()).toBe(true)
  })

  it('localStorage 标记非 1 时返回 false', () => {
    store[AGREEMENT_STORAGE_KEY] = '0'
    const { hasAccepted } = useUserAgreement()
    expect(hasAccepted()).toBe(false)
  })

  it('localStorage 不可用（getItem 抛错）时返回 false（视为未同意）', () => {
    localStorageMock.getItem.mockImplementation(() => { throw new Error('denied') })
    const { hasAccepted } = useUserAgreement()
    expect(hasAccepted()).toBe(false)
  })
})

describe('useUserAgreement agree', () => {
  it('agree 后 agreed=true、showAgreement=false 并写入 localStorage', () => {
    const { showAgreement, agreed, agree } = useUserAgreement()
    showAgreement.value = true
    agree()
    expect(agreed.value).toBe(true)
    expect(showAgreement.value).toBe(false)
    expect(localStorageMock.setItem).toHaveBeenCalledWith(AGREEMENT_STORAGE_KEY, '1')
    expect(store[AGREEMENT_STORAGE_KEY]).toBe('1')
  })

  it('localStorage 不可用（setItem 抛错）时静默降级，内存态仍放行', () => {
    localStorageMock.setItem.mockImplementation(() => { throw new Error('denied') })
    const { showAgreement, agreed, agree } = useUserAgreement()
    showAgreement.value = true
    expect(() => agree()).not.toThrow()
    expect(agreed.value).toBe(true)
    expect(showAgreement.value).toBe(false)
  })
})
