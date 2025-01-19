import hashlib
import os
import re
import sqlite3
import time
from typing import Dict, Any, List, Optional, Tuple

import yaml
from jarvis.models.base import BasePlatform
from jarvis.utils import OutputType, PrettyOutput, get_multiline_input, load_env_from_file
from jarvis.models.registry import PlatformRegistry

class JarvisCoder:
    def __init__(self, root_dir: str, language: str):
        """初始化代码修改工具"""
        self.main_model = None
        self.db_path = ""
        self.root_dir = root_dir
        self.platform = os.environ.get("JARVIS_CODEGEN_PLATFORM")
        self.model = os.environ.get("JARVIS_CODEGEN_MODEL")
        self.language = language

        self.root_dir = self._find_git_root_dir(self.root_dir)
        if not self.root_dir:
            self.root_dir = root_dir

        PrettyOutput.print(f"Git根目录: {self.root_dir}", OutputType.INFO)

        # 1. 判断代码库路径是否存在，如果不存在，创建
        if not os.path.exists(self.root_dir):
            PrettyOutput.print(
                "Root directory does not exist, creating...", OutputType.INFO)
            os.makedirs(self.root_dir)

        os.chdir(self.root_dir)

        self.jarvis_dir = os.path.join(self.root_dir, ".jarvis-coder")
        if not os.path.exists(self.jarvis_dir):
            os.makedirs(self.jarvis_dir)

        self.index_db_path = os.path.join(self.jarvis_dir, "index.db")
        if not os.path.exists(self.index_db_path):
            self._create_index_db()

        self.record_dir = os.path.join(self.jarvis_dir, "record")
        if not os.path.exists(self.record_dir):
            os.makedirs(self.record_dir)

        # 2. 判断代码库是否是git仓库，如果不是，初始化git仓库
        if not os.path.exists(os.path.join(self.root_dir, ".git")):
            PrettyOutput.print(
                "Git repository does not exist, initializing...", OutputType.INFO)
            os.system(f"git init")
            # 2.1 添加所有的文件
            os.system(f"git add .")
            # 2.2 提交
            os.system(f"git commit -m 'Initial commit'")

        # 3. 查看代码库是否有未提交的文件，如果有，提交一次
        if self._has_uncommitted_files():
            PrettyOutput.print("代码库有未提交的文件，提交一次", OutputType.INFO)
            os.system(f"git add .")
            os.system(f"git commit -m 'commit before code edit'")

    def _new_model(self):
        """获取大模型"""
        model = PlatformRegistry().get_global_platform_registry().create_platform(self.platform)
        if self.model:
            model_name = self.model
            model.set_model_name(model_name)
        return model

    def _has_uncommitted_files(self) -> bool:
        """判断代码库是否有未提交的文件"""
        # 获取未暂存的修改
        unstaged = os.popen("git diff --name-only").read()
        # 获取已暂存但未提交的修改
        staged = os.popen("git diff --cached --name-only").read()
        # 获取未跟踪的文件
        untracked = os.popen("git ls-files --others --exclude-standard").read()
        
        return bool(unstaged or staged or untracked)

    def _call_model_with_retry(self, model: BasePlatform, prompt: str, max_retries: int = 3, initial_delay: float = 1.0) -> Tuple[bool, str]:
        """调用模型并支持重试
        
        Args:
            prompt: 提示词
            max_retries: 最大重试次数
            initial_delay: 初始延迟时间(秒)
            
        Returns:
            Tuple[bool, str]: (是否成功, 响应内容)
        """
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                response = model.chat(prompt)
                return True, response
            except Exception as e:
                if attempt == max_retries - 1:  # 最后一次尝试
                    PrettyOutput.print(f"调用模型失败: {str(e)}", OutputType.ERROR)
                    return False, str(e)
                    
                PrettyOutput.print(f"调用模型失败，{delay}秒后重试: {str(e)}", OutputType.WARNING)
                time.sleep(delay)
                delay *= 2  # 指数退避
                
    def _get_key_info(self, file_path: str, content: str) -> Optional[Dict[str, Any]]:
        """获取文件的关键信息
        
        Args:
            file_path: 文件路径
            content: 文件内容
            
        Returns:
            Optional[Dict[str, Any]]: 文件信息，包含文件描述
        """
        model = self._new_model()  # 创建新的模型实例
        
        prompt = f"""你是一个资深程序员，请根据文件内容，生成文件的关键信息，要求如下，除了代码，不要输出任何内容：

1. 文件路径: {file_path}
2. 文件内容:(<CONTENT_START>和<CONTENT_END>之间的部分) 
<CONTENT_START>
{content}
<CONTENT_END>
3. 关键信息: 请生成文件的功能描述，仅输出以下格式内容
<FILE_INFO_START>
file_description: 这个文件的主要功能和作用描述
<FILE_INFO_END>
"""
        try:
            response = model.chat(prompt)
            model.delete_chat()  # 删除会话历史
            old_response = response
            response = response.replace("<FILE_INFO_START>", "").replace("<FILE_INFO_END>", "")
            if old_response != response:
                return yaml.safe_load(response)
            else:
                return None
        except Exception as e:
            PrettyOutput.print(f"解析文件信息失败: {str(e)}", OutputType.ERROR)
            return None
        finally:
            # 确保清理模型资源
            try:
                model.delete_chat()
            except:
                pass



    def _get_file_md5(self, file_path: str) -> str:
        """获取文件MD5"""
        return hashlib.md5(open(file_path, "rb").read()).hexdigest()

    def _create_index_db(self):
        """创建索引数据库"""
        if not os.path.exists(self.index_db_path):
            PrettyOutput.print("Index database does not exist, creating...", OutputType.INFO)
            index_db = sqlite3.connect(self.index_db_path)
            index_db.execute(
                "CREATE TABLE files (file_path TEXT PRIMARY KEY, file_md5 TEXT, file_description TEXT)")
            index_db.commit()
            index_db.close()
            PrettyOutput.print("Index database created", OutputType.SUCCESS)
            # commit
            os.chdir(self.root_dir)
            os.system(f"git add .gitignore -f")
            os.system(f"git commit -m 'add index database'")

    def _find_file_by_md5(self, file_md5: str) -> Optional[str]:
        """根据文件MD5查找文件路径"""
        index_db = sqlite3.connect(self.index_db_path)
        cursor = index_db.cursor()
        cursor.execute(
            "SELECT file_path FROM files WHERE file_md5 = ?", (file_md5,))
        result = cursor.fetchone()
        index_db.close()
        return result[0] if result else None

    def _update_file_path(self, file_path: str, file_md5: str):
        """更新文件路径"""
        index_db = sqlite3.connect(self.index_db_path)
        cursor = index_db.cursor()
        cursor.execute(
            "UPDATE files SET file_path = ? WHERE file_md5 = ?", (file_path, file_md5))
        index_db.commit()
        index_db.close()

    def _insert_info(self, file_path: str, file_md5: str, file_description: str):
        """插入文件信息"""
        index_db = sqlite3.connect(self.index_db_path)
        cursor = index_db.cursor()
        cursor.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
        cursor.execute("INSERT INTO files (file_path, file_md5, file_description) VALUES (?, ?, ?)",
                       (file_path, file_md5, file_description))
        index_db.commit()
        index_db.close()

    def _is_text_file(self, file_path: str) -> bool:
        """判断文件是否是文本文件"""
        try:
            with open(file_path, 'rb') as f:
                # 读取文件前1024个字节
                chunk = f.read(1024)
                # 检查是否包含空字节
                if b'\x00' in chunk:
                    return False
                # 尝试解码为文本
                chunk.decode('utf-8')
                return True
        except:
            return False

    def _index_project(self):
        """建立代码库索引"""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        git_files = os.popen("git ls-files").read().splitlines()

        index_db = sqlite3.connect(self.index_db_path)
        cursor = index_db.cursor()
        cursor.execute("SELECT file_path FROM files")
        db_files = [row[0] for row in cursor.fetchall()]
        for db_file in db_files:
            if not os.path.exists(db_file):
                cursor.execute("DELETE FROM files WHERE file_path = ?", (db_file,))
                PrettyOutput.print(f"删除不存在的文件记录: {db_file}", OutputType.INFO)
        index_db.commit()
        index_db.close()

        def process_file(file_path: str):
            """处理单个文件的索引任务"""
            if not self._is_text_file(file_path):
                return

            # 计算文件MD5
            file_md5 = self._get_file_md5(file_path)

            # 查找文件
            file_path_in_db = self._find_file_by_md5(file_md5)
            if file_path_in_db:
                PrettyOutput.print(
                    f"文件 {file_path} 重复，跳过", OutputType.INFO)
                if file_path_in_db != file_path:
                    self._update_file_path(file_path, file_md5)
                    PrettyOutput.print(
                        f"文件 {file_path} 重复，更新路径为 {file_path}", OutputType.INFO)
                return

            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
                key_info = self._get_key_info(file_path, file_content)
                if not key_info:
                    PrettyOutput.print(
                        f"文件 {file_path} 索引失败", OutputType.INFO)
                    return
                if "file_description" in key_info:
                    self._insert_info(file_path, file_md5, key_info["file_description"])
                    PrettyOutput.print(
                        f"文件 {file_path} 已建立索引", OutputType.INFO)
                else:
                    PrettyOutput.print(
                        f"文件 {file_path} 不是代码文件，跳过", OutputType.INFO)

        # 使用线程池处理文件索引
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_file, file_path) for file_path in git_files]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    PrettyOutput.print(f"处理文件时发生错误: {str(e)}", OutputType.ERROR)

        PrettyOutput.print("项目索引完成", OutputType.INFO)

    def _find_related_files(self, feature: str) -> List[Dict]:
        """根据需求描述，查找相关文件"""
        try:
            # Get all files from database
            index_db = sqlite3.connect(self.index_db_path)
            cursor = index_db.cursor()
            cursor.execute("SELECT file_path, file_description FROM files")
            all_files = cursor.fetchall()
            index_db.close()
        except sqlite3.Error as e:
            PrettyOutput.print(f"数据库操作失败: {str(e)}", OutputType.ERROR)
            return []

        batch_size = 100
        batch_results = []  # Store results from each batch with their scores
        
        for i in range(0, len(all_files), batch_size):
            batch_files = all_files[i:i + batch_size]
            
            prompt = """你是资深程序员，请根据需求描述，从以下文件路径中选出最相关的文件，按相关度从高到低排序。

相关度打分标准(0-9分)：
- 9分：文件名直接包含需求中的关键词，且文件功能与需求完全匹配
- 7-8分：文件名包含需求相关词，或文件功能与需求高度相关
- 5-6分：文件名暗示与需求有关，或文件功能与需求部分相关
- 3-4分：文件可能需要小幅修改以配合需求
- 1-2分：文件与需求关系较远，但可能需要少量改动
- 0分：文件与需求完全无关

请输出yaml格式，仅输出以下格式内容：
<RELEVANT_FILES_START>
file1.py: 9
file2.py: 7
<RELEVANT_FILES_END>

文件列表：
"""
            for file_path, _ in batch_files:
                prompt += f"- {file_path}\n"
            prompt += f"\n需求描述: {feature}\n"
            prompt += "\n注意：\n1. 只输出最相关的文件，不超过5个\n2. 根据上述打分标准判断相关性\n3. 相关度必须是0-9的整数"
            
            success, response = self._call_model_with_retry(self._new_model(), prompt)
            if not success:
                continue
            
            try:
                response = response.replace("<RELEVANT_FILES_START>", "").replace("<RELEVANT_FILES_END>", "")
                result = yaml.safe_load(response)
                
                # Convert results to file objects with scores
                batch_files_dict = {f[0]: f[1] for f in batch_files}
                for file_path, score in result.items():
                    if isinstance(file_path, str) and isinstance(score, int):
                        score = max(0, min(9, score))  # Ensure score is between 0-9
                        if file_path in batch_files_dict:
                            batch_results.append({
                                "file_path": file_path,
                                "file_description": batch_files_dict[file_path],
                                "score": score
                            })
                            
            except Exception as e:
                PrettyOutput.print(f"处理批次文件失败: {str(e)}", OutputType.ERROR)
                continue
        
        # Sort all results by score
        batch_results.sort(key=lambda x: x["score"], reverse=True)
        top_files = batch_results[:5]
        
        # If we don't have enough files, add more from database
        if len(top_files) < 5:
            remaining_files = [f for f in all_files if f[0] not in [tf["file_path"] for tf in top_files]]
            top_files.extend([{
                "file_path": f[0],
                "file_description": f[1],
                "score": 0
            } for f in remaining_files[:5-len(top_files)]])

        # Now do content relevance analysis on these files
        score = [[], [], [], [], [], [], [], [], [], []]
        
        prompt = """你是资深程序员，请根据需求描述，分析文件的相关性。

相关度打分标准(0-9分)：
- 9分：文件内容与需求完全匹配，是实现需求的核心文件
- 7-8分：文件内容与需求高度相关，需要较大改动
- 5-6分：文件内容与需求部分相关，需要中等改动
- 3-4分：文件内容与需求相关性较低，但需要配合修改
- 1-2分：文件内容与需求关系较远，只需极少改动
- 0分：文件内容与需求完全无关

文件列表如下：
<FILE_LIST_START>
"""
        for i, file in enumerate(top_files):
            prompt += f"""{i}. {file["file_path"]} : {file["file_description"]}\n"""
        prompt += f"""需求描述: {feature}\n"""
        prompt += "<FILE_LIST_END>\n"
        prompt += """请根据需求描述和文件描述，分析文件的相关性，输出每个编号的相关性[0~9]，仅输出以下格式内容(key为文件编号，value为相关性)：
<FILE_RELATION_START>
"0": 5
"1": 3
<FILE_RELATION_END>"""
        
        success, response = self._call_model_with_retry(self._new_model(), prompt)
        if not success:
            return top_files[:5]  # Return top 5 files from filename matching if model fails
        
        try:
            response = response.replace("<FILE_RELATION_START>", "").replace("<FILE_RELATION_END>", "")
            file_relation = yaml.safe_load(response)
            if not file_relation:
                return top_files[:5]
            
            for file_id, relation in file_relation.items():
                id = int(file_id)
                relation = max(0, min(9, relation))  # 确保范围在0-9之间
                score[relation].append(top_files[id])
            
        except Exception as e:
            PrettyOutput.print(f"处理文件关系失败: {str(e)}", OutputType.ERROR)
            return top_files[:5]
        
        files = []
        score.reverse()
        for i in score:
            files.extend(i)
            if len(files) >= 5:  # 直接取相关性最高的5个文件
                break
        
        return files[:5]
    
    def _remake_patch(self, prompt: str) -> List[str]:
        success, response = self._call_model_with_retry(self.main_model, prompt, max_retries=5)  # 增加重试次数
        if not success:
            return []
            
        try:
            patches = re.findall(r'<PATCH_START>.*?<PATCH_END>', response, re.DOTALL)
            return [patch.replace('<PATCH_START>', '').replace('<PATCH_END>', '').strip() 
                   for patch in patches if patch.strip()]
        except Exception as e:
            PrettyOutput.print(f"解析patch失败: {str(e)}", OutputType.ERROR)
            return []
        
    def _make_patch(self, related_files: List[Dict], feature: str) -> List[str]:
        """生成修改方案"""
        prompt = """你是一个资深程序员，请根据需求描述，修改文件内容。

修改格式说明：
1. 每个修改块格式如下：
<PATCH_START>
>>>>>> path/to/file
要替换的内容
======
新的内容
<<<<<<
<PATCH_END>

2. 如果是新文件，格式如下：
<PATCH_START>
>>>>>> path/to/new/file
======
新文件的完整内容
<<<<<<
<PATCH_END>

文件列表如下：
"""
        for i, file in enumerate(related_files):
            prompt += f"""{i}. {file["file_path"]} : {file["file_description"]}\n"""
            prompt += f"""文件内容:\n"""
            prompt += f"<FILE_CONTENT_START>\n"
            prompt += f'{file["file_content"]}\n'
            prompt += f"<FILE_CONTENT_END>\n"
        
        prompt += f"\n需求描述: {feature}\n"
        prompt += """
注意事项：
1、仅输出补丁内容，不要输出任何其他内容，每个补丁必须用<PATCH_START>和<PATCH_END>标记
2、如果在大段代码中有零星修改，生成多个补丁
"""
        
        success, response = self._call_model_with_retry(self.main_model, prompt)
        if not success:
            return []
            
        try:
            # 使用正则表达式匹配每个patch块
            patches = re.findall(r'<PATCH_START>.*?<PATCH_END>', response, re.DOTALL)
            return [patch.replace('<PATCH_START>', '').replace('<PATCH_END>', '').strip() 
                   for patch in patches if patch.strip()]
        except Exception as e:
            PrettyOutput.print(f"解析patch失败: {str(e)}", OutputType.ERROR)
            return []

    def _apply_patch(self, related_files: List[Dict], patches: List[str]) -> Tuple[bool, str]:
        """应用补丁"""
        error_info = []
        modified_files = set()

        # 创建文件内容映射
        file_map = {file["file_path"]: file["file_content"] for file in related_files}
        temp_map = file_map.copy()  # 创建临时映射用于尝试应用
        
        # 尝试应用所有补丁
        for i, patch in enumerate(patches):
            PrettyOutput.print(f"正在应用补丁 {i+1}/{len(patches)}", OutputType.INFO)
            
            try:
                # 解析补丁
                lines = patch.split("\n")
                if not lines:
                    continue
                    
                # 获取文件路径
                file_path_match = re.search(r'>>>>>> (.*)', lines[0])
                if not file_path_match:
                    error_info.append(f"无法解析文件路径: {lines[0]}")
                    return False, "\n".join(error_info)
                    
                file_path = file_path_match.group(1).strip()
                
                # 解析补丁内容
                patch_content = "\n".join(lines[1:])
                parts = patch_content.split("======")
                
                if len(parts) != 2:
                    error_info.append(f"补丁格式错误: {file_path}")
                    return False, "\n".join(error_info)
                
                old_content = parts[0].strip()
                new_content = parts[1].split("<<<<<<")[0].strip()
                
                # 处理新文件
                if not old_content:
                    temp_map[file_path] = new_content
                    modified_files.add(file_path)
                    continue
                
                # 处理文件修改
                if file_path not in temp_map:
                    error_info.append(f"文件不存在: {file_path}")
                    return False, "\n".join(error_info)
                
                current_content = temp_map[file_path]
                
                # 查找并替换代码块
                if old_content not in current_content:
                    error_info.append(
                        f"补丁应用失败: {file_path}\n"
                        f"原因: 未找到要替换的代码\n"
                        f"期望找到的代码:\n{old_content}\n"
                        f"实际文件内容:\n{current_content[:200]}..."  # 只显示前200个字符
                    )
                    return False, "\n".join(error_info)
                
                # 应用更改
                temp_map[file_path] = current_content.replace(old_content, new_content)
                modified_files.add(file_path)
                
            except Exception as e:
                error_info.append(f"处理补丁时发生错误: {str(e)}")
                return False, "\n".join(error_info)
        
        # 所有补丁都应用成功，更新实际文件
        for file_path in modified_files:
            try:
                dir_path = os.path.dirname(file_path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                    
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(temp_map[file_path])
                    
                PrettyOutput.print(f"成功修改文件: {file_path}", OutputType.SUCCESS)
                
            except Exception as e:
                error_info.append(f"写入文件失败 {file_path}: {str(e)}")
                return False, "\n".join(error_info)
        
        return True, ""

    def _save_edit_record(self, feature: str, patches: List[str]) -> None:
        """保存代码修改记录
        
        Args:
            feature: 需求描述
            patches: 补丁列表
        """
            
        # 获取下一个序号
        existing_records = [f for f in os.listdir(self.record_dir) if f.endswith('.yaml')]
        next_num = 1
        if existing_records:
            last_num = max(int(f[:4]) for f in existing_records)
            next_num = last_num + 1
        
        # 创建记录文件
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "feature": feature,
            "patches": patches
        }
        
        record_path = os.path.join(self.record_dir, f"{next_num:04d}.yaml")
        with open(record_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(record, f, allow_unicode=True)
        
        PrettyOutput.print(f"已保存修改记录: {record_path}", OutputType.SUCCESS)

    def _find_git_root_dir(self, root_dir: str) -> str:
        """查找git根目录"""
        while not os.path.exists(os.path.join(root_dir, ".git")):
            root_dir = os.path.dirname(root_dir)
            if root_dir == "/":
                return None
        return root_dir

    def execute(self, feature: str) -> Dict[str, Any]:
        """执行代码修改

        Args:
            args: 包含操作参数的字典
                - feature: 要实现的功能描述
                - root_dir: 代码库根目录
                - language: 编程语言

        Returns:
            Dict[str, Any]: 包含执行结果的字典
                - success: 是否成功
                - stdout: 标准输出信息
                - stderr: 错误信息
                - error: 错误对象(如果有)
        """
        try:
            self.main_model = self._new_model()  # 每次执行时重新创建模型
            

            # 4. 开始建立代码库索引
            self._index_project()

            # 5. 根据索引和需求，查找相关文件
            related_files = self._find_related_files(feature)
            for file in related_files:
                PrettyOutput.print(f"Related file: {file['file_path']}", OutputType.INFO)
            for file in related_files:
                with open(file["file_path"], "r", encoding="utf-8") as f:
                    file_content = f.read()
                    file["file_content"] = file_content
            patches = self._make_patch(related_files, feature)
            while True:
                # 生成修改方案
                PrettyOutput.print(f"生成{len(patches)}个补丁", OutputType.INFO)
                
                if not patches:
                    retry_prompt = f"""未生成补丁，请重新生成补丁"""
                    patches = self._remake_patch(retry_prompt)
                    continue
                
                # 尝试应用补丁
                success, error_info = self._apply_patch(related_files, patches)
                
                if success:
                    # 用户确认修改
                    user_confirm = input("是否确认修改？(y/n)")
                    if user_confirm.lower() == "y":
                        PrettyOutput.print("修改确认成功，提交修改", OutputType.INFO)
                        
                        os.system(f"git add .")
                        os.system(f"git commit -m '{feature}'")
                        
                        # 保存修改记录
                        self._save_edit_record(feature, patches)
                        # 重新建立代码库索引
                        self._index_project()
                        
                        return {
                            "success": True,
                            "stdout": f"已完成功能开发{feature}",
                            "stderr": "",
                            "error": None
                        }
                    else:
                        PrettyOutput.print("修改已取消，回退更改", OutputType.INFO)
                        
                        os.system(f"git reset --hard")  # 回退已修改的文件
                        os.system(f"git clean -df")     # 删除新创建的文件和目录
                        
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "修改被用户取消，文件未发生任何变化",
                            "error": UserWarning("用户取消修改")
                        }
                else:
                    # 补丁应用失败，让模型重新生成
                    PrettyOutput.print(f"补丁应用失败，请求重新生成: {error_info}", OutputType.WARNING)
                    retry_prompt = f"""补丁应用失败，请根据以下错误信息重新生成补丁：

错误信息：
{error_info}

请确保：
1. 准确定位要修改的代码位置
2. 正确处理代码缩进
3. 考虑代码上下文
4. 对新文件不要包含原始内容
"""
                    patches = self._remake_patch(retry_prompt)
                    continue
                
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行失败: {str(e)}",
                "error": e
            }


def main():
    """命令行入口"""
    import argparse

    load_env_from_file()
    
    parser = argparse.ArgumentParser(description='代码修改工具')
    parser.add_argument('-p', '--platform', help='AI平台名称', default=os.environ.get('JARVIS_CODEGEN_PLATFORM'))
    parser.add_argument('-m', '--model', help='模型名称', default=os.environ.get('JARVIS_CODEGEN_MODEL'))
    parser.add_argument('-d', '--dir', help='项目根目录', default=os.getcwd())
    parser.add_argument('-l', '--language', help='编程语言', default="python")
    args = parser.parse_args()
    
    # 设置平台
    if not args.platform:
        print("错误: 未指定AI平台，请使用 -p 参数")
    # 设置模型
    if args.model:
        os.environ['JARVIS_CODEGEN_MODEL'] = args.model
        
    tool = JarvisCoder(args.dir, args.language)
    
    # 循环处理需求
    while True:
        try:
            # 获取需求
            feature = get_multiline_input("请输入开发需求 (输入空行退出):")
            
            if not feature or feature == "__interrupt__":
                break
                
            # 执行修改
            result = tool.execute(feature)
            
            # 显示结果
            if result["success"]:
                PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
            else:
                if result["stderr"]:
                    PrettyOutput.print(result["stderr"], OutputType.ERROR)
                if result["error"]:
                    PrettyOutput.print(f"错误类型: {type(result['error']).__name__}", OutputType.ERROR)
                
        except KeyboardInterrupt:
            print("\n用户中断执行")
            break
        except Exception as e:
            PrettyOutput.print(f"执行出错: {str(e)}", OutputType.ERROR)
            continue
            
    return 0

if __name__ == "__main__":
    exit(main())
