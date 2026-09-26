# -*- coding: utf-8 -*-
"""OCR 文字识别工具

把图片里的文字提取成纯文本，供**不支持多模态**的模型"看"图使用，
也可用于截图取字、票据/文档识别等场景。

设计要点（多后端可插拔 + 优雅降级）：
- 项目坚持"不新增第三方依赖"，因此本工具不强制任何 OCR 依赖。
- 所有后端均在**函数内延迟导入**，缺失时自动跳过，不影响模块导入与工具加载。
- `check()` 只要探测到任一后端可用即返回 True；一个都不可用则工具不注册。
- 后端优先级（auto 模式）：tesseract → rapidocr → paddleocr → easyocr → vision。

后端说明：
- tesseract：本地引擎，需系统安装 tesseract 可执行文件（apt install tesseract-ocr），
  若装了 pytesseract 则能拿到置信度与坐标（detail=true 时更有用）。
- rapidocr：pip install rapidocr_onnxruntime，纯 onnx，无需系统依赖。
- paddleocr / easyocr：pip 安装后可用，体积较大。
- vision：调用项目已配置的多模态大模型识别图片（无需本地 OCR 依赖，但需要网络与模型配置）。
"""

import base64
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from jarvis.jarvis_utils.output import PrettyOutput

# 支持的图片扩展名白名单
_SUPPORTED_EXTS = {
    "png",
    "jpg",
    "jpeg",
    "bmp",
    "tif",
    "tiff",
    "webp",
    "gif",
    "pbm",
    "pgm",
    "ppm",
}

# 扩展名 -> MIME 类型（vision 后端构造 data URL 时需要）
_MIME_MAP = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "webp": "image/webp",
    "gif": "image/gif",
    "pbm": "image/x-portable-bitmap",
    "pgm": "image/x-portable-graymap",
    "ppm": "image/x-portable-pixmap",
}

# 图片大小上限（默认 20 MiB，与 add_images 的 max_image_size 保持一致）
_DEFAULT_MAX_SIZE = 20 * 1024 * 1024

# 下载远程图片的超时（秒）
_DOWNLOAD_TIMEOUT = 30


class OcrTool:
    """OCR 文字识别工具（多后端可插拔）

    支持的操作：单次调用识别一张图片（本地路径或 URL）。

    典型用法：
    - 识别本地截图：{"image": "/tmp/shot.png"}
    - 中英混排：{"image": "a.png", "lang": "chi_sim+eng"}
    - 要坐标信息：{"image": "a.png", "detail": true}
    - 指定后端：{"image": "a.png", "backend": "rapidocr"}

    **提示**：若模型本身支持多模态，直接看原图通常比 OCR 更准；
    本工具主要面向"模型不支持多模态"或"只需要纯文本"的场景。
    """

    name = "ocr"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用：任一 OCR 后端可用即启用。

        注意：本方法必须**快且无副作用**（不做网络请求、不抛异常），
        因为它会在工具加载阶段被调用。
        """
        try:
            # 1) tesseract 引擎（系统可执行文件；pytesseract 只是其 Python 封装）
            if shutil.which("tesseract"):
                return True

            # 2) 纯 Python 后端（用 find_spec 探测，不实际导入，快且无副作用）
            for module_name in (
                "rapidocr_onnxruntime",
                "paddleocr",
                "easyocr",
            ):
                if OcrTool._module_available(module_name):
                    return True

            # 3) vision 后端：仅做轻量判断（是否存在可用的平台配置）
            if OcrTool._has_vision_config():
                return True

            return False
        except Exception:
            # check 绝不抛异常，异常一律视为不可用
            return False

    @staticmethod
    def _module_available(module_name: str) -> bool:
        """判断某个可选模块是否可导入（用 find_spec，不实际导入）。"""
        try:
            import importlib.util

            return importlib.util.find_spec(module_name) is not None
        except Exception:
            return False

    @staticmethod
    def _has_vision_config() -> bool:
        """轻量判断是否配置了可用于视觉识别的平台（不发起任何网络请求）。"""
        try:
            from jarvis.jarvis_platform.registry import PlatformRegistry

            registry = PlatformRegistry.get_global_platform_registry()
            platform = registry.get_normal_platform()
            return platform is not None
        except Exception:
            return False

    description = """OCR 文字识别工具：把图片（本地路径或 http(s) URL）中的文字提取为纯文本。

