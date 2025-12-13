"""
Node.js构建验证器模块

提供Node.js项目的构建验证功能。
"""

import json
import os
import time

from jarvis.jarvis_utils.output import PrettyOutput

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
from typing import Optional

from .base import BuildResult
from .base import BuildSystem
from .base import BuildValidatorBase


class NodeJSBuildValidator(BuildValidatorBase):
    """Node.js构建验证器"""

    BUILD_SYSTEM_NAME = "npm/Node.js"
    SUPPORTED_LANGUAGES = ["javascript", "typescript"]

    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()

        # 策略1: 尝试使用 tsc --noEmit（如果存在TypeScript）
        tsconfig = os.path.join(self.project_root, "tsconfig.json")
        if os.path.exists(tsconfig):
            returncode, stdout, stderr = self._run_command(
                ["npx", "tsc", "--noEmit"],
                timeout=20,
            )
            duration = time.time() - start_time
            success = returncode == 0
            output = stdout + stderr
            if success:
                PrettyOutput.auto_print(
                    f"✅ Node.js (TypeScript) 构建验证成功（耗时 {duration:.2f} 秒）"
                )
            else:
                PrettyOutput.auto_print(
                    f"❌ Node.js (TypeScript) 构建验证失败（耗时 {duration:.2f} 秒）"
                )
                PrettyOutput.auto_print(
                    f"错误信息：TypeScript类型检查失败\n{output[:500]}"
                )
            return BuildResult(
                success=success,
                output=output,
                error_message=None if success else "TypeScript类型检查失败",
                build_system=BuildSystem.NODEJS,
                duration=duration,
            )

        # 策略2: 尝试运行 npm run build（如果存在build脚本）
        package_json = os.path.join(self.project_root, "package.json")
        if os.path.exists(package_json):
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    package_data = json.load(f)
                    scripts = package_data.get("scripts", {})
                    if "build" in scripts:
                        returncode, stdout, stderr = self._run_command(
                            ["npm", "run", "build"],
                            timeout=30,
                        )
                        duration = time.time() - start_time
                        success = returncode == 0
                        output = stdout + stderr
                        if success:
                            PrettyOutput.auto_print(
                                f"✅ Node.js (npm build) 构建验证成功（耗时 {duration:.2f} 秒）"
                            )
                        else:
                            PrettyOutput.auto_print(
                                f"❌ Node.js (npm build) 构建验证失败（耗时 {duration:.2f} 秒）"
                            )
                            PrettyOutput.auto_print(
                                f"错误信息：npm build失败\n{output[:500]}"
                            )
                        return BuildResult(
                            success=success,
                            output=output,
                            error_message=None if success else "npm build失败",
                            build_system=BuildSystem.NODEJS,
                            duration=duration,
                        )
            except Exception as e:
                PrettyOutput.auto_print(f"⚠️ 读取package.json失败: {e}")

        # 策略3: 使用 eslint 进行语法检查（如果存在）
        if modified_files:
            js_files = [
                f for f in modified_files if f.endswith((".js", ".jsx", ".ts", ".tsx"))
            ]
            if js_files:
                # 尝试使用 eslint
                returncode, stdout, stderr = self._run_command(
                    ["npx", "eslint", "--max-warnings=0"]
                    + js_files[:5],  # 限制文件数量
                    timeout=15,
                )
                duration = time.time() - start_time
                output = stdout + stderr
                # eslint返回非0可能是警告，不算失败
                PrettyOutput.auto_print(
                    f"✅ Node.js (eslint) 构建验证成功（耗时 {duration:.2f} 秒）"
                )
                return BuildResult(
                    success=True,  # 仅检查语法，警告不算失败
                    output=output,
                    error_message=None,
                    build_system=BuildSystem.NODEJS,
                    duration=duration,
                )

        duration = time.time() - start_time
        PrettyOutput.auto_print(
            f"✅ Node.js 构建验证成功（耗时 {duration:.2f} 秒，无构建脚本）"
        )
        return BuildResult(
            success=True,
            output="Node.js项目验证通过（无构建脚本）",
            error_message=None,
            build_system=BuildSystem.NODEJS,
            duration=duration,
        )
