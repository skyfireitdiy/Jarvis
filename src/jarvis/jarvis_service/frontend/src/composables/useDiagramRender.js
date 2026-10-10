// 图表渲染 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（原 1961-2159 行），保持行为完全一致：
// - PlantUML：通过 plantuml-encoder 编码源码，使用在线服务渲染 SVG
// - Mermaid：通过 mermaid 库在浏览器端渲染（返回占位 HTML，DOM 插入后异步渲染）
// - dot/Graphviz：通过 d3-graphviz 在浏览器端渲染（返回占位 HTML，DOM 插入后异步渲染）
//
// 无 Vue 响应式依赖（纯函数 + 模块级计数器），调用方直接解构使用：
//   const { renderPlantUmlBlock, renderDotBlock, renderMermaidBlock, ... } = useDiagramRender()

import plantumlEncoder from 'plantuml-encoder'
import mermaid from 'mermaid'
import { graphviz } from 'd3-graphviz'
import { escapeHtml } from '../diffRenderer.js'

const PLANTUML_SERVER_URL = 'https://www.plantuml.com/plantuml/svg/'
const PLANTUML_BLOCK_LANGUAGE = 'plantuml'
const MERMAID_BLOCK_LANGUAGE = 'mermaid'
const DOT_BLOCK_LANGUAGES = ['dot', 'graphviz']

// Mermaid 渲染计数器，用于生成唯一 ID
let mermaidRenderCounter = 0
// Dot 渲染计数器，用于生成唯一 ID
let dotRenderCounter = 0

// 初始化 Mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
  fontFamily: 'inherit'
})

