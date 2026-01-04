# -*- coding: utf-8 -*-
"""
FastAPI Web 应用

提供配置表单的 Web 服务
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .schema_parser import SchemaParser

from jarvis.jarvis_utils.output import PrettyOutput


# 请求模型
class SaveConfigRequest(BaseModel):
    """保存配置的请求模型"""

    config: Dict[str, Any]


# 存储全局状态（在实际应用中应该使用更好的状态管理）
_schema_parser: Optional[SchemaParser] = None
_output_path: Optional[Path] = None
_existing_config: Dict[str, Any] = {}


def create_app(schema_path: Path, output_path: Path) -> FastAPI:
    """创建 FastAPI 应用

    Args:
        schema_path: JSON Schema 文件路径
        output_path: 输出配置文件路径

    Returns:
        FastAPI 应用实例
    """
    global _schema_parser, _output_path, _existing_config

    # 初始化 schema 解析器
    _schema_parser = SchemaParser(schema_path)
    _output_path = output_path

    # 加载现有配置文件（如果存在）
    _existing_config = {}
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                if output_path.suffix in (".yaml", ".yml"):
                    _existing_config = yaml.safe_load(f) or {}
                else:
                    _existing_config = json.load(f)
        except Exception:
            # 如果加载失败，使用空配置
            _existing_config = {}

    # 创建 FastAPI 应用
    app = FastAPI(
        title="Jarvis 配置工具",
        description="基于 JSON Schema 的动态配置表单",
        version="1.0.0",
    )

    # 启用 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        """返回 HTML 页面"""
        # TODO: 在任务4中实现完整的 Zen-iOS Hybrid 风格前端
        # 这里先返回一个基础框架
        return get_html_template()

    @app.get("/api/schema")
    async def get_schema() -> Dict[str, Any]:
        """获取 Schema 数据

        Returns:
            Schema 对象，包含属性、类型、约束等信息
        """
        if _schema_parser is None:
            raise HTTPException(status_code=500, detail="Schema parser not initialized")

        properties = _schema_parser.get_properties()

        # 为每个属性添加额外的元数据
        for prop_name in properties:
            schema_default = _schema_parser.get_default_value(prop_name)
            # 如果现有配置中有该属性的值，则用该值覆盖默认值
            if prop_name in _existing_config:
                schema_default = _existing_config[prop_name]

            properties[prop_name]["_meta"] = {
                "default": schema_default,
                "enum": _schema_parser.get_enum(prop_name),
                "description": _schema_parser.get_description_for_property(prop_name),
                "required": prop_name in _schema_parser.get_required(),
            }

        return {
            "title": _schema_parser.get_title(),
            "description": _schema_parser.get_description(),
            "properties": properties,
            "required": _schema_parser.get_required(),
        }

    @app.post("/api/save")
    async def save_config(request: SaveConfigRequest) -> Dict[str, Any]:
        """保存配置

        Args:
            request: 配置数据请求

        Returns:
            保存结果
        """
        if _schema_parser is None:
            raise HTTPException(status_code=500, detail="Schema parser not initialized")

        if _output_path is None:
            raise HTTPException(status_code=500, detail="Output path not set")

        # 调试：打印保存信息
        PrettyOutput.auto_print(
            f"🔍 [DEBUG] 准备保存配置到: {_output_path}", timestamp=False
        )
        PrettyOutput.auto_print(
            f"🔍 [DEBUG] 文件路径类型: {type(_output_path)}", timestamp=False
        )
        PrettyOutput.auto_print(
            f"🔍 [DEBUG] 文件路径存在: {_output_path.exists()}", timestamp=False
        )

        # 清理配置中的 null 值（递归移除）
        def clean_null_values(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {
                    k: clean_null_values(v) for k, v in obj.items() if v is not None
                }
            elif isinstance(obj, list):
                return [clean_null_values(item) for item in obj if item is not None]
            return obj

        cleaned_config = clean_null_values(request.config)
        PrettyOutput.auto_print(
            f"🔍 [DEBUG] 清理 null 值后的配置键数: {len(cleaned_config)}",
            timestamp=False,
        )

        # 验证配置
        errors = _schema_parser.validate_config(cleaned_config)
        PrettyOutput.auto_print(
            f"🔍 [DEBUG] 验证结果: {len(errors) if errors else 0} 个错误",
            timestamp=False,
        )
        if errors:
            for error in errors:
                PrettyOutput.auto_print(
                    f"🔍 [DEBUG] 验证错误: path={error.path}, message={error.message}",
                    timestamp=False,
                )
            return {
                "success": False,
                "errors": [
                    {"path": error.path, "message": error.message} for error in errors
                ],
            }

        # 保存配置文件
        try:
            # 确保输出目录存在
            _output_path.parent.mkdir(parents=True, exist_ok=True)

            # 根据文件后缀决定格式
            PrettyOutput.auto_print(
                f"🔍 [DEBUG] 开始写入文件，后缀: {_output_path.suffix}", timestamp=False
            )
            if _output_path.suffix in (".yaml", ".yml"):
                with open(_output_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        cleaned_config,
                        f,
                        allow_unicode=True,
                        default_flow_style=False,
                        sort_keys=False,
                    )
                PrettyOutput.auto_print("🔍 [DEBUG] YAML 写入完成", timestamp=False)
            else:
                with open(_output_path, "w", encoding="utf-8") as f:
                    json.dump(cleaned_config, f, indent=2, ensure_ascii=False)
                PrettyOutput.auto_print("🔍 [DEBUG] JSON 写入完成", timestamp=False)

            # 验证写入结果
            import os

            PrettyOutput.auto_print(
                f"🔍 [DEBUG] 写入后文件大小: {os.path.getsize(_output_path)} 字节",
                timestamp=False,
            )
            PrettyOutput.auto_print(
                f"🔍 [DEBUG] 写入后文件修改时间: {os.path.getmtime(_output_path)}",
                timestamp=False,
            )

            return {
                "success": True,
                "message": f"配置已保存到 {_output_path}",
                "path": str(_output_path),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")

    @app.get("/api/health")
    async def health_check() -> Dict[str, str]:
        """健康检查"""
        return {"status": "ok"}

    @app.post("/api/shutdown")
    async def shutdown() -> Dict[str, str]:
        """关闭服务器"""
        import threading
        import os
        import signal

        def delayed_shutdown():
            """延迟关闭，确保响应先发送"""
            import time

            time.sleep(0.5)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=delayed_shutdown, daemon=True).start()
        return {"status": "shutting_down"}

    return app


def get_html_template() -> str:
    """获取 HTML 模板

    Returns:
        HTML 字符串
    """
    return r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jarvis 配置工具</title>
    <script>
        function expandAll() {
            const sections = document.querySelectorAll('.form-section');
            
            // 对于每个折叠的区域，模拟点击其折叠按钮以确保状态一致
            for (let i = 0; i < sections.length; i++) {
                const toggleBtn = sections[i].querySelector('.collapse-toggle');
                if (toggleBtn && sections[i].classList.contains('collapsed')) {
                    // 模拟点击操作，确保调用toggleCollapse函数
                    toggleBtn.click();
                }
            }
        }
        
        function collapseAll() {
            const sections = document.querySelectorAll('.form-section');
            
            // 对于每个展开的区域，模拟点击其折叠按钮以确保状态一致
            for (let i = 0; i < sections.length; i++) {
                const toggleBtn = sections[i].querySelector('.collapse-toggle');
                if (toggleBtn && !sections[i].classList.contains('collapsed')) {
                    // 模拟点击操作，确保调用toggleCollapse函数
                    toggleBtn.click();
                }
            }
        }
    </script>
    <style>
        :root {
            --bg-primary: #F2F2F7;
            --bg-glass: rgba(255, 255, 255, 0.5);
            --bg-input: rgba(243, 244, 246, 0.5);
            --bg-input-focus: rgba(243, 244, 246, 0.7);
            --text-primary: #1C1C1E;
            --text-secondary: #6B7280;
            --text-label: #3C3C43;
            --border-inner: rgba(255, 255, 255, 0.6);
            --border-outer: rgba(0, 0, 0, 0.08);
            --button-primary: #1C1C1E;
            --button-primary-hover: #2C2C2E;
            --error: #DC2626;
            --error-bg: #FEE2E2;
            --shadow-float: 0 24px 48px -12px rgba(0, 0, 0, 0.08);
            --shadow-inset: inset 0 2px 4px rgba(0, 0, 0, 0.06);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.4;
            padding: 12px;
            min-height: 100vh;
        }

        .main-container {
            max-width: 1400px;
            margin: 0 auto;
        }

        #form-fields {
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
        }

        /* 宽屏多列布局 */
        @media (min-width: 1024px) {
            #form-fields {
                grid-template-columns: repeat(2, 1fr);
            }

            /* 复杂字段（包含嵌套对象或数组）占满整行 */
            .form-section:has(.nested-object),
            .form-section:has(.dict-container),
            .form-section:has(.array-item) {
                grid-column: 1 / -1;
            }
        }

        /* 超宽屏三列布局 */
        @media (min-width: 1600px) {
            #form-fields {
                grid-template-columns: repeat(3, 1fr);
            }
        }

        .glass-card {
            background: var(--bg-glass);
            backdrop-filter: blur(50px);
            -webkit-backdrop-filter: blur(50px);
            border-radius: 20px;
            padding: 20px;
            border: 1px solid var(--border-inner);
            box-shadow: 0 0 0 1px var(--border-outer), var(--shadow-float);
            margin-bottom: 12px;
        }

        h1 {
            font-weight: 800;
            letter-spacing: -0.02em;
            font-size: 22px;
            margin-bottom: 4px;
            color: var(--text-primary);
        }

        .description {
            color: var(--text-secondary);
            font-size: 13px;
            line-height: 1.4;
            margin-bottom: 16px;
        }

        .loading, .error, .success {
            text-align: center;
            padding: 24px 16px;
            border-radius: 12px;
            background: var(--bg-glass);
            backdrop-filter: blur(50px);
        }

        .loading {
            color: var(--text-secondary);
            font-size: 16px;
        }

        .error {
            background: var(--error-bg);
            color: var(--error);
            border: 1px solid rgba(220, 38, 38, 0.2);
        }

        .success {
            background: rgba(16, 185, 129, 0.1);
            color: #059669;
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        #form-container {
            display: none;
        }

        .form-section {
            background: var(--bg-glass);
            backdrop-filter: blur(40px);
            border-radius: 12px;
            padding: 0;
            border: 1px solid var(--border-inner);
            box-shadow: 0 0 0 1px var(--border-outer), var(--shadow-float);
            /* Grid 布局时不再需要 margin-bottom，由 gap 控制 */
        }
        
        .form-section-header {
            padding: 8px;
            border-bottom: 1px solid var(--border-inner);
            cursor: pointer;
            display: flex;
            align-items: center;
        }
        
        .collapse-toggle {
            background: none;
            border: none;
            font-size: 14px;
            cursor: pointer;
            color: var(--text-secondary);
            padding: 1px 4px;
            border-radius: 3px;
            margin-left: auto;
        }
        
        .form-section-header:hover {
            background: var(--bg-input-focus);
            border-radius: 12px 12px 0 0;
        }
        
        .form-section-content {
            padding: 8px;
            display: block;
        }
        
        .form-section.collapsed .form-section-content {
            display: none;
        }
        
        /* 添加CSS优化以提高性能 */
        .form-section {
            will-change: transform;
        }
        
        .form-section-header {
            cursor: pointer;
            user-select: none; /* 防止误选文本 */
        }
        
        .collapse-toggle {
            background: none;
            border: none;
            font-size: 14px;
            cursor: pointer;
            color: var(--text-secondary);
            padding: 1px 4px;
            border-radius: 3px;
        }
        
        .collapse-toggle:hover {
            background: var(--bg-input);
            color: var(--text-primary);
        }

        .form-group {
            margin-bottom: 6px;
        }

        .form-group:last-child {
            margin-bottom: 0;
        }

        label {
            display: block;
            font-weight: 700;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-label);
            margin-bottom: 4px;
        }

        .required-mark {
            color: var(--error);
            margin-left: 2px;
        }

        .field-description {
            display: inline-block;
            color: var(--text-secondary);
            font-size: 11px;
            margin-left: 6px;
            line-height: 1.3;
            vertical-align: middle;
        }

        .field-description.deprecated {
            color: #9CA3AF;
            font-style: italic;
            background: linear-gradient(135deg, rgba(156, 163, 175, 0.1), rgba(156, 163, 175, 0.05));
            padding: 4px 8px;
            border-radius: 4px;
            border-left: 3px solid #F59E0B;
        }

        .field-description.deprecated::before {
            content: "⚠️ ";
        }

        input[type="text"],
        input[type="number"],
        input[type="email"],
        input[type="url"],
        input[type="tel"],
        textarea,
        select {
            width: 100%;
            padding: 4px 8px;
            border: 1px solid var(--border-inner);
            border-radius: 6px;
            background: var(--bg-input);
            font-size: 13px;
            color: var(--text-primary);
            outline: none;
            transition: all 0.2s ease;
            box-shadow: var(--shadow-inset);
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif;
        }

        input:focus,
        textarea:focus,
        select:focus {
            background: var(--bg-input-focus);
            box-shadow: var(--shadow-inset), 0 0 0 3px rgba(0, 122, 255, 0.1);
        }

        input::placeholder,
        textarea::placeholder {
            color: var(--text-secondary);
        }

        textarea {
            min-height: 60px;
            resize: vertical;
        }

        .checkbox-group,
        .radio-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .checkbox-item,
        .radio-item {
            display: flex;
            align-items: center;
            padding: 8px 12px;
            background: var(--bg-input);
            border: 1px solid var(--border-inner);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: var(--shadow-inset);
        }

        .checkbox-item:hover,
        .radio-item:hover {
            background: var(--bg-input-focus);
        }

        .checkbox-item:active,
        .radio-item:active {
            transform: scale(0.98);
        }

        .checkbox-item input,
        .radio-item input {
            width: 16px;
            height: 16px;
            margin-right: 8px;
            cursor: pointer;
            accent-color: var(--button-primary);
        }

        .switch-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 6px 12px;
            background: var(--bg-input);
            border: 1px solid var(--border-inner);
            border-radius: 8px;
            box-shadow: var(--shadow-inset);
        }

        .switch {
            position: relative;
            width: 40px;
            height: 24px;
            flex-shrink: 0;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .switch-slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #D1D1D6;
            transition: 0.3s;
            border-radius: 12px;
        }

        .switch-slider:before {
            position: absolute;
            content: "";
            height: 20px;
            width: 20px;
            left: 2px;
            bottom: 2px;
            background-color: white;
            transition: 0.3s;
            border-radius: 50%;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }

        .switch input:checked + .switch-slider {
            background-color: #34C759;
        }

        .switch input:checked + .switch-slider:before {
            transform: translateX(16px);
        }

        .switch:active .switch-slider:before {
            width: 24px;
        }

        .nested-object {
            background: rgba(243, 244, 246, 0.3);
            border-radius: 10px;
            padding: 12px;
            margin-top: 6px;
            border: 1px solid var(--border-inner);
        }

        .dict-container {
            background: var(--bg-input);
            border: 1px solid var(--border-inner);
            border-radius: 10px;
            padding: 10px;
        }

        .dict-item {
            background: var(--bg-glass);
            border: 1px solid var(--border-inner);
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 8px;
            box-shadow: var(--shadow-inset);
        }

        .dict-item:last-child {
            margin-bottom: 0;
        }

        .dict-key-input {
            width: 100%;
            padding: 6px 10px;
            border: 1px solid var(--border-inner);
            border-radius: 6px;
            background: var(--bg-primary);
            font-size: 13px;
            color: var(--text-primary);
            outline: none;
            margin-bottom: 8px;
            box-shadow: var(--shadow-inset);
        }

        .dict-key-input:focus {
            background: rgba(243, 244, 246, 0.5);
            box-shadow: var(--shadow-inset), 0 0 0 3px rgba(0, 122, 255, 0.1);
        }

        .dict-controls {
            display: flex;
            gap: 8px;
            margin-top: 8px;
        }

        .dict-item-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }

        .dict-item-remove {
            margin-left: auto;
            flex-shrink: 0;
        }

        .array-item {
            background: var(--bg-input);
            border: 1px solid var(--border-inner);
            border-radius: 10px;
            padding: 10px;
            margin-bottom: 8px;
            box-shadow: var(--shadow-inset);
        }

        .array-item:last-child {
            margin-bottom: 0;
        }

        .array-controls {
            display: flex;
            gap: 8px;
            margin-top: 8px;
        }

        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif;
        }

        .btn:active {
            transform: scale(0.98);
        }

        .btn-primary {
            background: var(--button-primary);
            color: white;
        }

        .btn-primary:hover {
            background: var(--button-primary-hover);
        }

        .btn-secondary {
            background: white;
            color: var(--text-primary);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        .btn-secondary:hover {
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }

        .btn-danger {
            background: rgba(220, 38, 38, 0.1);
            color: var(--error);
            border: 1px solid rgba(220, 38, 38, 0.2);
        }

        .btn-danger:hover {
            background: rgba(220, 38, 38, 0.15);
        }

        .btn-sm {
            padding: 5px 12px;
            font-size: 12px;
            border-radius: 6px;
        }

        .btn-icon {
            width: 26px;
            height: 26px;
            padding: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 6px;
        }

        .form-actions {
            margin-top: 16px;
            display: flex;
            gap: 10px;
        }

        .field-error {
            color: var(--error);
            font-size: 11px;
            margin-top: 4px;
            display: none;
        }

        .has-error input,
        .has-error select,
        .has-error textarea {
            border-color: var(--error);
        }

        .has-error .field-error {
            display: block;
        }

        @media (max-width: 768px) {
            body {
                padding: 16px;
            }

            .glass-card {
                border-radius: 32px;
                padding: 32px 24px;
            }

            h1 {
                font-size: 28px;
            }

            .form-section {
                border-radius: 24px;
                padding: 24px 20px;
            }

            .form-actions {
                flex-direction: column;
            }

            .btn {
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="glass-card">
            <h1 id="title">Loading...</h1>
            <p id="description" class="description"></p>
            
            <div id="loading" class="loading">
                <div style="margin-bottom: 16px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6B7280" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="3"></circle>
                        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                    </svg>
                </div>
                加载配置表单中...
            </div>
            
            <div id="error" class="error" style="display: none;"></div>
            <div id="success" class="success" style="display: none;"></div>
            
            <div id="form-container">
                <form id="config-form" novalidate>
                    <div style="display: flex; gap: 10px; margin-bottom: 16px;">
                        <button type="button" class="btn btn-secondary" onclick="expandAll()">展开所有</button>
                        <button type="button" class="btn btn-secondary" onclick="collapseAll()">折叠所有</button>
                    </div>
                    <div id="form-fields"></div>
                    <div class="form-actions">
                        <button type="submit" class="btn btn-primary">保存配置</button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <script>
        let schemaData = null;
        let formData = {};
        let arrayCounters = {};
        let dictCounters = {};

        async function loadSchema() {
            try {
                const response = await fetch('/api/schema');
                if (!response.ok) throw new Error('加载 Schema 失败');
                schemaData = await response.json();
                renderForm();
            } catch (error) {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('error').style.display = 'block';
                document.getElementById('error').textContent = error.message;
            }
        }

        function renderForm() {
            document.getElementById('loading').style.display = 'none';
            document.getElementById('form-container').style.display = 'block';

            document.getElementById('title').textContent = schemaData.title || '配置';
            document.getElementById('description').textContent = schemaData.description || '';

            const fieldsContainer = document.getElementById('form-fields');
            fieldsContainer.innerHTML = '';
            
            // 使用 DocumentFragment 来批量添加元素，减少重排次数
            const fragment = document.createDocumentFragment();

            for (const [name, prop] of Object.entries(schemaData.properties)) {
                const meta = prop._meta || {};
                const isRequired = schemaData.required.includes(name);

                const section = document.createElement('div');
                section.className = 'form-section';
                section.innerHTML = createFieldHTML(name, prop, meta, isRequired, []);
                fragment.appendChild(section);
            }
            
            fieldsContainer.appendChild(fragment);

            initializeFormValues();
        }

        function createFieldHTML(name, prop, meta, isRequired, path) {
            const type = prop.type;
            const fullPath = [...path, name];
            const fullPathStr = fullPath.join('.');
            const labelText = name + (isRequired ? '<span class="required-mark">*</span>' : '');
            
            // 创建可折叠的表单区域，默认折叠
            let html = '<div class="form-section collapsed">';
            html += '<div class="form-section-header">';
            html += '<span>' + labelText + '</span>';
            
            // 如果有描述，将其添加到标签后面
            if (meta.description) {
                const isDeprecated = meta.description.includes('[已废弃');
                const descClass = isDeprecated ? 'field-description deprecated' : 'field-description';
                html += '<span class="' + descClass + '">' + escapeHtml(meta.description) + '</span>';
            }
            
            html += '<button type="button" class="collapse-toggle">▶</button>';
            html += '</div>';
            html += '<div class="form-section-content">';
            html += '<div class="form-group" data-path="' + fullPathStr + '">';

            if (prop.enum) {
                html += createSelectHTML(fullPathStr, prop.enum, meta.default);
            } else if (type === 'boolean') {
                html += createSwitchHTML(fullPathStr, meta.default);
            } else if (type === 'string' && prop.format === 'textarea') {
                html += createTextareaHTML(fullPathStr, prop, meta.default);
            } else if (type === 'number' || type === 'integer') {
                html += createNumberInputHTML(fullPathStr, prop, meta.default);
            } else if (type === 'array') {
                html += createArrayHTML(fullPathStr, prop, meta.default, fullPath);
            } else if (type === 'object') {
                // 判断是固定属性对象还是字典类型
                if (prop.additionalProperties && !prop.properties) {
                    html += createDictHTML(fullPathStr, prop, meta.default, fullPath);
                } else {
                    html += createObjectHTML(fullPathStr, prop, meta.default, fullPath);
                }
            } else {
                html += createTextInputHTML(fullPathStr, prop, meta.default);
            }

            html += '<div class="field-error" id="error-' + fullPathStr + '"></div>';
            html += '</div>';
            html += '</div>';
            html += '</div>';

            return html;
        }

        function createTextInputHTML(path, prop, defaultValue) {
            const placeholder = prop.examples ? prop.examples[0] : '';
            const value = defaultValue !== undefined ? defaultValue : '';
            return '<input type="text" name="' + path + '" placeholder="' + escapeHtml(placeholder) + '" value="' + escapeHtml(String(value)) + '">';
        }

        function createNumberInputHTML(path, prop, defaultValue) {
            const min = prop.minimum !== undefined ? prop.minimum : '';
            const max = prop.maximum !== undefined ? prop.maximum : '';
            const value = defaultValue !== undefined ? defaultValue : '';
            return '<input type="number" name="' + path + '" min="' + min + '" max="' + max + '" value="' + value + '">';
        }

        function createTextareaHTML(path, prop, defaultValue) {
            const minLength = prop.minLength !== undefined ? prop.minLength : '';
            const maxLength = prop.maxLength !== undefined ? prop.maxLength : '';
            const value = defaultValue !== undefined ? defaultValue : '';
            return '<textarea name="' + path + '" minlength="' + minLength + '" maxlength="' + maxLength + '" placeholder="输入内容...">' + escapeHtml(String(value)) + '</textarea>';
        }

        function createSelectHTML(path, enumValues, defaultValue) {
            let html = '<select name="' + path + '">';
            if (defaultValue === undefined) {
                html += '<option value="">请选择...</option>';
            }
            enumValues.forEach(function(value) {
                const selected = value === defaultValue ? ' selected' : '';
                html += '<option value="' + escapeHtml(String(value)) + '"' + selected + '>' + escapeHtml(String(value)) + '</option>';
            });
            html += '</select>';
            return html;
        }

        function createSwitchHTML(path, defaultValue) {
            const checked = defaultValue === true ? 'checked' : '';
            return '<div class="switch-container">\n                <span>' + (defaultValue === true ? '已启用' : '已禁用') + '</span>\n                <label class="switch">\n                    <input type="checkbox" name="' + path + '" value="true" ' + checked + '>\n                    <span class="switch-slider"></span>\n                </label>\n            </div>';
        }

        function createArrayHTML(path, prop, defaultValue, parentPath) {
            // path 已经是完整路径字符串
            // parentPath 不再使用，保留参数以保持兼容性
            const fullPathStr = path;
            
            if (!arrayCounters[fullPathStr]) {
                arrayCounters[fullPathStr] = 0;
            }

            // 创建数组容器，不具有独立折叠功能
            let html = '<div class="array-container" data-path="' + fullPathStr + '">';
            html += '<div id="array-items-' + fullPathStr + '"></div>';
            html += '<div class="array-controls">';
            html += '<button type="button" class="btn btn-secondary btn-sm" onclick="addArrayItem(\'' + fullPathStr + '\')">+ 添加项</button>';
            html += '</div></div>';
            html += '</div>';
            html += '</div>';

            setTimeout(function() {
                const itemsContainer = document.getElementById('array-items-' + fullPathStr);
                if (itemsContainer) {
                    itemsContainer.dataset.schema = JSON.stringify(prop.items || {});
                }
            }, 0);

            return html;
        }

        function addArrayItem(path) {
            const container = document.getElementById('array-items-' + path);
            if (!container) return;

            const schema = JSON.parse(container.dataset.schema || '{}');
            const index = arrayCounters[path]++;
            const itemPath = path + '[' + index + ']';

            const itemDiv = document.createElement('div');
            itemDiv.className = 'array-item';
            itemDiv.dataset.index = index;

            let fieldHTML = '';
            if (schema.type === 'object') {
                for (const propName in schema.properties || {}) {
                    const propSchema = schema.properties[propName];
                    const propMeta = propSchema._meta || {};
                    const propRequired = (schema.required || []).includes(propName);
                    fieldHTML += createFieldHTML(propName, propSchema, propMeta, propRequired, [itemPath]);
                }
            } else {
                const meta = schema._meta || {};
                fieldHTML += createFieldHTML('value', schema, meta, false, [itemPath]);
            }

            itemDiv.innerHTML = fieldHTML;
            itemDiv.innerHTML += '<button type="button" class="btn btn-danger btn-sm btn-icon" onclick="removeArrayItem(\'' + path + '\', ' + index + ')" style="margin-top: 16px;">×</button>';

            container.appendChild(itemDiv);
        }

        function removeArrayItem(path, index) {
            const container = document.getElementById('array-items-' + path);
            if (!container) return;

            const item = container.querySelector('[data-index="' + index + '"]');
            if (item) {
                item.remove();
            }
        }

        function createObjectHTML(path, prop, defaultValue, parentPath) {
            // path 已经是完整路径字符串
            // parentPath 是包含完整路径的数组，用于传递给子字段
            const fullPathStr = path;
            
            // 创建对象容器，不具有独立折叠功能
            let html = '<div class="nested-object" data-path="' + fullPathStr + '">';
            
            for (const propName in prop.properties || {}) {
                const propSchema = prop.properties[propName];
                const propMeta = propSchema._meta || {};
                const propRequired = (prop.required || []).includes(propName);
                html += createFieldHTML(propName, propSchema, propMeta, propRequired, parentPath);
            }
            
            html += '</div>';
            html += '</div>';
            html += '</div>';
            return html;
        }

        function createDictHTML(path, prop, defaultValue, parentPath) {
            // path 已经是完整路径字符串（如 "llms[glm].llm_config"）
            // parentPath 不再使用，保留参数以保持兼容性
            const fullPathStr = path;
            
            if (!dictCounters[fullPathStr]) {
                dictCounters[fullPathStr] = Object.keys(defaultValue || {}).length;
            }
            
            // 创建字典容器，不具有独立折叠功能
            let html = '<div class="dict-container" data-path="' + fullPathStr + '">';
            html += '<div id="dict-items-' + fullPathStr + '"></div>';
            html += '<div class="dict-controls">';
            html += '<button type="button" class="btn btn-secondary btn-sm" onclick="addDictItem(\'' + fullPathStr + '\')">+ 添加条目</button>';
            html += '</div></div>';
            html += '</div>';
            html += '</div>';
            
            setTimeout(function() {
                const itemsContainer = document.getElementById('dict-items-' + fullPathStr);
                if (itemsContainer) {
                    itemsContainer.dataset.schema = JSON.stringify(prop.additionalProperties || {});
                    itemsContainer.dataset.defaultValue = JSON.stringify(defaultValue || {});
                    // 初始化已有条目
                    for (const key in defaultValue || {}) {
                        addDictItem(fullPathStr, key, defaultValue[key]);
                    }
                }
            }, 0);
            
            return html;
        }

        function addDictItem(path, existingKey, existingValue) {
            const container = document.getElementById('dict-items-' + path);
            if (!container) return;

            const schema = JSON.parse(container.dataset.schema || '{}');
            const itemId = 'dict-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

            const itemDiv = document.createElement('div');
            itemDiv.className = 'dict-item';
            itemDiv.dataset.id = itemId;

            const key = existingKey || '';
            let fieldHTML = '';

            if (existingKey) {
                // 编辑已有条目，创建键名显示和值字段
                fieldHTML = '<div class="dict-item-header">';
                fieldHTML += '<label>键名: ' + escapeHtml(String(existingKey)) + '</label>';
                fieldHTML += '<button type="button" class="btn btn-danger btn-sm btn-icon dict-item-remove" onclick="removeDictItem(\'' + path + '\', \'' + itemId + '\')">×</button>';
                fieldHTML += '</div>';

                // 根据值类型创建不同的字段
                const valuePath = [path + '[' + existingKey + ']'];
                if (schema.type === 'object' && schema.properties) {
                    // 对象类型：遍历所有属性
                    for (const propName in schema.properties || {}) {
                        const propSchema = schema.properties[propName];
                        const propDefaultValue = (existingValue || {})[propName];
                        const propMeta = {
                            default: propDefaultValue !== undefined ? propDefaultValue : propSchema.default,
                            description: propSchema.description,
                            enum: propSchema.enum
                        };
                        const propRequired = (schema.required || []).includes(propName);
                        fieldHTML += createFieldHTML(propName, propSchema, propMeta, propRequired, valuePath);
                    }
                } else {
                    // 非对象类型：直接使用路径作为字段名，不添加额外后缀
                    const fieldPath = path + '[' + existingKey + ']';
                    const defaultVal = existingValue !== undefined ? existingValue : (schema.default || '');
                    if (schema.type === 'boolean') {
                        fieldHTML += createSwitchHTML(fieldPath, defaultVal);
                    } else if (schema.type === 'number' || schema.type === 'integer') {
                        fieldHTML += createNumberInputHTML(fieldPath, schema, defaultVal);
                    } else {
                        fieldHTML += createTextInputHTML(fieldPath, schema, defaultVal);
                    }
                }
            } else {
                // 添加新条目，创建键名输入框和值字段
                // 使用特殊的 name 属性格式：path[__key__] 用于标识这是键名输入框
                // 添加 oninput 事件，当用户输入键名时立即更新相关字段的 name 属性
                fieldHTML = '<input type="text" class="dict-key-input" name="' + path + '[__key__]' + '" placeholder="输入键名..." value="" oninput="updateDictKey(\'' + path + '\', \'' + itemId + '\', this.value)">';

                // 根据值类型创建不同的字段
                // 使用临时键名 __temp__，在收集数据时会根据实际的键名输入框的值来替换
                if (schema.type === 'object' && schema.properties) {
                    // 对象类型：遍历所有属性
                    const valuePath = [path + '[__temp__]'];
                    for (const propName in schema.properties || {}) {
                        const propSchema = schema.properties[propName];
                        const propMeta = {
                            default: propSchema.default,
                            description: propSchema.description,
                            enum: propSchema.enum
                        };
                        const propRequired = (schema.required || []).includes(propName);
                        fieldHTML += createFieldHTML(propName, propSchema, propMeta, propRequired, valuePath);
                    }
                } else {
                    // 简单类型：直接创建输入框
                    const fieldPath = path + '[__temp__]';
                    if (schema.type === 'boolean') {
                        fieldHTML += createSwitchHTML(fieldPath, schema.default);
                    } else if (schema.type === 'number' || schema.type === 'integer') {
                        fieldHTML += createNumberInputHTML(fieldPath, schema, schema.default);
                    } else {
                        fieldHTML += createTextInputHTML(fieldPath, schema, schema.default || '');
                    }
                }
                fieldHTML += '<button type="button" class="btn btn-danger btn-sm btn-icon dict-item-remove" onclick="removeDictItem(\'' + path + '\', \'' + itemId + '\')" style="margin-top: 12px;">×</button>';
            }

            itemDiv.innerHTML = fieldHTML;
            container.appendChild(itemDiv);

            if (!existingKey) {
                // 新条目自动聚焦到键名输入框
                const keyInput = itemDiv.querySelector('.dict-key-input');
                if (keyInput) {
                    keyInput.focus();
                }
            }
        }

        function updateDictKey(path, itemId, newKey) {
            const container = document.getElementById('dict-items-' + path);
            if (!container) return;

            const item = container.querySelector('[data-id="' + itemId + '"]');
            if (!item) return;

            // 获取当前存储的键名，如果没有则默认为 __temp__
            const currentKey = item.dataset.currentKey || '__temp__';
            
            // 更新所有值字段的 name 属性
            const valueFields = item.querySelectorAll('[name]');
            if (newKey) {
                valueFields.forEach(function(valueField) {
                    const oldName = valueField.getAttribute('name');
                    // 跳过键名输入框本身
                    if (oldName === path + '[__key__]') {
                        return;
                    }
                    // 匹配模式：path[currentKey] 或 path[currentKey].subfield 或 path[currentKey][subkey]
                    // 使用当前存储的键名进行匹配
                    const keyPattern = new RegExp('^' + escapeRegExp(path) + '\\[' + escapeRegExp(currentKey) + '\\](.*)$');
                    const match = oldName.match(keyPattern);
                    if (match) {
                        const suffix = match[1];
                        valueField.setAttribute('name', path + '[' + newKey + ']' + suffix);
                    }
                });
                // 更新存储的当前键名
                item.dataset.currentKey = newKey;
            }
        }

        function removeDictItem(path, itemId) {
            const container = document.getElementById('dict-items-' + path);
            if (!container) return;

            const item = container.querySelector('[data-id="' + itemId + '"]');
            if (item) {
                item.remove();
            }
        }

        function initializeFormValues() {
            document.querySelectorAll('.switch input').forEach(function(switchEl) {
                updateSwitchText(switchEl);
                switchEl.addEventListener('change', function(e) { updateSwitchText(e.target); });
            });
        }

        function updateSwitchText(checkbox) {
            const container = checkbox.closest('.switch-container');
            const textSpan = container.querySelector('span');
            if (textSpan) {
                textSpan.textContent = checkbox.checked ? '已启用' : '已禁用';
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function toggleCollapse(element) {
            const section = element.closest('.form-section');
            if (section) {
                // 获取折叠按钮
                const toggleBtn = element.classList.contains('collapse-toggle') ? element : section.querySelector('.collapse-toggle');
                
                // 检查当前是否是折叠状态
                const isCurrentlyCollapsed = section.classList.contains('collapsed');
                
                if (isCurrentlyCollapsed) {
                    // 当前是折叠状态，需要展开
                    section.classList.remove('collapsed');
                    
                    // 确保移除了类，再设置按钮文本
                    setTimeout(() => {
                        if (toggleBtn) {
                            toggleBtn.textContent = '▼';
                        }
                    }, 0);
                } else {
                    // 当前是展开状态，需要折叠
                    section.classList.add('collapsed');
                    
                    // 确保添加了类，再设置按钮文本
                    setTimeout(() => {
                        if (toggleBtn) {
                            toggleBtn.textContent = '▶';
                        }
                    }, 0);
                }
                
                // 强制重排以确保CSS变更被应用
                void section.offsetWidth;
            }
        }

        function escapeRegExp(str) {
            return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        }

        function clearErrors() {
            document.querySelectorAll('.has-error').forEach(function(el) { el.classList.remove('has-error'); });
            document.querySelectorAll('.field-error').forEach(function(el) { el.textContent = ''; });
        }

        function showError(path, message) {
            const fieldGroup = document.querySelector('[data-path="' + path + '"]');
            if (fieldGroup) {
                fieldGroup.classList.add('has-error');
                const errorDiv = document.getElementById('error-' + path);
                if (errorDiv) {
                    errorDiv.textContent = message;
                }
            }
        }

        async function handleSubmit(event) {
            event.preventDefault();
            
            clearErrors();
            const config = {};
            
            const formData = new FormData(event.target);
            
            for (const name in schemaData.properties) {
                const prop = schemaData.properties[name];
                const value = collectFieldValue(name, prop, formData);
                if (value !== undefined) {
                    config[name] = value;
                }
            }
            
            for (let i = 0; i < schemaData.required.length; i++) {
                const required = schemaData.required[i];
                if (config[required] === undefined || config[required] === '' || config[required] === null) {
                    showError(required, '此字段为必填项');
                    return;
                }
            }

            try {
                const response = await fetch('/api/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config: config })
                });

                const result = await response.json();

                if (result.success) {
                    // 弹出成功提示
                    alert('✅ ' + result.message + '\n\n页面即将关闭...');
                    
                    // 调用 shutdown 接口关闭服务器
                    fetch('/api/shutdown', { method: 'POST' }).catch(() => {});
                    
                    // 关闭页面
                    setTimeout(function() {
                        window.close();
                        // 如果 window.close() 不起作用（非脚本打开的窗口），显示提示
                        document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;font-size:24px;color:#059669;">✅ 配置已保存，请手动关闭此页面</div>';
                    }, 500);
                } else {
                    for (let i = 0; i < result.errors.length; i++) {
                        const err = result.errors[i];
                        showError(err.path, err.message);
                    }
                }
            } catch (error) {
                document.getElementById('error').style.display = 'block';
                document.getElementById('error').textContent = '请求失败：' + error.message;
            }
        }

        // 辅助函数：将路径字符串解析为嵌套对象并设置值
        function setNestedValue(obj, path, value) {
            // 解析路径，支持 .field 和 [key] 格式
            const parts = [];
            let remaining = path;
            while (remaining) {
                if (remaining.startsWith('.')) {
                    // 处理 .field 格式
                    remaining = remaining.substring(1);
                    const dotMatch = remaining.match(/^([^.\[]+)/);
                    if (dotMatch) {
                        parts.push(dotMatch[1]);
                        remaining = remaining.substring(dotMatch[1].length);
                    }
                } else if (remaining.startsWith('[')) {
                    // 处理 [key] 格式
                    const bracketMatch = remaining.match(/^\[([^\]]+)\]/);
                    if (bracketMatch) {
                        parts.push(bracketMatch[1]);
                        remaining = remaining.substring(bracketMatch[0].length);
                    } else {
                        break;
                    }
                } else {
                    break;
                }
            }
            
            // 设置嵌套值
            let current = obj;
            for (let i = 0; i < parts.length - 1; i++) {
                if (!current[parts[i]]) {
                    current[parts[i]] = {};
                }
                current = current[parts[i]];
            }
            if (parts.length > 0) {
                current[parts[parts.length - 1]] = value;
            }
        }

        // 辅助函数：递归处理嵌套对象中的 __key__ 和 __temp__ 键
        function processNestedDictKeys(obj) {
            if (typeof obj !== 'object' || obj === null) {
                return obj;
            }
            
            if (Array.isArray(obj)) {
                return obj.map(item => processNestedDictKeys(item));
            }
            
            const result = {};
            let tempValue = null;
            let actualKey = null;
            
            // 第一遍：收集 __key__ 和 __temp__ 的值
            for (const key in obj) {
                if (key === '__key__') {
                    actualKey = obj[key];
                } else if (key === '__temp__') {
                    tempValue = processNestedDictKeys(obj[key]);
                } else {
                    // 递归处理其他键的值
                    result[key] = processNestedDictKeys(obj[key]);
                }
            }
            
            // 如果存在 __key__ 和 __temp__，用实际键名替换
            if (actualKey && tempValue !== null) {
                result[actualKey] = tempValue;
            } else if (tempValue !== null && !actualKey) {
                // 如果只有 __temp__ 没有 __key__，保留 __temp__ 的值但记录警告
                // 这种情况不应该发生，但为了安全起见处理它
                result['__temp__'] = tempValue;
            }
            
            return result;
        }

        function collectFieldValue(name, prop, formData) {
            const type = prop.type;

            // 先判断是否是字典类型（object 且有 additionalProperties 但没有 properties）
            if (type === 'object' && prop.additionalProperties && !prop.properties) {
                const dict = {};
                const tempData = {};  // 存储临时键名 __temp__ 的数据
                let actualKeyName = null;  // 存储用户输入的实际键名
                const entries = formData.entries();

                for (const [key, value] of entries) {
                    const match = key.match(new RegExp('^' + escapeRegExp(name) + '\\[([^\\]]+)\\](.*)$'));
                    if (match) {
                        const dictKey = match[1];
                        const subPath = match[2];

                        // 收集 __key__ 键的值（用户输入的实际键名）
                        if (dictKey === '__key__') {
                            if (value && value.trim() !== '') {
                                actualKeyName = value.trim();
                            }
                            continue;
                        }

                        // 如果是 __temp__ 键，先存储到 tempData 中
                        if (dictKey === '__temp__') {
                            if (!tempData.__temp__) {
                                tempData.__temp__ = subPath ? {} : value;
                            }
                            if (subPath) {
                                setNestedValue(tempData.__temp__, subPath, value);
                            } else {
                                tempData.__temp__ = value;
                            }
                            continue;
                        }

                        // 正常的字典键
                        if (!dict[dictKey]) {
                            dict[dictKey] = subPath ? {} : value;
                        }

                        if (subPath) {
                            // 使用辅助函数处理深层嵌套路径
                            setNestedValue(dict[dictKey], subPath, value);
                        } else {
                            dict[dictKey] = value;
                        }
                    }
                }

                // 处理临时键名 __temp__ 的数据
                // 使用第一次遍历时收集的实际键名
                if (tempData.__temp__ !== undefined && actualKeyName) {
                    if (!dict[actualKeyName]) {
                        dict[actualKeyName] = tempData.__temp__;
                    } else {
                        // 如果该键已存在，合并数据
                        if (typeof dict[actualKeyName] === 'object' && typeof tempData.__temp__ === 'object') {
                            Object.assign(dict[actualKeyName], tempData.__temp__);
                        } else {
                            dict[actualKeyName] = tempData.__temp__;
                        }
                    }
                }

                // 类型转换
                const valueSchema = prop.additionalProperties || {};
                if (valueSchema.type === 'number' || valueSchema.type === 'integer') {
                    for (const key in dict) {
                        dict[key] = valueSchema.type === 'integer' ? parseInt(dict[key]) : parseFloat(dict[key]);
                    }
                } else if (valueSchema.type === 'boolean') {
                    for (const key in dict) {
                        dict[key] = dict[key] === 'true';
                    }
                }

                // 递归处理嵌套对象中的 __key__ 和 __temp__ 键
                const processedDict = processNestedDictKeys(dict);
                return Object.keys(processedDict).length > 0 ? processedDict : prop.default || {};
            }
            
            if (type === 'array') {
                const values = [];
                const entries = formData.entries();
                let index = 0;
                
                for (const [key, value] of entries) {
                    if (key.startsWith(name + '[')) {
                        const match = key.match(new RegExp('^' + escapeRegExp(name) + '\\[(\\d+)\\](.*)$'));
                        if (match) {
                            const idx = parseInt(match[1]);
                            const subPath = match[2];
                            
                            while (values.length <= idx) {
                                values.push(subPath ? {} : null);
                            }
                            
                            if (subPath) {
                                if (subPath.startsWith('.')) {
                                    const subField = subPath.substring(1);
                                    if (!values[idx]) values[idx] = {};
                                    values[idx][subField] = value;
                                } else {
                                    values[idx][subPath] = value;
                                }
                            } else {
                                values[idx] = value;
                            }
                        }
                    }
                }
                
                if (values.length === 0) {
                    return prop.default || [];
                }
                
                const itemSchema = prop.items || {};
                if (itemSchema.type === 'number' || itemSchema.type === 'integer') {
                    return values.map(v => v ? (itemSchema.type === 'integer' ? parseInt(v) : parseFloat(v)) : v).filter(v => v !== null && v !== '');
                } else if (itemSchema.type === 'boolean') {
                    return values.map(v => v === 'true').filter(v => v !== null && v !== '');
                }
                
                return values.filter(v => v !== null && v !== '');
            }
            
            if (type === 'object') {
                const obj = {};
                const entries = formData.entries();
                const prefix = name + '.';
                
                for (const [key, value] of entries) {
                    if (key.startsWith(prefix)) {
                        const subField = key.substring(prefix.length);
                        if (prop.properties && prop.properties[subField]) {
                            const subType = prop.properties[subField].type;
                            if (subType === 'boolean') {
                                obj[subField] = value === 'true';
                            } else if (subType === 'number' || subType === 'integer') {
                                obj[subField] = subType === 'integer' ? parseInt(value) : parseFloat(value);
                            } else {
                                obj[subField] = value;
                            }
                        } else {
                            obj[subField] = value;
                        }
                    }
                }
                
                return Object.keys(obj).length > 0 ? obj : prop.default || {};
            }
            
            const value = formData.get(name);

            if (value === null || value === '') {
                if (type === 'boolean') {
                    return false;  // checkbox 未选中时返回 false，而不是默认值
                }
                return prop.default;
            }

            if (type === 'boolean') {
                return value === 'true';
            } else if (type === 'number' || type === 'integer') {
                return type === 'integer' ? parseInt(value) : parseFloat(value);
            } else {
                return value;
            }
        }

        // 使用事件委托处理折叠操作
        document.getElementById('form-fields').addEventListener('click', function(e) {
            if (e.target.classList.contains('form-section-header')) {
                // 如果点击的是折叠按钮，则不触发头部的折叠功能
                if (!e.target.classList.contains('collapse-toggle')) {
                    toggleCollapse(e.target);
                }
            } else if (e.target.classList.contains('collapse-toggle')) {
                e.stopPropagation();
                toggleCollapse(e.target.closest('.form-section'));
            }
        });
        
        document.getElementById('config-form').addEventListener('submit', handleSubmit);
        loadSchema();
    </script>
</body>
</html>
"""
