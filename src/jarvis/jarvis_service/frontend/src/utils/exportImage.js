/**
 * 导出 DOM 内容为图片工具模块
 * 将 Markdown 渲染后的消息内容合成为带信息条的 PNG，优先复制到剪贴板，失败时降级为下载。
 */
import { toBlob } from "html-to-image";

// 图片合成参数（与前端深色主题保持一致）
const PADDING = 24; // 内容四周留白
const HEADER_H = 56; // 顶部信息条高度
const FOOTER_H = 36; // 底部水印高度
// 导出时的内容排版宽度：窄容器（宠物气泡/窄面板）按此宽度重新排版，避免图片瘦长
const EXPORT_WIDTH = 760;
// 浏览器 canvas 单边尺寸上限（Chrome/Firefox 约 32767），留出信息条与水印的空间
const MAX_CANVAS_SIDE = 32000;
const SCALE = 2; // 像素比，保证高清
const BG_COLOR = "#0b1424";
const HEADER_BG = "#0f1c30";
const BORDER_COLOR = "rgba(32, 200, 255, 0.25)";
const TEXT_PRIMARY = "#d6e4f0";
const TEXT_SECONDARY = "#8ba3b8";
const ACCENT = "#20c8ff";

/**
 * 是否为移动端/触屏设备
 * 移动端浏览器普遍不支持 navigator.clipboard.write 写图片，且用户更需要保存到相册，
 * 因此移动端在尝试复制之外，始终额外触发一次下载。
 */
function isMobileDevice() {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  if (/Android|iPhone|iPad|iPod|Windows Phone|HarmonyOS|Mobile/i.test(ua))
    return true;
  // iPadOS 13+ 桌面模式 UA 与 Mac 相同，用触点数补充判断
  return navigator.maxTouchPoints > 1 && /Macintosh/.test(ua);
}

/**
 * 按最大宽度截断文本，超出部分用省略号代替
 */
function truncateText(ctx, text, maxWidth) {
  const str = String(text || "");
  if (!str) return "";
  if (ctx.measureText(str).width <= maxWidth) return str;
  let result = str;
  while (result.length > 1 && ctx.measureText(result + "…").width > maxWidth) {
    result = result.slice(0, -1);
  }
  return result + "…";
}

/**
 * 将 DOM 元素渲染为 PNG blob
 * 返回 null 表示渲染失败
 *
 * 注意：目标元素常处于滚动容器中（如宠物气泡 max-height + overflow-y:auto），
 * 直接渲染只能得到可视区域，会丢失超出部分。因此先克隆一份并解除高度/溢出限制，
 * 挂到离屏容器中按完整内容尺寸渲染，渲染结束后清理。
 */
async function elementToBlob(el) {
  if (!el) return null;

  const clone = el.cloneNode(true);
  // 解除克隆体的高度与溢出限制，确保完整内容参与渲染
  clone.style.maxHeight = "none";
  clone.style.height = "auto";
  clone.style.overflow = "visible";
  clone.style.overflowY = "visible";
  // 宽度取原宽度与目标宽度中较大者：窄容器（宠物气泡/窄面板）导出时按宽屏排版，
  // 避免图片过于瘦长导致内容换行过多
  const sourceW = el.offsetWidth || el.getBoundingClientRect().width || 0;
  const exportW = Math.max(sourceW, EXPORT_WIDTH);
  clone.style.width = `${exportW}px`;
  clone.style.maxWidth = "none";
  clone.style.boxSizing = "border-box";

  const holder = document.createElement("div");
  holder.style.position = "fixed";
  holder.style.left = "-100000px";
  holder.style.top = "0";
  holder.style.width = `${exportW}px`;
  holder.style.background = BG_COLOR;
  holder.appendChild(clone);
  document.body.appendChild(holder);

  try {
    // 像素比按内容高度自适应：内容越长越低，避免位图超出浏览器 canvas 上限
    const fullH = clone.scrollHeight || clone.offsetHeight || 0;
    const pixelRatio =
      fullH * SCALE > MAX_CANVAS_SIDE
        ? Math.max(1, MAX_CANVAS_SIDE / fullH)
        : SCALE;
    const blob = await toBlob(clone, {
      backgroundColor: BG_COLOR,
      pixelRatio,
      // 跳过不参与导出的交互控件（复制/导出按钮本身）
      filter: (node) => {
        if (!node || !node.classList) return true;
        return (
          !node.classList.contains("lobby-pet-copy") &&
          !node.classList.contains("lobby-pet-export") &&
          !node.classList.contains("copy-message-btn") &&
          !node.classList.contains("export-message-btn")
        );
      },
    });
    return blob ? { blob, pixelRatio } : null;
  } catch (err) {
    console.error("[EXPORT-IMAGE] 元素渲染失败:", err);
    return null;
  } finally {
    document.body.removeChild(holder);
  }
}

