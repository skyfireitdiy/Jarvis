# -*- coding: utf-8 -*-
import os
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple



class EditFileTool:
    """文件编辑工具，用于对文件进行结构化编辑"""

    name = "edit_file"
    description = "对文件进行结构化编辑（通过块id）。\n\n    💡 使用步骤：\n    1. 先使用read_code工具获取文件的结构化块id\n    2. 通过块id进行精确的代码块操作（删除、插入、替换、编辑）\n    3. 避免手动计算行号，减少错误风险\n\n    📝 支持的操作类型：\n    - delete: 删除块\n    - insert_before: 在块前插入内容\n    - insert_after: 在块后插入内容\n    - replace: 替换整个块\n    - edit: 在块内进行search/replace（需要提供search和replace参数）"

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要修改的文件路径（支持绝对路径和相对路径）",
            },
            "diffs": {
                "type": "array",
                "items": {
                            "type": "object",
                            "properties": {
                                "block_id": {
                                    "type": "string",
                                    "description": "要操作的块id（从read_code工具获取的结构化块id）",
                                },
                                "action": {
                                    "type": "string",
                                    "enum": ["delete", "insert_before", "insert_after", "replace", "edit"],
                                    "description": "操作类型：delete（删除块）、insert_before（在块前插入）、insert_after（在块后插入）、replace（替换块）、edit（在块内进行search/replace）",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "新内容（对于insert_before、insert_after、replace操作必需，delete和edit操作不需要）",
                                },
                                "search": {
                                    "type": "string",
                                    "description": "要搜索的文本（对于edit操作必需）",
                                },
                                "replace": {
                                    "type": "string",
                                    "description": "替换后的文本（对于edit操作必需）",
                                },
                            },
                            "required": ["block_id", "action"],
                        },
                "description": "修改操作列表，每个操作包含一个结构化编辑块",
            },
        },
        "required": ["file_path", "diffs"],
    }

    def __init__(self):
        """初始化文件编辑工具"""
        pass


    @staticmethod
    def _validate_basic_args(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """验证基本参数
            
        Returns:
            如果验证失败，返回错误响应；否则返回None
        """
        file_path = args.get("file_path")
        diffs = args.get("diffs", [])

        if not file_path:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需参数：file_path",
            }

        if not diffs:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必需参数：diffs",
            }

        if not isinstance(diffs, list):
            return {
                "success": False,
                "stdout": "",
                "stderr": "diffs参数必须是数组类型",
            }
        
        return None

    @staticmethod
    def _get_file_cache(agent: Any, filepath: str) -> Optional[Dict[str, Any]]:
        """获取文件的缓存信息
        
        Args:
            agent: Agent实例
            filepath: 文件路径
            
        Returns:
            缓存信息字典，如果不存在则返回None
        """
        if not agent:
            return None
        
        cache = agent.get_user_data("read_code_cache")
        if not cache:
            return None
        
        abs_path = os.path.abspath(filepath)
        return cache.get(abs_path)

    @staticmethod
    def _is_cache_valid(cache_info: Optional[Dict[str, Any]], filepath: str) -> bool:
        """检查缓存是否有效
        
        Args:
            cache_info: 缓存信息字典
            filepath: 文件路径
            
        Returns:
            True表示缓存有效，False表示缓存无效
        """
        if not cache_info:
            return False
        
        try:
            # 检查文件是否存在
            if not os.path.exists(filepath):
                return False
            
            # 检查文件修改时间是否变化
            current_mtime = os.path.getmtime(filepath)
            cached_mtime = cache_info.get("file_mtime")
            
            if cached_mtime is None or abs(current_mtime - cached_mtime) > 0.1:  # 允许0.1秒的误差
                return False
            
            # 检查缓存数据结构是否完整
            if "id_list" not in cache_info or "blocks" not in cache_info or "total_lines" not in cache_info:
                return False
            
            return True
        except Exception:
            return False

    @staticmethod
    def _find_block_by_id_in_cache(cache_info: Dict[str, Any], block_id: str) -> Optional[Dict[str, Any]]:
        """从缓存中根据块id定位代码块
        
        Args:
            cache_info: 缓存信息字典
            block_id: 块id
            
        Returns:
            如果找到，返回包含 content 的字典；否则返回 None
        """
        if not cache_info:
            return None
        
        # 直接从 blocks 字典中查找
        blocks = cache_info.get("blocks", {})
        block = blocks.get(block_id)
        if block:
            return {
                "content": block.get("content", ""),
            }
        
        return None

    @staticmethod
    def _update_cache_timestamp(agent: Any, filepath: str) -> None:
        """更新缓存的时间戳
        
        Args:
            agent: Agent实例
            filepath: 文件路径
        """
        if not agent:
            return
        
        cache = agent.get_user_data("read_code_cache")
        if not cache:
            return
        
        abs_path = os.path.abspath(filepath)
        if abs_path in cache:
            cache[abs_path]["read_time"] = time.time()
            # 更新文件修改时间
            try:
                if os.path.exists(abs_path):
                    cache[abs_path]["file_mtime"] = os.path.getmtime(abs_path)
            except Exception:
                pass
            agent.set_user_data("read_code_cache", cache)

    @staticmethod
    def _validate_structured(diff: Dict[str, Any], idx: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """验证并转换structured类型的diff
        
        Returns:
            (错误响应或None, patch字典或None)
        """
        block_id = diff.get("block_id")
        action = diff.get("action")
        content = diff.get("content")
        
        if block_id is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少block_id参数",
            }, None)
        if not isinstance(block_id, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的block_id参数必须是字符串",
            }, None)
        if not block_id.strip():
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的block_id参数不能为空",
            }, None)
        
        if action is None:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff缺少action参数",
            }, None)
        if not isinstance(action, str):
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的action参数必须是字符串",
            }, None)
        if action not in ["delete", "insert_before", "insert_after", "replace", "edit"]:
            return ({
                "success": False,
                "stdout": "",
                "stderr": f"第 {idx+1} 个diff的action参数必须是 delete、insert_before、insert_after、replace 或 edit 之一",
            }, None)
        
        # 对于edit操作，需要search和replace参数
        if action == "edit":
            search = diff.get("search")
            replace = diff.get("replace")
            if search is None:
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff的action为 edit，需要提供search参数",
                }, None)
            if not isinstance(search, str):
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff的search参数必须是字符串",
                }, None)
            if replace is None:
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff的action为 edit，需要提供replace参数",
                }, None)
            if not isinstance(replace, str):
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff的replace参数必须是字符串",
                }, None)
        # 对于非delete和非edit操作，content是必需的
        elif action != "delete":
            if content is None:
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff的action为 {action}，需要提供content参数",
                }, None)
            if not isinstance(content, str):
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff的content参数必须是字符串",
            }, None)
        
        patch = {
            "STRUCTURED_BLOCK_ID": block_id,
            "STRUCTURED_ACTION": action,
        }
        if content is not None:
            patch["STRUCTURED_CONTENT"] = content
        if action == "edit":
            patch["STRUCTURED_SEARCH"] = diff.get("search")
            patch["STRUCTURED_REPLACE"] = diff.get("replace")
        return (None, patch)


    @staticmethod
    def _convert_diffs_to_patches(diffs: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, str]]]:
        """验证并转换diffs为内部patches格式
        
        Returns:
            (错误响应或None, patches列表)
        """
        patches = []
        for idx, diff in enumerate(diffs):
            if not isinstance(diff, dict):
                return ({
                    "success": False,
                    "stdout": "",
                    "stderr": f"第 {idx+1} 个diff必须是字典类型",
                }, [])
            
            # 所有diff都是structured类型
            error_response, patch = EditFileTool._validate_structured(diff, idx + 1)
            
            if error_response:
                return (error_response, [])
            
            if patch:
                patches.append(patch)
        
        return (None, patches)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行文件编辑操作"""
        try:
            # 验证基本参数
            error_response = EditFileTool._validate_basic_args(args)
            if error_response:
                return error_response
            
            file_path = args.get("file_path")
            diffs = args.get("diffs", [])

            # 转换diffs为patches
            error_response, patches = EditFileTool._convert_diffs_to_patches(diffs)
            if error_response:
                return error_response

            # 记录 PATCH 操作调用统计
            try:
                from jarvis.jarvis_stats.stats import StatsManager

                StatsManager.increment("patch", group="tool")
            except Exception:
                pass

            # 获取 agent
            agent = args.get("agent", None)

            # 执行编辑
            success, result = self._fast_edit(file_path, patches, agent)

            if success:
                return {
                    "success": True,
                    "stdout": f"文件 {file_path} 修改成功",
                    "stderr": "",
                }
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": result,
                }

        except Exception as e:
            error_msg = f"文件编辑失败: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}

    @staticmethod
    def _read_file_with_backup(file_path: str) -> Tuple[str, Optional[str]]:
        """读取文件并创建备份
        
        Args:
            file_path: 文件路径
            
        Returns:
            (文件内容, 备份文件路径或None)
        """
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        file_content = ""
        backup_path = None
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            # 创建备份文件
            backup_path = abs_path + ".bak"
            try:
                shutil.copy2(abs_path, backup_path)
            except Exception:
                # 备份失败不影响主流程
                backup_path = None
        
        return file_content, backup_path

    @staticmethod
    def _order_patches_by_range(patches: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """按顺序返回补丁列表
        
        注意：对于结构化编辑，由于需要在实际应用时才能获取块的行号范围，
        这里暂时按原始顺序返回。如果需要优化，可以在应用时动态排序。
        
        Args:
            patches: 补丁列表
            
        Returns:
            补丁列表（当前按原始顺序返回）
        """
        # 对于结构化编辑，暂时按原始顺序处理
        # 如果需要按行号排序，需要在应用时动态获取块的行号范围
        return patches


    @staticmethod
    def _restore_file_from_cache(cache_info: Dict[str, Any]) -> str:
        """从缓存恢复文件内容
        
        Args:
            cache_info: 缓存信息字典
            
        Returns:
            恢复的文件内容字符串（与原始文件内容完全一致）
        """
        if not cache_info:
            return ""
        
        # 按照 id_list 的顺序恢复
        id_list = cache_info.get("id_list", [])
        blocks = cache_info.get("blocks", {})
        file_ends_with_newline = cache_info.get("file_ends_with_newline", False)
        
        result = []
        for idx, block_id in enumerate(id_list):
            block = blocks.get(block_id)
            if block:
                content = block.get('content', '')
                if content:
                    result.append(content)
                    # 在块之间添加换行符（最后一个块后面根据文件是否以换行符结尾决定）
                    is_last_block = (idx == len(id_list) - 1)
                    if is_last_block:
                        # 最后一个块：如果文件以换行符结尾，添加换行符
                        if file_ends_with_newline:
                            result.append('\n')
                    else:
                        # 非最后一个块：在块之间添加换行符
                        result.append('\n')
        
        return ''.join(result) if result else ""

    @staticmethod
    def _apply_structured_edit_to_cache(
        cache_info: Dict[str, Any],
        block_id: str,
        action: str,
        new_content: Optional[str] = None,
        search: Optional[str] = None,
        replace: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """在缓存中应用结构化编辑
        
        Args:
            cache_info: 缓存信息字典（会被修改）
            block_id: 块id（字符串，从read_code工具获取）
            action: 操作类型（delete, insert_before, insert_after, replace, edit）
            new_content: 新内容（对于非delete和非edit操作）
            search: 要搜索的文本（对于edit操作）
            replace: 替换后的文本（对于edit操作）
            
        Returns:
            (是否成功, 错误信息)
        """
        if not cache_info:
            return (False, "缓存信息不完整")
        
        # 从 blocks 字典中查找
        blocks = cache_info.get("blocks", {})
        block = blocks.get(block_id)
        
        if block is None:
            return (False, f"未找到块id: {block_id}。请使用read_code工具查看文件的结构化块id。")
        
        # 根据操作类型执行编辑
        if action == "delete":
            # 删除块：将当前块的内容清空
            block['content'] = ""
            return (True, None)
        
        elif action == "insert_before":
            # 在块前插入：在当前块的内容前面插入文本
            if new_content is None:
                return (False, "insert_before操作需要提供content参数")
            
            current_content = block.get('content', '')
            # 自动添加换行符：在插入内容后添加换行符（如果插入内容不以换行符结尾）
            if new_content and not new_content.endswith('\n'):
                new_content = new_content + '\n'
            block['content'] = new_content + current_content
            return (True, None)
        
        elif action == "insert_after":
            # 在块后插入：在当前块的内容后面插入文本
            if new_content is None:
                return (False, "insert_after操作需要提供content参数")
            
            current_content = block.get('content', '')
            # 自动添加换行符：在插入内容前添加换行符（如果插入内容不以换行符开头）
            # 避免重复换行符：如果当前内容以换行符结尾，则不需要添加
            if new_content and not new_content.startswith('\n'):
                # 如果当前内容不以换行符结尾，则在插入内容前添加换行符
                if not current_content or not current_content.endswith('\n'):
                    new_content = '\n' + new_content
            block['content'] = current_content + new_content
            return (True, None)
        
        elif action == "replace":
            # 替换块
            if new_content is None:
                return (False, "replace操作需要提供content参数")
            
            block['content'] = new_content
            return (True, None)
        
        elif action == "edit":
            # 在块内进行search/replace
            if search is None:
                return (False, "edit操作需要提供search参数")
            if replace is None:
                return (False, "edit操作需要提供replace参数")
            
            current_content = block.get('content', '')
            if search not in current_content:
                return (False, f"在块 {block_id} 中未找到要搜索的文本: {search[:100]}...")
            
            # 在块内进行替换（只替换第一次出现）
            block['content'] = current_content.replace(search, replace, 1)
            return (True, None)
        
        else:
            return (False, f"不支持的操作类型: {action}")

    @staticmethod
    def _format_patch_description(patch: Dict[str, str]) -> str:
        """格式化补丁描述用于错误信息
        
        Args:
            patch: 补丁字典
            
        Returns:
            补丁描述字符串
        """
        if "STRUCTURED_BLOCK_ID" in patch:
            block_id = patch.get('STRUCTURED_BLOCK_ID', '')
            action = patch.get('STRUCTURED_ACTION', '')
            if action == "edit":
                search = patch.get('STRUCTURED_SEARCH', '')
                replace = patch.get('STRUCTURED_REPLACE', '')
                search_preview = search[:50] + "..." if len(search) > 50 else search
                replace_preview = replace[:50] + "..." if len(replace) > 50 else replace
                return f"结构化编辑: block_id={block_id}, action={action}, search={search_preview}, replace={replace_preview}"
            else:
                content = patch.get('STRUCTURED_CONTENT', '')
                if content:
                    content_preview = content[:100] + "..." if len(content) > 100 else content
                    return f"结构化编辑: block_id={block_id}, action={action}, content={content_preview}"
                else:
                    return f"结构化编辑: block_id={block_id}, action={action}"
        else:
            return "未知的补丁格式"

    @staticmethod
    def _generate_error_summary(
        abs_path: str,
        failed_patches: List[Dict[str, Any]],
        patch_count: int,
        successful_patches: int
    ) -> str:
        """生成错误摘要
        
        Args:
            abs_path: 文件绝对路径
            failed_patches: 失败的补丁列表
            patch_count: 总补丁数
            successful_patches: 成功的补丁数
            
        Returns:
            错误摘要字符串
        """
        error_details = []
        for p in failed_patches:
            patch = p["patch"]
            patch_desc = EditFileTool._format_patch_description(patch)
            error_details.append(f"  - 失败的补丁: {patch_desc}\n    错误: {p['error']}")
        
        if successful_patches == 0:
            summary = (
                f"文件 {abs_path} 修改失败（全部失败，文件未修改）。\n"
                f"失败: {len(failed_patches)}/{patch_count}.\n"
                f"失败详情:\n" + "\n".join(error_details)
            )
        else:
            summary = (
                f"文件 {abs_path} 修改部分成功。\n"
                f"成功: {successful_patches}/{patch_count}, "
                f"失败: {len(failed_patches)}/{patch_count}.\n"
                f"失败详情:\n" + "\n".join(error_details)
            )
        return summary

    @staticmethod
    def _write_file_with_rollback(
        abs_path: str,
        content: str,
        backup_path: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """写入文件，失败时回滚
        
        Args:
            abs_path: 文件绝对路径
            content: 要写入的内容
            backup_path: 备份文件路径或None
            
        Returns:
            (是否成功, 错误信息或None)
        """
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return (True, None)
        except Exception as write_error:
            # 写入失败，尝试回滚
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, abs_path)
                    os.remove(backup_path)
                except Exception:
                    pass
            error_msg = f"文件写入失败: {str(write_error)}"
            print(f"❌ {error_msg}")
            return (False, error_msg)

    @staticmethod
    def _fast_edit(file_path: str, patches: List[Dict[str, str]], agent: Any = None) -> Tuple[bool, str]:
        """快速应用补丁到文件

        该方法基于缓存进行编辑：
        1. 先检查缓存有效性，无效则提示重新读取
        2. 在缓存中应用所有补丁
        3. 从缓存恢复文件内容并写入
        4. 更新缓存的时间戳

        Args:
            file_path: 要修改的文件路径，支持绝对路径和相对路径
            patches: 补丁列表，每个补丁包含 STRUCTURED_BLOCK_ID
            agent: Agent实例，用于访问缓存

        Returns:
            Tuple[bool, str]:
                返回处理结果元组，第一个元素表示是否所有补丁都成功应用，
                第二个元素为结果信息，全部成功时为修改后的文件内容，部分或全部失败时为错误信息
        """
        abs_path = os.path.abspath(file_path)
        backup_path = None
        
        try:
            # 检查缓存有效性
            cache_info = EditFileTool._get_file_cache(agent, abs_path)
            if not EditFileTool._is_cache_valid(cache_info, abs_path):
                error_msg = (
                    f"⚠️ 缓存无效或文件已被外部修改。\n"
                    f"📋 文件: {abs_path}\n"
                    f"💡 请先使用 read_code 工具重新读取文件，然后再进行编辑。"
                )
                return False, error_msg
            
            # 创建缓存副本，避免直接修改原缓存
            cache_copy = {
                "id_list": list(cache_info["id_list"]),  # 浅拷贝列表
                "blocks": {k: v.copy() for k, v in cache_info["blocks"].items()},  # 深拷贝字典
                "total_lines": cache_info["total_lines"],
                "read_time": cache_info.get("read_time", time.time()),
                "file_mtime": cache_info.get("file_mtime", 0),
                "file_ends_with_newline": cache_info.get("file_ends_with_newline", False),
            }
            
            # 创建备份
            if os.path.exists(abs_path):
                backup_path = abs_path + ".bak"
                try:
                    shutil.copy2(abs_path, backup_path)
                except Exception:
                    backup_path = None
            
            # 对补丁进行排序
            ordered_patches = EditFileTool._order_patches_by_range(patches)
            patch_count = len(ordered_patches)
            failed_patches: List[Dict[str, Any]] = []
            successful_patches = 0
            
            # 在缓存中应用所有补丁
            for patch in ordered_patches:
                # 结构化编辑模式
                if "STRUCTURED_BLOCK_ID" in patch:
                    block_id = patch.get("STRUCTURED_BLOCK_ID", "")
                    action = patch.get("STRUCTURED_ACTION", "")
                    new_content = patch.get("STRUCTURED_CONTENT")
                    search = patch.get("STRUCTURED_SEARCH")
                    replace = patch.get("STRUCTURED_REPLACE")
                    try:
                        success, error_msg = EditFileTool._apply_structured_edit_to_cache(
                            cache_copy, block_id, action, new_content, search, replace
                        )
                        if success:
                            successful_patches += 1
                        else:
                            failed_patches.append({"patch": patch, "error": error_msg})
                    except Exception as e:
                        error_msg = (
                            f"结构化编辑执行出错: {str(e)}\n"
                            f"block_id: {block_id}, action: {action}"
                        )
                        failed_patches.append({"patch": patch, "error": error_msg})
                else:
                    # 如果不支持的模式，记录错误
                    error_msg = "不支持的补丁格式。支持的格式: STRUCTURED_BLOCK_ID"
                    failed_patches.append({"patch": patch, "error": error_msg})
            
            # 如果有失败的补丁，且没有成功的补丁，则不写入文件
            if failed_patches and successful_patches == 0:
                if backup_path and os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                summary = EditFileTool._generate_error_summary(
                    abs_path, failed_patches, patch_count, successful_patches
                )
                print(f"❌ {summary}")
                return False, summary
            
            # 从缓存恢复文件内容
            modified_content = EditFileTool._restore_file_from_cache(cache_copy)
            if not modified_content:
                error_msg = "从缓存恢复文件内容失败"
                if backup_path and os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                return False, error_msg
            
            # 写入文件
            success, error_msg = EditFileTool._write_file_with_rollback(abs_path, modified_content, backup_path)
            if not success:
                return False, error_msg
            
            # 写入成功，更新缓存
            if agent:
                cache = agent.get_user_data("read_code_cache")
                if cache and abs_path in cache:
                    # 更新缓存内容
                    cache[abs_path] = cache_copy
                    # 更新缓存时间戳
                    EditFileTool._update_cache_timestamp(agent, abs_path)
                    agent.set_user_data("read_code_cache", cache)
            
            # 写入成功，删除备份文件
            if backup_path and os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception:
                    pass
            
            # 如果有失败的补丁，返回部分成功信息
            if failed_patches:
                summary = EditFileTool._generate_error_summary(
                    abs_path, failed_patches, patch_count, successful_patches
                )
                print(f"❌ {summary}")
                return False, summary
            
            return True, modified_content
            
        except Exception as e:
            # 发生异常时，尝试回滚
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, abs_path)
                    os.remove(backup_path)
                except Exception:
                    pass
            error_msg = f"文件修改失败: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg

