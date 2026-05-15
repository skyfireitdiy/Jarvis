/**
 * Markdown和PlantUML渲染 Composable
 * 提供Markdown解析、PlantUML渲染、语法高亮等功能
 */

import { marked } from "marked";
import hljs from "highlight.js";
import "highlight.js/styles/github-dark.css";
import plantumlEncoder from "plantuml-encoder";
import { escapeHtml, renderSideBySideDiff } from "../diffRenderer.js";

export function useMarkdown() {
  // PlantUML服务器URL
  const PLANTUML_SERVER_URL = "https://www.plantuml.com/plantuml/svg/";
  const PLANTUML_BLOCK_LANGUAGE = "plantuml";

  /**
   * 编码PlantUML文本
   * @param {string} plantUmlSource - PlantUML源码
   * @returns {string} 编码后的文本
   */
  function encodePlantUmlText(plantUmlSource) {
    return plantumlEncoder.encode(String(plantUmlSource || "").trim());
  }

  /**
   * 检查语言是否为PlantUML
   * @param {string} language - 语言标识
   * @returns {boolean} 是否为PlantUML
   */
  function isPlantUmlLanguage(language) {
    return (
      String(language || "")
        .trim()
        .toLowerCase() === PLANTUML_BLOCK_LANGUAGE
    );
  }

  /**
   * 检查PlantUML代码是否完整（包含@startuml和@enduml标记）
   * @param {string} source - PlantUML源码
   * @returns {boolean} 返回true表示完整
   */
  function isPlantUmlComplete(source) {
    const trimmedSource = String(source || "").trim();
    const lowerSource = trimmedSource.toLowerCase();
    return lowerSource.includes("@startuml") && lowerSource.includes("@enduml");
  }

  /**
   * 渲染PlantUML代码块
   * @param {string} plantUmlSource - PlantUML源码
   * @returns {string} 渲染后的HTML
   */
  function renderPlantUmlBlock(plantUmlSource) {
    const trimmedSource = String(plantUmlSource || "").trim();
    if (!trimmedSource) {
      return '<pre><code class="language-plantuml"></code></pre>';
    }

    // 检查PlantUML代码是否完整，不完整时不请求远端渲染
    if (!isPlantUmlComplete(trimmedSource)) {
      return `<pre><code class="language-plantuml">${escapeHtml(trimmedSource)}</code></pre>`;
    }

    try {
      const escapedSource = escapeHtml(trimmedSource);
      const encodedSource = encodePlantUmlText(trimmedSource);
      const plantUmlUrl = `${PLANTUML_SERVER_URL}${encodedSource}`;

      return [
        '<div class="plantuml-block">',
        '  <div class="plantuml-notice">',
        "    当前前端使用PlantUML在线服务渲染，若图片加载失败可展开查看源码。",
        "  </div>",
        `  <a class="plantuml-link" href="${plantUmlUrl}" target="_blank" rel="noopener noreferrer">`,
        `    <img class="plantuml-image" src="${plantUmlUrl}" alt="PlantUML diagram" loading="lazy" />`,
        "  </a>",
        '  <details class="plantuml-source">',
        "    <summary>查看PlantUML源码</summary>",
        `    <pre><code class="language-plantuml">${escapedSource}</code></pre>`,
        "  </details>",
        "</div>",
      ].join("\n");
    } catch (error) {
      console.error("[PlantUML] Failed to render PlantUML block:", error);
      return `<pre><code class="language-plantuml">${escapeHtml(trimmedSource)}</code></pre>`;
    }
  }

  // 配置marked渲染器
  const markedRenderer = new marked.Renderer();
  const defaultCodeRenderer = markedRenderer.code.bind(markedRenderer);

  // 重写code渲染方法以支持PlantUML
  markedRenderer.code = function (code, language, isEscaped) {
    if (isPlantUmlLanguage(language)) {
      return renderPlantUmlBlock(code);
    }
    return defaultCodeRenderer(code, language, isEscaped);
  };

  // 配置marked使用highlight.js进行语法高亮
  marked.setOptions({
    renderer: markedRenderer,
    highlight: function (code, lang) {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return hljs.highlight(code, { language: lang }).value;
        } catch (e) {
          console.error("[highlight.js] Error highlighting code:", e);
        }
      }
      return hljs.highlightAuto(code).value;
    },
  });

  /**
   * 渲染消息为HTML
   * @param {Object} payload - 消息负载
   * @returns {string} 渲染后的HTML
   */
  function renderMessageHtml(payload) {
    if (payload?.output_type === "DIFF") {
      // 专门的DIFF类型：解析side by side diff数据
      try {
        const diffData = JSON.parse(payload.text || "{}");
        if (diffData.diff_type === "side_by_side") {
          return renderSideBySideDiff(diffData);
        }
      } catch (e) {
        console.error("[DIFF] Failed to parse side by side diff:", e);
        return escapeHtml(payload.text || "");
      }
    }

    if (payload?.lang === "markdown") {
      return marked.parse(payload.text || "");
    } else if (payload?.lang === "diff") {
      // 将diff包装在markdown代码块中，以便语法高亮
      return marked.parse(`\`\`\`diff\n${payload.text || ""}\n\`\`\``);
    } else {
      return escapeHtml(payload.text || "");
    }
  }

  return {
    // 常量
    PLANTUML_SERVER_URL,
    PLANTUML_BLOCK_LANGUAGE,

    // PlantUML相关函数
    encodePlantUmlText,
    isPlantUmlLanguage,
    isPlantUmlComplete,
    renderPlantUmlBlock,

    // 渲染函数
    renderMessageHtml,

    // marked实例（如果需要外部访问）
    marked,
  };
}