/**
 * 把内容图与信息条合成为最终 PNG
 */
function composeImage(contentBitmap, meta, contentW, contentH, scale) {
  const headerText = String(meta.title || "Jarvis");
  const subText = String(meta.subtitle || "");
  const timeText = String(meta.time || "");

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  // 内容图为高清位图（已按像素比放大），信息条与水印尺寸同步放大以保持视觉比例一致
  const s = scale || SCALE;
  const padding = PADDING * s;
  const headerH = HEADER_H * s;
  const footerH = FOOTER_H * s;

  const width = contentW + padding * 2;
  const height = headerH + contentH + footerH + padding;

  canvas.width = width;
  canvas.height = height;

  // canvas 尺寸超出浏览器上限时会被静默置 0，此时无法绘制
  if (!canvas.width || !canvas.height) {
    console.error("[EXPORT-IMAGE] canvas 尺寸超出上限:", width, height);
    return null;
  }

  // 背景
  ctx.fillStyle = BG_COLOR;
  ctx.fillRect(0, 0, width, height);

  // 顶部信息条
  ctx.fillStyle = HEADER_BG;
  ctx.fillRect(0, 0, width, headerH);
  ctx.strokeStyle = BORDER_COLOR;
  ctx.lineWidth = 1 * s;
  ctx.beginPath();
  ctx.moveTo(0, headerH + 0.5);
  ctx.lineTo(width, headerH + 0.5);
  ctx.stroke();

  // 左侧：Jarvis 标识 + 标题
  ctx.textBaseline = "middle";
  ctx.font = `bold ${16 * s}px sans-serif`;
  ctx.fillStyle = ACCENT;
  const brandText = "◆ Jarvis";
  ctx.fillText(brandText, padding, headerH / 2);
  const brandW = ctx.measureText(brandText).width;

  ctx.font = `${15 * s}px sans-serif`;
  ctx.fillStyle = TEXT_PRIMARY;
  const titleMaxW =
    width - padding * 2 - brandW - 16 * s - (timeText ? 140 * s : 0);
  ctx.fillText(
    truncateText(ctx, headerText, Math.max(titleMaxW, 60 * s)),
    padding + brandW + 12 * s,
    headerH / 2,
  );

  // 右侧：时间
  if (timeText) {
    ctx.font = `${13 * s}px sans-serif`;
    ctx.fillStyle = TEXT_SECONDARY;
    ctx.textAlign = "right";
    ctx.fillText(timeText, width - padding, headerH / 2);
    ctx.textAlign = "left";
  }

  // 内容图
  ctx.drawImage(contentBitmap, padding, headerH, contentW, contentH);

  // 底部水印
  ctx.font = `${12 * s}px sans-serif`;
  ctx.fillStyle = TEXT_SECONDARY;
  ctx.textAlign = "center";
  const footerText = subText
    ? `${subText} · Generated by Jarvis`
    : "Generated by Jarvis";
  ctx.fillText(
    truncateText(ctx, footerText, width - padding * 2),
    width / 2,
    headerH + contentH + footerH / 2,
  );
  ctx.textAlign = "left";

  return canvas;
}

/**
 * 将 canvas 转为 PNG blob
 */