适用场景：模型不支持多模态时"看"图、截图取字、票据/文档/表格文字提取。

每次调用识别一张图片。参数：
- image（必填）：本地图片路径（支持 ~ 与相对路径）或 http(s) 图片 URL
- backend（可选）：auto（默认，按可用性自动选择）/ tesseract / rapidocr / paddleocr / easyocr / vision
- lang（可选）：识别语言，默认 "eng"；tesseract 支持组合如 "chi_sim+eng"
- psm（可选）：tesseract 页面分割模式（3=全自动，6=单块文本，7=单行，11=稀疏文本）
- detail（可选）：true 时额外返回逐行信息（文本/置信度/坐标，取决于后端能力）
- options（可选）：透传给后端的额外参数对象

返回：识别出的文本（detail=true 时附逐行明细）。
若本机未安装任何 OCR 后端，会返回明确的安装提示。

**提示**：若模型本身支持多模态，直接看原图通常更准确；本工具面向纯文本提取场景。"""

    parameters = {
        "type": "object",
        "properties": {
            "image": {
                "type": "string",
                "description": "图片路径（本地路径或 http(s) URL）。本地路径支持 ~ 展开与相对路径",
            },
            "backend": {
                "type": "string",
                "enum": [
                    "auto",
                    "tesseract",
                    "rapidocr",
                    "paddleocr",
                    "easyocr",
                    "vision",
                ],
                "description": "OCR 后端；auto 表示按可用性自动选择（默认 auto）",
                "default": "auto",
            },
            "lang": {
                "type": "string",
                "description": '识别语言，默认 "eng"；tesseract 可传组合如 "chi_sim+eng"',
                "default": "eng",
            },
            "psm": {
                "type": "integer",
                "description": "tesseract 页面分割模式（3=全自动，6=单块，7=单行，11=稀疏文本）",
            },
            "detail": {
                "type": "boolean",
                "description": "是否返回逐行/逐块信息（文本+置信度+坐标，取决于后端能力）",
                "default": False,
            },
            "options": {
                "type": "object",
                "description": "透传给后端的额外参数（键值由具体后端决定）",
            },
        },
        "required": ["image"],
    }

    # ------------------------------------------------------------------
    # 图像准备
    # ------------------------------------------------------------------
    def _resolve_image(self, image: str) -> Tuple[Optional[str], Optional[str]]:
        """把入参解析为可用的本地图片路径。

        返回 (本地路径, 错误信息)：成功时错误信息为 None；失败时路径为 None。
        远程 URL 会下载到临时文件（调用方负责清理）。
        """
        image = str(image or "").strip()
        if not image:
            return None, "image 不能为空"

        # 远程 URL：下载到临时文件
        if image.startswith(("http://", "https://")):
            try:
                import requests
            except Exception:
                return None, "下载远程图片需要 requests 库，但当前环境不可用"

            try:
                resp = requests.get(image, timeout=_DOWNLOAD_TIMEOUT, stream=True)
                resp.raise_for_status()
            except Exception as e:
                return None, f"下载远程图片失败: {e}"

            # 推断扩展名（优先 Content-Type，退化到 URL 后缀）
            ext = self._guess_ext_from_url(image, resp.headers.get("Content-Type", ""))
            if ext not in _SUPPORTED_EXTS:
                return None, (
                    f"远程图片格式不支持: {ext or '未知'}；"
                    f"支持: {', '.join(sorted(_SUPPORTED_EXTS))}"
                )

            try:
                fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}", prefix="jarvis_ocr_")
                with os.fdopen(fd, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            except Exception as e:
                return None, f"保存远程图片失败: {e}"
            return tmp_path, None

        # 本地路径：~ 展开 + 相对转绝对
        path = os.path.abspath(os.path.expanduser(image))
        if not os.path.exists(path):
            return None, f"图片文件不存在: {path}"
        if not os.path.isfile(path):
            return None, f"不是文件: {path}"

        ext = os.path.splitext(path)[1].lower().lstrip(".")
        if ext not in _SUPPORTED_EXTS:
            return None, (
                f"图片格式不支持: {ext or '未知'}；"
                f"支持: {', '.join(sorted(_SUPPORTED_EXTS))}"
            )

        # 大小校验
        max_size = self._max_image_size()
        try:
            size = os.path.getsize(path)
        except OSError as e:
            return None, f"无法读取图片大小: {e}"
        if size > max_size:
            return None, (
                f"图片过大: {size} 字节，超过上限 {max_size} 字节"
                f"（约 {max_size // (1024 * 1024)} MiB）"
            )
        if size == 0:
            return None, f"图片为空文件: {path}"

        return path, None

    @staticmethod
    def _guess_ext_from_url(url: str, content_type: str) -> str:
        """从 Content-Type 或 URL 后缀推断图片扩展名（小写，不含点）。"""
        ct = (content_type or "").lower()
        ct_map = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/bmp": "bmp",
            "image/tiff": "tiff",
            "image/webp": "webp",
            "image/gif": "gif",
        }
        for key, ext in ct_map.items():
            if key in ct:
                return ext
        # 退化：从 URL 路径取后缀
        path_part = url.split("?", 1)[0].split("#", 1)[0]
        return os.path.splitext(path_part)[1].lower().lstrip(".")

    @staticmethod
    def _max_image_size() -> int:
        """读取项目配置的图片大小上限，读取失败时用默认值。"""
        try:
            from jarvis.jarvis_platform.content_types import CONTENT_CONFIG

            max_size = CONTENT_CONFIG.get("max_image_size", _DEFAULT_MAX_SIZE)
            if isinstance(max_size, int) and max_size > 0:
                return max_size
        except Exception:
            pass
        return _DEFAULT_MAX_SIZE

    @staticmethod
    def _encode_data_url(path: str) -> str:
        """把本地图片编码为 data URL（vision 后端用）。"""
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        mime = _MIME_MAP.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    # ------------------------------------------------------------------
    # 后端探测
    # ------------------------------------------------------------------
    @staticmethod
    def _tesseract_available() -> bool:
        """tesseract 是否可用（CLI 存在即可，pytesseract 为增强项）。"""
        return shutil.which("tesseract") is not None

    @staticmethod
    def _import_optional(module_name: str):
        """延迟导入可选模块，失败返回 None。"""
        try:
            import importlib

            return importlib.import_module(module_name)
        except Exception:
            return None

    def _pick_backend(self, requested: str) -> Optional[str]:
        """按 auto 优先级选择实际后端；显式指定时原样返回。"""
        requested = (requested or "auto").strip().lower()
        if requested and requested != "auto":
            return requested

        # auto：按可用性与轻量程度排序
        if self._tesseract_available():
            return "tesseract"
        if self._import_optional("rapidocr_onnxruntime") is not None:
            return "rapidocr"
        if self._import_optional("paddleocr") is not None:
            return "paddleocr"
        if self._import_optional("easyocr") is not None:
            return "easyocr"
        if self._has_vision_config():
            return "vision"
        return None

    # ------------------------------------------------------------------
    # 各后端实现
    # ------------------------------------------------------------------
    def _run_tesseract(
        self,
        path: str,
        lang: str,
        psm: Optional[int],
        detail: bool,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """tesseract 后端：优先 pytesseract（可拿置信度/坐标），否则调 CLI。"""
        if not self._tesseract_available():
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    "tesseract 后端不可用：未找到 tesseract 可执行文件。\n"
                    "安装方式：\n"
                    "  - Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-chi-sim\n"
                    "  - macOS: brew install tesseract tesseract-lang\n"
                    "  - Windows: 下载安装 https://github.com/UB-Mannheim/tesseract/wiki\n"
                    "可选：pip install pytesseract（可获得置信度与坐标信息）"
                ),
            }

        pytesseract = self._import_optional("pytesseract")
        if pytesseract is not None:
            try:
                from PIL import Image  # noqa: F401
            except Exception:
                pytesseract = None  # 无 PIL 则退回 CLI

        if pytesseract is not None:
            return self._run_tesseract_py(pytesseract, path, lang, psm, detail, options)
        return self._run_tesseract_cli(path, lang, psm, detail)

    def _run_tesseract_py(
        self,
        pytesseract,
        path: str,
        lang: str,
        psm: Optional[int],
        detail: bool,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """用 pytesseract 执行识别（可输出置信度与坐标）。"""
        from PIL import Image

        config_parts: List[str] = []
        if psm is not None:
            config_parts.append(f"--psm {int(psm)}")
        extra_config = str(options.get("config", "")).strip()
        if extra_config:
            config_parts.append(extra_config)
        config = " ".join(config_parts)

        data: Optional[Dict[str, Any]] = None
        try:
            with Image.open(path) as img:
                if detail:
                    data = pytesseract.image_to_data(
                        img,
                        lang=lang,
                        config=config,
                        output_type=pytesseract.Output.DICT,
                    )
                text = pytesseract.image_to_string(img, lang=lang, config=config)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"tesseract 识别失败: {e}",
            }

        lines = (
            self._tesseract_lines_from_data(data)
            if (detail and data is not None)
            else []
        )
        return self._format_success(text, lines, "tesseract", detail)

    @staticmethod
    def _tesseract_lines_from_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """把 pytesseract.image_to_data 的 DICT 输出整理为逐行信息。"""
        lines: List[Dict[str, Any]] = []
        n = len(data.get("text", []))
        for i in range(n):
            word = str(data["text"][i] or "").strip()
            if not word:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if conf < 0:
                continue
            lines.append(
                {
                    "text": word,
                    "confidence": round(conf, 2),
                    "bbox": {
                        "x": int(data["left"][i]),
                        "y": int(data["top"][i]),
                        "width": int(data["width"][i]),
                        "height": int(data["height"][i]),
                    },
                }
            )
        return lines

    def _run_tesseract_cli(
        self, path: str, lang: str, psm: Optional[int], detail: bool
    ) -> Dict[str, Any]:
        """用 tesseract CLI 执行识别（无置信度/坐标）。"""
        cmd = ["tesseract", path, "stdout", "-l", lang]
        if psm is not None:
            cmd.extend(["--psm", str(int(psm))])
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "tesseract CLI 执行超时（>120s）",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"tesseract CLI 执行失败: {e}",
            }

        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            hint = ""
            if "Failed loading language" in err or "Error opening data file" in err:
                hint = (
                    f"\n提示：语言包 '{lang}' 可能未安装。"
                    "Ubuntu/Debian 可执行：sudo apt install tesseract-ocr-chi-sim"
                )
            return {
                "success": False,
                "stdout": "",
                "stderr": f"tesseract 返回码 {proc.returncode}: {err}{hint}",
            }

        lines: List[Dict[str, Any]] = []
        if detail:
            # CLI 模式无坐标信息，如实说明
            lines = [
                {"text": ln, "confidence": None, "bbox": None}
                for ln in (proc.stdout or "").splitlines()
                if ln.strip()
            ]
        return self._format_success(proc.stdout or "", lines, "tesseract-cli", detail)

    def _run_rapidocr(
        self, path: str, detail: bool, options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """rapidocr_onnxruntime 后端。"""
        mod = self._import_optional("rapidocr_onnxruntime")
        if mod is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    "rapidocr 后端不可用：未安装 rapidocr_onnxruntime。\n"
                    "安装方式：pip install rapidocr_onnxruntime"
                ),
            }
        try:
            engine = mod.RapidOCR()
            result, _elapse = engine(path)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"rapidocr 识别失败: {e}",
            }

        lines: List[Dict[str, Any]] = []
        texts: List[str] = []
        for item in result or []:
            # RapidOCR 返回 [bbox, text, score]
            try:
                bbox, text, score = item[0], item[1], item[2]
            except Exception:
                continue
            text = str(text or "").strip()
            if not text:
                continue
            texts.append(text)
            try:
                conf = round(float(score) * 100, 2)
            except (TypeError, ValueError):
                conf = None
            lines.append({"text": text, "confidence": conf, "bbox": bbox})
        return self._format_success("\n".join(texts), lines, "rapidocr", detail)

    def _run_paddleocr(
        self, path: str, lang: str, detail: bool, options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """paddleocr 后端（延迟导入并适配其 API）。"""
        mod = self._import_optional("paddleocr")
        if mod is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    "paddleocr 后端不可用：未安装 paddleocr。\n"
                    "安装方式：pip install paddleocr paddlepaddle"
                ),
            }
        try:
            # PaddleOCR 3.x 与 2.x 构造参数不同，这里用最小公共参数
            ocr = mod.PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
            raw = ocr.ocr(path, cls=True)
        except TypeError:
            # 兼容不支持的参数（如 show_log 在 3.x 被移除）
            try:
                ocr = mod.PaddleOCR(lang=lang)
                raw = ocr.ocr(path)
            except Exception as e:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"paddleocr 识别失败: {e}",
                }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"paddleocr 识别失败: {e}",
            }

        lines: List[Dict[str, Any]] = []
        texts: List[str] = []
        # 兼容 2.x（[[ [bbox,(text,score)], ... ]]) 与 3.x（[{"rec_texts":[...]}]）结构
        for page in raw or []:
            if isinstance(page, dict):
                for t in page.get("rec_texts", []) or []:
                    t = str(t or "").strip()
                    if t:
                        texts.append(t)
                        lines.append({"text": t, "confidence": None, "bbox": None})
                continue
            for item in page or []:
                try:
                    bbox, (text, score) = item[0], item[1]
                except Exception:
                    continue
                text = str(text or "").strip()
                if not text:
                    continue
                texts.append(text)
                try:
                    conf = round(float(score) * 100, 2)
                except (TypeError, ValueError):
                    conf = None
                lines.append({"text": text, "confidence": conf, "bbox": bbox})
        return self._format_success("\n".join(texts), lines, "paddleocr", detail)

    def _run_easyocr(
        self, path: str, lang: str, detail: bool, options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """easyocr 后端（延迟导入并适配其 API）。"""
        mod = self._import_optional("easyocr")
        if mod is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    "easyocr 后端不可用：未安装 easyocr。\n"
                    "安装方式：pip install easyocr"
                ),
            }
        try:
            # easyocr 语言代码与 tesseract 不同，做常见映射
            lang_map = {
                "eng": "en",
                "chi_sim": "ch_sim",
                "chi_tra": "ch_tra",
                "jpn": "ja",
                "kor": "ko",
            }
            langs = [
                lang_map.get(x.strip(), x.strip()) for x in lang.split("+") if x.strip()
            ]
            reader = mod.Reader(langs, gpu=False)
            raw = reader.readtext(path)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"easyocr 识别失败: {e}",
            }

        lines: List[Dict[str, Any]] = []
        texts: List[str] = []
        for item in raw or []:
            try:
                bbox, text, score = item[0], item[1], item[2]
            except Exception:
                continue
            text = str(text or "").strip()
            if not text:
                continue
            texts.append(text)
            try:
                conf = round(float(score) * 100, 2)
            except (TypeError, ValueError):
                conf = None
            lines.append({"text": text, "confidence": conf, "bbox": bbox})
        return self._format_success("\n".join(texts), lines, "easyocr", detail)

    def _run_vision(
        self, path: str, detail: bool, options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """vision 后端：调用项目已配置的多模态大模型识别图中文字。"""
        try:
            from jarvis.jarvis_platform.registry import PlatformRegistry
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"vision 后端不可用：无法导入平台模块（{e}）",
            }

        try:
            registry = PlatformRegistry.get_global_platform_registry()
            platform = registry.get_normal_platform()
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"vision 后端不可用：获取平台失败（{e}）",
            }
        if platform is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    "vision 后端不可用：未配置可用的模型平台。\n"
                    "请在 llm_config 中配置模型，并确保 supports_multimodal: true"
                ),
            }

        try:
            if (
                hasattr(platform, "supports_multimodal")
                and not platform.supports_multimodal()
            ):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        "vision 后端不可用：当前模型未开启多模态。\n"
                        "请在 llm_config 中设置 supports_multimodal: true"
                    ),
                }
        except Exception:
            pass

        try:
            data_url = self._encode_data_url(path)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"图片编码失败: {e}",
            }

        prompt = str(
            options.get(
                "prompt",
                "请提取这张图片中的全部文字，按原始阅读顺序输出纯文本，"
                "不要添加任何解释、标题或 Markdown 标记。若图中没有文字，输出空字符串。",
            )
        )
        # 构造多模态消息内容（与 add_images.py 使用同一套 ContentBlock 类型）
        try:
            from jarvis.jarvis_platform.content_types import (
                ContentBlock,
                ImageURLContent,
                TextContent,
            )

            text_block: TextContent = {"type": "text", "text": prompt}
            image_block: ImageURLContent = {
                "type": "image_url",
                "image_url": data_url,
            }
            content: List[ContentBlock] = [text_block, image_block]
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"构造多模态消息失败: {e}",
            }

        try:
            resp = platform.chat_until_success(content)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"vision 后端调用模型失败: {e}",
            }

        text = resp if isinstance(resp, str) else str(resp or "")
        lines = (
            [
                {"text": ln, "confidence": None, "bbox": None}
                for ln in text.splitlines()
                if ln.strip()
            ]
            if detail
            else []
        )
        return self._format_success(text, lines, "vision", detail)

    # ------------------------------------------------------------------
    # 结果组装
    # ------------------------------------------------------------------
    @staticmethod
    def _format_success(
        text: str, lines: List[Dict[str, Any]], backend: str, detail: bool
    ) -> Dict[str, Any]:
        """组装成功返回。"""
        text = (text or "").strip()
        out_parts: List[str] = []
        if text:
            out_parts.append(text)
        else:
            out_parts.append("（未识别到文字）")

        if detail:
            out_parts.append("")
            out_parts.append(f"--- 逐行明细（后端: {backend}）---")
            if lines:
                for idx, ln in enumerate(lines, 1):
                    conf = ln.get("confidence")
                    bbox = ln.get("bbox")
                    conf_str = f"conf={conf}" if conf is not None else "conf=N/A"
                    bbox_str = f"bbox={bbox}" if bbox else "bbox=N/A"
                    out_parts.append(
                        f"{idx:>4}. {ln.get('text', '')}  [{conf_str} {bbox_str}]"
                    )
            else:
                out_parts.append("（当前后端未提供逐行/坐标信息）")

        return {
            "success": True,
            "stdout": "\n".join(out_parts),
            "stderr": "",
            "text": text,
            "backend": backend,
            "lines": lines,
        }

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行 OCR 识别。

        参数:
            args: 工具参数（image/backend/lang/psm/detail/options）
        返回:
            Dict[str, Any]: {"success": bool, "stdout": str, "stderr": str, ...}
        """
        # 兼容 v1.0 协议：registry 可能把整个参数字典作为 args 传入
        if not isinstance(args, dict):
            return {
                "success": False,
                "stdout": "",
                "stderr": "参数必须是对象",
            }

        image = args.get("image")
        backend = str(args.get("backend") or "auto").strip().lower()
        lang = str(args.get("lang") or "eng").strip() or "eng"
        psm = args.get("psm")
        detail = bool(args.get("detail", False))
        options = args.get("options")
        if not isinstance(options, dict):
            options = {}

        if not image:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必填参数 image（图片路径或 URL）",
            }

        # 准备图片（URL 会下载到临时文件）
        local_path, err = self._resolve_image(str(image))
        if local_path is None:
            return {"success": False, "stdout": "", "stderr": err or "图片准备失败"}

        is_temp = str(image).startswith(("http://", "https://"))
        try:
            # 选择后端
            chosen = self._pick_backend(backend)
            if chosen is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        "没有可用的 OCR 后端。请任选其一安装：\n"
                        "  1) 系统 tesseract: sudo apt install tesseract-ocr tesseract-ocr-chi-sim\n"
                        "  2) pip install pytesseract （配合系统 tesseract）\n"
                        "  3) pip install rapidocr_onnxruntime （纯 Python，推荐）\n"
                        "  4) pip install paddleocr paddlepaddle\n"
                        "  5) pip install easyocr\n"
                        "  6) 或配置支持多模态的模型后使用 backend=vision"
                    ),
                }

            # 显式指定但不可用时的明确报错
            if backend != "auto":
                avail = {
                    "tesseract": self._tesseract_available(),
                    "rapidocr": self._import_optional("rapidocr_onnxruntime")
                    is not None,
                    "paddleocr": self._import_optional("paddleocr") is not None,
                    "easyocr": self._import_optional("easyocr") is not None,
                    "vision": self._has_vision_config(),
                }
                if not avail.get(backend, False):
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"指定的后端 '{backend}' 当前不可用，请安装对应依赖或改用 auto。",
                    }

            # 分发到具体后端
            if chosen == "tesseract":
                result = self._run_tesseract(local_path, lang, psm, detail, options)
            elif chosen == "rapidocr":
                result = self._run_rapidocr(local_path, detail, options)
            elif chosen == "paddleocr":
                result = self._run_paddleocr(local_path, lang, detail, options)
            elif chosen == "easyocr":
                result = self._run_easyocr(local_path, lang, detail, options)
            elif chosen == "vision":
                result = self._run_vision(local_path, detail, options)
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未知后端: {chosen}",
                }

            if result.get("success"):
                PrettyOutput.auto_print(
                    f"✅ OCR 完成（后端: {result.get('backend', chosen)}）"
                )
            return result
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"OCR 执行异常: {e}",
            }
        finally:
            # 清理远程下载的临时文件
            if is_temp and local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