export function useDiagramRender() {
  function encodePlantUmlText(plantUmlSource) {
    return plantumlEncoder.encode(String(plantUmlSource || '').trim())
  }

  function isPlantUmlLanguage(language) {
    return String(language || '').trim().toLowerCase() === PLANTUML_BLOCK_LANGUAGE
  }

  /**
   * 检查 PlantUML 代码是否完整（包含 @startuml 和 @enduml 标记）
   * @param {string} source - PlantUML 源码
   * @returns {boolean} - 返回 true 表示完整
   */
  function isPlantUmlComplete(source) {
    const trimmedSource = String(source || '').trim()
    const lowerSource = trimmedSource.toLowerCase()
    return lowerSource.includes('@startuml') && lowerSource.includes('@enduml')
  }

  function renderPlantUmlBlock(plantUmlSource) {
    const trimmedSource = String(plantUmlSource || '').trim()
    if (!trimmedSource) {
      return '<pre><code class="language-plantuml"></code></pre>'
    }

    // 检查 PlantUML 代码是否完整，不完整时不请求远端渲染
    if (!isPlantUmlComplete(trimmedSource)) {
      return `<pre><code class="language-plantuml">${escapeHtml(trimmedSource)}</code></pre>`
    }

    try {
      const escapedSource = escapeHtml(trimmedSource)
      const encodedSource = encodePlantUmlText(trimmedSource)
      const plantUmlUrl = `${PLANTUML_SERVER_URL}${encodedSource}`

      return [
        '<div class="plantuml-block">',
        '  <div class="plantuml-notice">',
        '    当前前端使用 PlantUML 在线服务渲染，若图片加载失败可展开查看源码。',
        '  </div>',
        `  <a class="plantuml-link" href="${plantUmlUrl}" target="_blank" rel="noopener noreferrer">`,
        `    <img class="plantuml-image" src="${plantUmlUrl}" alt="PlantUML diagram" loading="lazy" />`,
        '  </a>',
        '  <details class="plantuml-source">',
        '    <summary>查看 PlantUML 源码</summary>',
        `    <pre><code class="language-plantuml">${escapedSource}</code></pre>`,
        '  </details>',
        '</div>'
      ].join('\n')
    } catch (error) {
      console.error('[PlantUML] Failed to render PlantUML block:', error)
      return `<pre><code class="language-plantuml">${escapeHtml(trimmedSource)}</code></pre>`
    }
  }

  function isDotLanguage(language) {
    return DOT_BLOCK_LANGUAGES.includes(String(language || '').trim().toLowerCase())
  }

  function isMermaidLanguage(language) {
    return String(language || '').trim().toLowerCase() === MERMAID_BLOCK_LANGUAGE
  }

  /**
   * 渲染 dot/Graphviz 代码块
   * 使用 d3-graphviz 在浏览器端渲染
   */
  function renderDotBlock(dotSource) {
    const trimmedSource = String(dotSource || '').trim()
    if (!trimmedSource) {
      return '<pre><code class="language-dot"></code></pre>'
    }

    const id = `dot-diagram-${++dotRenderCounter}`
    const escapedSource = escapeHtml(trimmedSource)

    // 返回占位 HTML，后续由 renderDotDiagrams 函数在 DOM 插入后异步渲染
    return [
      '<div class="diagram-block">',
      '  <div class="diagram-notice">',
      '    Graphviz 图形（浏览器端渲染）。',
      '  </div>',
      `  <div class="dot-container" data-dot-id="${id}" data-dot-source="${encodeURIComponent(trimmedSource)}">`,
      '    <div class="dot-loading">渲染中...</div>',
      '  </div>',
      '  <details class="diagram-source">',
      '    <summary>查看 dot 源码</summary>',
      `    <pre><code class="language-dot">${escapedSource}</code></pre>`,
      '  </details>',
      '</div>'
    ].join('\n')
  }

  /**
   * 渲染 Mermaid 代码块
   * 使用 mermaid 库在浏览器端渲染
   */
  function renderMermaidBlock(mermaidSource) {
    const trimmedSource = String(mermaidSource || '').trim()
    if (!trimmedSource) {
      return '<pre><code class="language-mermaid"></code></pre>'
    }

    const id = `mermaid-diagram-${++mermaidRenderCounter}`
    const escapedSource = escapeHtml(trimmedSource)

    // 返回占位 HTML，后续由 renderMermaidDiagrams 函数在 DOM 插入后异步渲染
    return [
      '<div class="diagram-block">',
      '  <div class="diagram-notice">',
      '    Mermaid 流程图（浏览器端渲染）。',
      '  </div>',
      `  <div class="mermaid-container" data-mermaid-id="${id}" data-mermaid-source="${encodeURIComponent(trimmedSource)}">`,
      '    <div class="mermaid-loading">渲染中...</div>',
      '  </div>',
      '  <details class="diagram-source">',
      '    <summary>查看 Mermaid 源码</summary>',
      `    <pre><code class="language-mermaid">${escapedSource}</code></pre>`,
      '  </details>',
      '</div>'
    ].join('\n')
  }

  /**
   * 异步渲染页面中所有未渲染的 Mermaid 图形
   * 在消息内容更新后调用
   */
  async function renderMermaidDiagrams(containerEl) {
    if (!containerEl) return
    const elements = containerEl.querySelectorAll('.mermaid-container[data-mermaid-source]')
    for (const el of elements) {
      const source = decodeURIComponent(el.getAttribute('data-mermaid-source') || '')
      const id = el.getAttribute('data-mermaid-id') || 'mermaid-diagram'
      if (!source) continue

      try {
        const { svg } = await mermaid.render(id, source)
        el.innerHTML = svg
        el.removeAttribute('data-mermaid-source')
      } catch (error) {
        console.error('[Mermaid] Failed to render diagram:', error)
        el.innerHTML = `<pre><code class="language-mermaid">${escapeHtml(source)}</code></pre>`
        el.removeAttribute('data-mermaid-source')
      }
    }
  }

  /**
   * 异步渲染页面中所有未渲染的 dot/Graphviz 图形
   * 在消息内容更新后调用
   */
  async function renderDotDiagrams(containerEl) {
    if (!containerEl) return
    const elements = containerEl.querySelectorAll('.dot-container[data-dot-source]')
    for (const el of elements) {
      const source = decodeURIComponent(el.getAttribute('data-dot-source') || '')
      if (!source) continue

      try {
        await new Promise((resolve, reject) => {
          graphviz(el, { useWorker: false })
            .renderDot(source)
            .on('end', resolve)
            .on('error', reject)
        })
        el.removeAttribute('data-dot-source')
      } catch (error) {
        console.error('[Dot] Failed to render diagram:', error)
        el.innerHTML = `<pre><code class="language-dot">${escapeHtml(source)}</code></pre>`
        el.removeAttribute('data-dot-source')
      }
    }
  }

  return {
    encodePlantUmlText,
    isPlantUmlLanguage,
    isPlantUmlComplete,
    renderPlantUmlBlock,
    isDotLanguage,
    isMermaidLanguage,
    renderDotBlock,
    renderMermaidBlock,
    renderMermaidDiagrams,
    renderDotDiagrams,
  }
}
