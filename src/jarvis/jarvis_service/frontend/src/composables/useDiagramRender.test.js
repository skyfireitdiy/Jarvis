// useDiagramRender 单元测试
import { describe, it, expect, vi } from 'vitest'
import { useDiagramRender } from './useDiagramRender.js'

function makeHarness() {
  return useDiagramRender()
}

describe('useDiagramRender', () => {
  it('暴露预期接口', () => {
    const api = makeHarness()
    expect(typeof api.encodePlantUmlText).toBe('function')
    expect(typeof api.isPlantUmlLanguage).toBe('function')
    expect(typeof api.isPlantUmlComplete).toBe('function')
    expect(typeof api.renderPlantUmlBlock).toBe('function')
    expect(typeof api.isDotLanguage).toBe('function')
    expect(typeof api.isMermaidLanguage).toBe('function')
    expect(typeof api.renderDotBlock).toBe('function')
    expect(typeof api.renderMermaidBlock).toBe('function')
    expect(typeof api.renderMermaidDiagrams).toBe('function')
    expect(typeof api.renderDotDiagrams).toBe('function')
  })

  describe('语言识别', () => {
    it('isPlantUmlLanguage 识别 plantuml（大小写/空白不敏感）', () => {
      const { isPlantUmlLanguage } = makeHarness()
      expect(isPlantUmlLanguage('plantuml')).toBe(true)
      expect(isPlantUmlLanguage('PlantUML')).toBe(true)
      expect(isPlantUmlLanguage(' plantuml ')).toBe(true)
      expect(isPlantUmlLanguage('mermaid')).toBe(false)
      expect(isPlantUmlLanguage('')).toBe(false)
      expect(isPlantUmlLanguage(null)).toBe(false)
    })

    it('isDotLanguage 识别 dot 与 graphviz', () => {
      const { isDotLanguage } = makeHarness()
      expect(isDotLanguage('dot')).toBe(true)
      expect(isDotLanguage('graphviz')).toBe(true)
      expect(isDotLanguage('GraphViz')).toBe(true)
      expect(isDotLanguage('mermaid')).toBe(false)
      expect(isDotLanguage('')).toBe(false)
    })

    it('isMermaidLanguage 识别 mermaid', () => {
      const { isMermaidLanguage } = makeHarness()
      expect(isMermaidLanguage('mermaid')).toBe(true)
      expect(isMermaidLanguage('Mermaid')).toBe(true)
      expect(isMermaidLanguage('dot')).toBe(false)
      expect(isMermaidLanguage('')).toBe(false)
    })
  })

  describe('PlantUML 完整性判断', () => {
    it('isPlantUmlComplete 要求同时包含 @startuml 与 @enduml', () => {
      const { isPlantUmlComplete } = makeHarness()
      expect(isPlantUmlComplete('@startuml\nA -> B\n@enduml')).toBe(true)
      expect(isPlantUmlComplete('@startuml\nA -> B')).toBe(false)
      expect(isPlantUmlComplete('A -> B\n@enduml')).toBe(false)
      expect(isPlantUmlComplete('')).toBe(false)
      expect(isPlantUmlComplete(null)).toBe(false)
    })
  })

  describe('renderPlantUmlBlock', () => {
    it('空源码返回空占位', () => {
      const { renderPlantUmlBlock } = makeHarness()
      expect(renderPlantUmlBlock('')).toBe('<pre><code class="language-plantuml"></code></pre>')
      expect(renderPlantUmlBlock(null)).toBe('<pre><code class="language-plantuml"></code></pre>')
    })

    it('不完整源码不请求远端渲染，直接转义输出', () => {
      const { renderPlantUmlBlock } = makeHarness()
      const html = renderPlantUmlBlock('A -> B')
      expect(html).toContain('<pre><code class="language-plantuml">')
      expect(html).not.toContain('plantuml.com')
    })

    it('完整源码生成带在线服务 URL 的 img', () => {
      const { renderPlantUmlBlock } = makeHarness()
      const html = renderPlantUmlBlock('@startuml\nA -> B\n@enduml')
      expect(html).toContain('plantuml-block')
      expect(html).toContain('https://www.plantuml.com/plantuml/svg/')
      expect(html).toContain('class="plantuml-image"')
      expect(html).toContain('class="plantuml-link"')
    })
  })

  describe('renderDotBlock / renderMermaidBlock', () => {
    it('空源码返回空占位', () => {
      const { renderDotBlock, renderMermaidBlock } = makeHarness()
      expect(renderDotBlock('')).toBe('<pre><code class="language-dot"></code></pre>')
      expect(renderMermaidBlock('')).toBe('<pre><code class="language-mermaid"></code></pre>')
    })

    it('dot 源码生成带 data-dot-id/data-dot-source 的占位 HTML', () => {
      const { renderDotBlock } = makeHarness()
      const html = renderDotBlock('digraph G { A -> B }')
      expect(html).toContain('diagram-block')
      expect(html).toMatch(/data-dot-id="dot-diagram-\d+"/)
      expect(html).toContain('data-dot-source=')
      expect(html).toContain('dot-loading')
    })

    it('mermaid 源码生成带 data-mermaid-id/data-mermaid-source 的占位 HTML', () => {
      const { renderMermaidBlock } = makeHarness()
      const html = renderMermaidBlock('graph TD\nA-->B')
      expect(html).toContain('diagram-block')
      expect(html).toMatch(/data-mermaid-id="mermaid-diagram-\d+"/)
      expect(html).toContain('data-mermaid-source=')
      expect(html).toContain('mermaid-loading')
    })
  })

  describe('renderMermaidDiagrams / renderDotDiagrams', () => {
    it('空容器安全返回', async () => {
      const { renderMermaidDiagrams, renderDotDiagrams } = makeHarness()
      await expect(renderMermaidDiagrams(null)).resolves.toBeUndefined()
      await expect(renderDotDiagrams(null)).resolves.toBeUndefined()
    })

    it('无匹配元素时安全返回', async () => {
      const { renderMermaidDiagrams, renderDotDiagrams } = makeHarness()
      const container = document.createElement('div')
      await expect(renderMermaidDiagrams(container)).resolves.toBeUndefined()
      await expect(renderDotDiagrams(container)).resolves.toBeUndefined()
    })
  })
})
