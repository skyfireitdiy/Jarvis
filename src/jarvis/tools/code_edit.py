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


class CodeEditTool:
    """代码修改工具"""

    name = "code_edit"
    description = "根据需求描述修改代码文件"
    parameters = {
        "type": "object",
        "properties": {
            "feature": {
                "type": "string",
                "description": "要实现的功能描述"
            },
            "root_dir": {
                "type": "string",
                "description": "代码库根目录"
            },
            "language": {
                "type": "string",
                "description": "编程语言"
            }
        },
        "required": ["feature", "root_dir", "language"]
    }

    def __init__(self):
        """初始化代码修改工具"""
        self.main_model = self._new_model()
        self.language_extensions = {
            "c": {".c", ".h"},
            "cpp": {".cpp", ".hpp", ".h"},
            "python": {".py", ".pyw"},
            "java": {".java"},
            "go": {".go"},
            "rust": {".rs"},
            "javascript": {".js"},
            "typescript": {".ts"},
            "php": {".php"},
            "ruby": {".rb"},
            "swift": {".swift"},
            "kotlin": {".kt"},
            "scala": {".scala"},
            "haskell": {".hs"},
            "erlang": {".erl"},
            "elixir": {".ex"},
        }
        self.db_path = ""
        self.feature = ""
        self.root_dir = ""
        self.language = ""
        self.current_dir = ""

    def _new_model(self):
        """获取大模型"""
        platform_name = os.environ.get(
            "JARVIS_CODEGEN_PLATFORM", PlatformRegistry.global_platform_name)
        model_name = os.environ.get("JARVIS_CODEGEN_MODEL")
        model = PlatformRegistry().get_global_platform_registry().create_platform(platform_name)
        if model_name:
            model.set_model_name(model_name)
        return model

    def _has_uncommitted_files(self, root_dir: str) -> bool:
        """判断代码库是否有未提交的文件"""
        os.chdir(root_dir)
        return os.system(f"git status | grep 'Changes not staged for commit'")

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
3. 关键信息: 请生成文件的功能描述，使用标准的yaml格式描述，仅输出以下格式内容，如果目标文件不是代码文件，输出（无）
<FILE_INFO_START>
file_description: 这个文件的主要功能和作用描述
<FILE_INFO_END>
"""
        try:
            response = model.chat(prompt)
            model.delete_chat()  # 删除会话历史
            
            response = response.replace("<FILE_INFO_START>", "").replace("<FILE_INFO_END>", "")
            return yaml.safe_load(response)
        except Exception as e:
            PrettyOutput.print(f"解析文件信息失败: {str(e)}", OutputType.ERROR)
            return None
        finally:
            # 确保清理模型资源
            try:
                model.delete_chat()
            except:
                pass

    def _get_file_extensions(self, language: str) -> List[str]:
        """获取文件扩展名"""
        return self.language_extensions.get(language, [])

    def _get_file_md5(self, file_path: str) -> str:
        """获取文件MD5"""
        return hashlib.md5(open(file_path, "rb").read()).hexdigest()

    def _create_index_db(self):
        """创建索引数据库"""
        index_db_path = os.path.join(self.root_dir, ".index.db")
        if not os.path.exists(index_db_path):
            PrettyOutput.print("Index database does not exist, creating...", OutputType.INFO)
            index_db = sqlite3.connect(index_db_path)
            index_db.execute(
                "CREATE TABLE files (file_path TEXT PRIMARY KEY, file_md5 TEXT, file_description TEXT)")
            index_db.commit()
            index_db.close()
            PrettyOutput.print("Index database created", OutputType.SUCCESS)
            # 将.index.db文件添加到gitignore
            with open(os.path.join(self.root_dir, ".gitignore"), "a") as f:
                f.write("\n.index.db\n")
            PrettyOutput.print("Index database added to gitignore", OutputType.SUCCESS)
            # commit
            os.chdir(self.root_dir)
            os.system(f"git add .gitignore -f")
            os.system(f"git commit -m 'add index database'")
            os.chdir(self.current_dir)

    def _find_file_by_md5(self, index_db_path: str, file_md5: str) -> Optional[str]:
        """根据文件MD5查找文件路径"""
        index_db = sqlite3.connect(index_db_path)
        cursor = index_db.cursor()
        cursor.execute(
            "SELECT file_path FROM files WHERE file_md5 = ?", (file_md5,))
        result = cursor.fetchone()
        index_db.close()
        return result[0] if result else None

    def _update_file_path(self, index_db_path: str, file_path: str, file_md5: str):
        """更新文件路径"""
        index_db = sqlite3.connect(index_db_path)
        cursor = index_db.cursor()
        cursor.execute(
            "UPDATE files SET file_path = ? WHERE file_md5 = ?", (file_path, file_md5))
        index_db.commit()
        index_db.close()

    def _insert_info(self, index_db_path: str, file_path: str, file_md5: str, file_description: str):
        """插入文件信息"""
        index_db = sqlite3.connect(index_db_path)
        cursor = index_db.cursor()
        cursor.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
        cursor.execute("INSERT INTO files (file_path, file_md5, file_description) VALUES (?, ?, ?)",
                       (file_path, file_md5, file_description))
        index_db.commit()
        index_db.close()

    def _index_project(self, language: str):
        """建立代码库索引"""
        # 1. 创建索引数据库，位于root_dir/.index.db
        index_db_path = os.path.join(self.root_dir, ".index.db")
        self.db_path = index_db_path
        if not os.path.exists(index_db_path):
            self._create_index_db()

        # 2. 使用git ls-files获取文件列表
        os.chdir(self.root_dir)
        git_files = os.popen("git ls-files").read().splitlines()
        os.chdir(self.current_dir)

        # 2.1 删除数据库中不存在的文件记录
        index_db = sqlite3.connect(index_db_path)
        cursor = index_db.cursor()
        cursor.execute("SELECT file_path FROM files")
        db_files = [row[0] for row in cursor.fetchall()]
        for db_file in db_files:
            if not os.path.exists(db_file):
                cursor.execute("DELETE FROM files WHERE file_path = ?", (db_file,))
                PrettyOutput.print(f"删除不存在的文件记录: {db_file}", OutputType.INFO)
        index_db.commit()
        index_db.close()

        # 3. 遍历git管理的文件
        for file_path in git_files:
            if os.path.splitext(file_path)[1] in self._get_file_extensions(language):
                # 计算文件MD5
                file_md5 = self._get_file_md5(file_path)

                # 查找文件
                file_path_in_db = self._find_file_by_md5(self.db_path, file_md5)
                if file_path_in_db:
                    PrettyOutput.print(
                        f"File {file_path} is duplicate, skip", OutputType.INFO)
                    if file_path_in_db != file_path:
                        self._update_file_path(self.db_path, file_path, file_md5)
                        PrettyOutput.print(
                            f"File {file_path} is duplicate, update path to {file_path}", OutputType.INFO)
                    continue

                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                    key_info = self._get_key_info(file_path, file_content)
                    if not key_info:
                        PrettyOutput.print(
                            f"File {file_path} index failed", OutputType.INFO)
                        continue
                    if "file_description" in key_info:
                        self._insert_info(
                            self.db_path, file_path, file_md5, key_info["file_description"])
                        PrettyOutput.print(
                            f"File {file_path} is indexed", OutputType.INFO)
                    else:
                        PrettyOutput.print(
                            f"File {file_path} is not a code file, skip", OutputType.INFO)
        PrettyOutput.print("Index project finished", OutputType.INFO)

    def _find_related_files(self, feature: str) -> List[Dict]:
        """根据需求描述，查找相关文件"""
        try:
            # Get all files from database
            index_db = sqlite3.connect(self.db_path)
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
            
            prompt = "你是资深程序员，请根据需求描述，从以下文件路径中选出最相关的文件，按相关度从高到低排序，输出yaml格式，仅输出以下格式内容：\n"
            prompt += "<RELEVANT_FILES_START>\n"
            prompt += "file1.py: 9\n"
            prompt += "file2.py: 7\n"
            prompt += "<RELEVANT_FILES_END>\n\n"
            prompt += "文件列表：\n"
            for file_path, _ in batch_files:
                prompt += f"- {file_path}\n"
            prompt += f"\n需求描述: {feature}\n"
            prompt += "\n注意：\n1. 只输出最相关的文件，不超过5个\n2. 根据文件路径名判断相关性\n3. 相关度必须是0-9的整数"
            
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
        
        prompt = "你是资深程序员，请根据需求描述，分析文件的相关性，文件列表如下：\n"
        prompt += "<FILE_LIST_START>\n"
        for i, file in enumerate(top_files):
            prompt += f"""{i}. {file["file_path"]} : {file["file_description"]}\n"""
        prompt += f"""需求描述: {feature}\n"""
        prompt += "<FILE_LIST_END>\n"
        prompt += "请根据需求描述和文件描述，分析文件的相关性，输出每个编号的相关性[0~9]，仅输出以下格式内容(key为文件编号，value为相关性)\n"
        prompt += "<FILE_RELATION_START>\n"
        prompt += '''"0": 5\n'''
        prompt += '''"1": 3\n'''
        prompt += "<FILE_RELATION_END>\n"
        
        success, response = self._call_model_with_retry(self._new_model(), prompt)
        if not success:
            return top_files[:3]  # Return top 3 files from filename matching if model fails
        
        try:
            response = response.replace("<FILE_RELATION_START>", "").replace("<FILE_RELATION_END>", "")
            file_relation = yaml.safe_load(response)
            if not file_relation:
                return top_files[:3]
            
            for file_id, relation in file_relation.items():
                id = int(file_id)
                relation = max(0, min(9, relation))  # 确保范围在0-9之间
                score[relation].append(top_files[id])
            
        except Exception as e:
            PrettyOutput.print(f"处理文件关系失败: {str(e)}", OutputType.ERROR)
            return top_files[:3]
        
        files = []
        score.reverse()
        for i in score:
            files.extend(i)
            if len(files) >= 3:  # 直接取相关性最高的3个文件
                break
        
        return files[:3]
    
    def _remake_patch(self, prompt: str) -> List[str]:
        success, response = self._call_model_with_retry(self.main_model, prompt, max_retries=5)  # 增加重试次数
        if not success:
            return []
            
        try:
            patches = re.findall(r">>>>>>.*?<<<<<<", response, re.DOTALL)
            return patches
        except Exception as e:
            PrettyOutput.print(f"解析patch失败: {str(e)}", OutputType.ERROR)
            return []
        
    def _make_patch(self, related_files: List[Dict]) -> List[str]:
        """生成修改方案"""
        prompt = "你是一个资深程序员，请根据需求描述，修改文件内容，文件列表如下：\n"
        prompt += "<FILE_RELATION_START>\n"
        for i, file in enumerate(related_files):
            prompt += f"""{i}. {file["file_path"]} : {file["file_description"]}\n"""
            prompt += f"""文件内容: \n"""
            prompt += f"<FILE_CONTENT_START>\n"
            prompt += f'{file["file_content"]}\n'
            prompt += f"<FILE_CONTENT_END>\n"
        prompt += f"<FILE_RELATION_END>\n"
        prompt += f"请根据需求描述，修改文件。\n"
        prompt += f"需求描述: {self.feature}\n"
        prompt += f"请输出以下格式内容（多段patch），注意缩进也是代码的一部分，不要输出任何其他内容\n"
        prompt += f">>>>>> [文件路径1]\n"
        prompt += f"[原文件内容]\n"
        prompt += f"==========\n"
        prompt += f"[修改后的文件内容]\n"
        prompt += f"<<<<<<\n"
        prompt += f"如果文件不存在，请创建新文件，不要包含原始内容，如下：\n"
        prompt += f">>>>>> [文件路径1]\n"
        prompt += f"==========\n"
        prompt += f"[新文件内容]\n"
        prompt += f"<<<<<<\n"
        prompt += f"生成最小化的patch，原文件内容与修改后文件内容不要有大量重复内容。"
        prompt += f"如果一个文件有多处需要修改，请生成多个patch，不要生成一个patch包含多处修改。"
        
        success, response = self._call_model_with_retry(self.main_model, prompt, max_retries=5)  # 增加重试次数
        if not success:
            return []
            
        try:
            patches = re.findall(r">>>>>>.*?<<<<<<", response, re.DOTALL)
            return patches
        except Exception as e:
            PrettyOutput.print(f"解析patch失败: {str(e)}", OutputType.ERROR)
            return []

    def _apply_patch(self, related_files: List[Dict], patches: List[str]) -> Tuple[bool, str]:
        """应用补丁
        
        Args:
            related_files: 相关文件列表
            patches: 补丁列表
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        # 创建文件内容映射
        file_map = {file["file_path"]: file["file_content"] for file in related_files}
        temp_map = file_map.copy()  # 创建临时映射用于尝试应用
        
        error_info = []

        modified_files = set()  # 记录修改的文件
        
        # 尝试应用所有补丁
        for i, patch in enumerate(patches):
            PrettyOutput.print(f"正在应用补丁 {i+1}/{len(patches)}", OutputType.INFO)
            patch_lines = patch.split("\n")
            file_name = ""
            old_code = []
            new_code = []
            old_code_flag = False
            new_code_flag = False
            
            # 解析补丁内容
            for line in patch_lines:
                if line.startswith(">>>>>>"):
                    old_code_flag = True
                    file_name = line.split(" ")[1]
                elif line.startswith("=========="):
                    old_code_flag = False
                    new_code_flag = True
                elif line.startswith("<<<<<<"):
                    new_code_flag = False
                elif old_code_flag:
                    old_code.append(line)
                elif new_code_flag:
                    new_code.append(line)
                
            # 处理新文件的情况
            if file_name not in temp_map:
                PrettyOutput.print(f"创建新文件: {file_name}", OutputType.WARNING)
                if old_code:  # 如果是新文件但有原始内容，这是错误的
                    error_info.append(f"文件 {file_name} 不存在，但补丁包含原始内容")
                    return False, "\n".join(error_info)
                
                temp_map[file_name] = "\n".join(new_code)
                modified_files.add(file_name)  # 记录新文件
                continue
            
            # 应用补丁到现有文件
            old_content = "\n".join(old_code)
            new_content = "\n".join(new_code)
            
            if old_content not in temp_map[file_name]:
                error_info.append(
                    f"补丁应用失败: {file_name}\n"
                    f"原因: 未找到要替换的代码\n"
                    f"期望找到的代码:\n{old_content}\n"
                    f"实际文件内容:\n{temp_map[file_name][:200]}..."  # 只显示前200个字符
                )
                return False, "\n".join(error_info)
            
            # 应用更改到临时映射
            temp_map[file_name] = temp_map[file_name].replace(old_content, new_content)
            modified_files.add(file_name)  # 记录修改的文件
            
        # 所有补丁都应用成功，更新实际文件
        for file_path in modified_files:
            try:
                dir = os.path.dirname(file_path)
                if dir and not os.path.exists(dir):
                    os.makedirs(dir, exist_ok=True)
                PrettyOutput.print(f"更新文件: {file_path}", OutputType.INFO)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(temp_map[file_path])
                os.system(f"git add {file_path} -f")  # 立即加入暂存区
                PrettyOutput.print(f"成功更新文件: {file_path}", OutputType.SUCCESS)
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
        # 创建记录目录
        record_dir = os.path.join(self.root_dir, ".jarvis_code_edit")
        os.makedirs(record_dir, exist_ok=True)
        
        # 添加到 .gitignore
        gitignore_path = os.path.join(self.root_dir, ".gitignore")
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r") as f:
                if ".jarvis_code_edit" not in f.read():
                    with open(gitignore_path, "a") as f:
                        f.write("\n.jarvis_code_edit/\n")
        else:
            with open(gitignore_path, "w") as f:
                f.write(".jarvis_code_edit/\n")
            
        # 获取下一个序号
        existing_records = [f for f in os.listdir(record_dir) if f.endswith('.yaml')]
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
        
        record_path = os.path.join(record_dir, f"{next_num:04d}.yaml")
        with open(record_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(record, f, allow_unicode=True)
        
        PrettyOutput.print(f"已保存修改记录: {record_path}", OutputType.SUCCESS)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
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
            self.feature = args["feature"]
            self.root_dir = args["root_dir"]
            self.language = args["language"]
            self.current_dir = os.getcwd()

            # 0. 判断语言是否支持
            if not self._get_file_extensions(self.language):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "不支持的编程语言",
                    "error": ValueError("不支持的编程语言")
                }

            # 1. 判断代码库路径是否存在，如果不存在，创建
            if not os.path.exists(self.root_dir):
                PrettyOutput.print(
                    "Root directory does not exist, creating...", OutputType.INFO)
                os.makedirs(self.root_dir)

            # 2. 判断代码库是否是git仓库，如果不是，初始化git仓库
            if not os.path.exists(os.path.join(self.root_dir, ".git")):
                PrettyOutput.print(
                    "Git repository does not exist, initializing...", OutputType.INFO)
                os.chdir(self.root_dir)
                os.system(f"git init")
                # 2.1 添加所有的文件
                os.system(f"git add .")
                # 2.2 提交
                os.system(f"git commit -m 'Initial commit'")
                os.chdir(self.current_dir)

            # 3. 查看代码库是否有未提交的文件，如果有，提交一次
            if self._has_uncommitted_files(self.root_dir):
                os.chdir(self.root_dir)
                os.system(f"git add .")
                os.system(f"git commit -m 'commit before code edit'")
                os.chdir(self.current_dir)

            # 4. 开始建立代码库索引
            os.chdir(self.root_dir)
            self._index_project(self.language)
            os.chdir(self.current_dir)

            # 5. 根据索引和需求，查找相关文件
            related_files = self._find_related_files(self.feature)
            for file in related_files:
                PrettyOutput.print(f"Related file: {file['file_path']}", OutputType.INFO)
            for file in related_files:
                with open(file["file_path"], "r", encoding="utf-8") as f:
                    file_content = f.read()
                    file["file_content"] = file_content
            patches = self._make_patch(related_files)
            while True:
                # 生成修改方案
                PrettyOutput.print(f"生成{len(patches)}个补丁", OutputType.INFO)
                
                if not patches:
                    self._save_edit_record(self.feature, patches)
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "未生成补丁",
                        "error": ValueError("未生成补丁")
                    }
                
                # 尝试应用补丁
                success, error_info = self._apply_patch(related_files, patches)
                
                if success:
                    # 用户确认修改
                    user_confirm = input("是否确认修改？(y/n)")
                    if user_confirm.lower() == "y":
                        PrettyOutput.print("修改确认成功，提交修改", OutputType.INFO)
                        os.chdir(self.root_dir)
                        os.system(f"git add .")
                        os.system(f"git commit -m '{self.feature}'")
                        os.chdir(self.current_dir)
                        # 保存修改记录
                        self._save_edit_record(self.feature, patches)
                        # 重新建立代码库索引
                        self._index_project(self.language)
                        
                        return {
                            "success": True,
                            "stdout": f"已完成功能开发{self.feature}",
                            "stderr": "",
                            "error": None
                        }
                    else:
                        PrettyOutput.print("修改已取消，回退更改", OutputType.INFO)
                        os.chdir(self.root_dir)
                        os.system(f"git reset --hard")  # 回退已修改的文件
                        os.system(f"git clean -df")     # 删除新创建的文件和目录
                        os.chdir(self.current_dir)
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
    parser.add_argument('-p', '--platform', help='AI平台名称', default=os.environ.get('JARVIS_PLATFORM'))
    parser.add_argument('-m', '--model', help='模型名称', default=os.environ.get('JARVIS_CODEGEN_MODEL'))
    parser.add_argument('-d', '--dir', help='项目根目录', required=True)
    parser.add_argument('-l', '--language', help='编程语言', required=True)
    args = parser.parse_args()
    
    # 设置平台
    if not args.platform:
        print("错误: 未指定AI平台，请使用 -p 参数或设置 JARVIS_PLATFORM 环境变量")
        return 1
        
    PlatformRegistry.get_global_platform_registry().set_global_platform_name(args.platform)
    
    # 设置模型
    if args.model:
        os.environ['JARVIS_CODEGEN_MODEL'] = args.model
        
    tool = CodeEditTool()
    
    # 循环处理需求
    while True:
        try:
            # 获取需求
            feature = get_multiline_input("请输入开发需求 (输入空行退出):")
            
            if not feature or feature == "__interrupt__":
                break
                
            # 执行修改
            result = tool.execute({
                "feature": feature,
                "root_dir": args.dir,
                "language": args.language
            })
            
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