function canvasToBlob(canvas) {
  return new Promise((resolve) => {
    try {
      canvas.toBlob((blob) => resolve(blob), "image/png");
    } catch (err) {
      console.error("[EXPORT-IMAGE] canvas 转 blob 失败:", err);
      resolve(null);
    }
  });
}

/**
 * 触发浏览器下载 PNG
 */
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || `jarvis-${Date.now()}.png`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // 延迟释放，避免部分浏览器下载未开始就失效
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

/**
 * 复制 PNG blob 到剪贴板
 * 返回 true 表示成功；剪贴板不可用（非安全上下文/浏览器不支持）时返回 false
 */
async function copyBlobToClipboard(blob) {
  if (!blob) return false;
  if (typeof ClipboardItem === "undefined" || !navigator.clipboard?.write)
    return false;
  try {
    await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
    return true;
  } catch (err) {
    console.warn("[EXPORT-IMAGE] 剪贴板写入失败，将降级为下载:", err);
    return false;
  }
}

/**
 * 导出 DOM 元素为带信息条的 PNG 图片
 *
 * @param {HTMLElement} el 目标元素（Markdown 渲染后的内容容器）
 * @param {Object} meta 信息条内容
 * @param {string} meta.title 标题（如 Agent 名）
 * @param {string} meta.subtitle 底部水印附加信息（如 Agent 类型）
 * @param {string} meta.time 右上角时间文本
 * @param {string} meta.filename 下载时的文件名（不含扩展名）
 * @returns {Promise<{ok: boolean, mode?: 'clipboard'|'download', error?: string}>}
 */
export async function exportElementAsImage(el, meta = {}) {
  if (!el) {
    return { ok: false, error: "没有可导出的内容" };
  }

  // 元素尺寸为 0 时（如被隐藏）无法渲染
  const rect = el.getBoundingClientRect();
  if (!rect.width || !rect.height) {
    return { ok: false, error: "内容为空或不可见" };
  }

  const rendered = await elementToBlob(el);
  if (!rendered) {
    return { ok: false, error: "图片生成失败" };
  }
  const { blob: contentBlob, pixelRatio } = rendered;

  // 解码为位图，按最大尺寸等比缩放
  let bitmap;
  try {
    bitmap = await createImageBitmap(contentBlob);
  } catch (err) {
    console.error("[EXPORT-IMAGE] 位图解码失败:", err);
    return { ok: false, error: "图片生成失败" };
  }

  // 内容按位图原始尺寸绘制，不做缩放（保证清晰度与完整内容）
  const contentW = bitmap.width;
  let contentH = bitmap.height;

  // 内容极高时按比例整体缩小（而非截断），避免超出 canvas 单边上限导致创建失败
  const maxContentH =
    MAX_CANVAS_SIDE - (HEADER_H + FOOTER_H + PADDING) * pixelRatio;
  let contentWFinal = contentW;
  if (contentH > maxContentH) {
    const shrink = maxContentH / contentH;
    contentH = maxContentH;
    contentWFinal = Math.max(1, Math.round(contentW * shrink));
  }

  const canvas = composeImage(
    bitmap,
    meta,
    contentWFinal,
    contentH,
    pixelRatio,
  );
  if (!canvas) {
    return { ok: false, error: "图片合成失败" };
  }

  const finalBlob = await canvasToBlob(canvas);
  if (!finalBlob) {
    return { ok: false, error: "图片生成失败" };
  }

  const filename = `${meta.filename || "jarvis-export"}.png`;
  const mobile = isMobileDevice();
  const copied = await copyBlobToClipboard(finalBlob);

  // 移动端：剪贴板写图片普遍不可用，且用户更需要保存到相册，复制之外始终下载一份
  if (mobile) {
    downloadBlob(finalBlob, filename);
    return { ok: true, mode: copied ? "clipboard+download" : "download" };
  }

  if (copied) {
    return { ok: true, mode: "clipboard" };
  }

  // 剪贴板不可用（如非 HTTPS 环境）时降级为下载
  downloadBlob(finalBlob, filename);
  return { ok: true, mode: "download" };
}
