import hashlib
import os
import re
import sqlite3
from typing import Dict, Any, List, Optional

import yaml
from jarvis.utils import OutputType, PrettyOutput
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
        platform_name = os.environ.get("JARVIS_CODEGEN_PLATFORM", PlatformRegistry.global_platform_name)
        model_name = os.environ.get("JARVIS_CODEGEN_MODEL") 
        model = PlatformRegistry().get_global_platform_registry().create_platform(platform_name)
        if model_name:
            model.set_model_name(model_name)
        return model

    def _has_uncommitted_files(self, root_dir: str) -> bool:
        """判断代码库是否有未提交的文件"""
        os.chdir(root_dir)
        return os.system(f"git status | grep 'Changes not staged for commit'")
    
    def _get_key_info(self, file_path: str, content: str) -> Dict[str, Any]:
        """获取文件的关键信息"""
        model = self._new_model()
        prompt = f"""你是一个资深程序员，请根据文件内容，生成文件的关键信息，要求如下，除了代码，不要输出任何内容：

1. 文件路径: {file_path}
2. 文件内容:(<CONTENT_START>和<CONTENT_END>之间的部分) 
<CONTENT_START>
{content}
<CONTENT_END>
3. 关键信息: 请生成文件的关键信息，包括文件功能，符号列表（类型、名称、描述），使用标准的yaml格式描述，仅输出以下格式内容，如果目标文件不是代码文件，输出（无）
<FILE_INFO_START>
file_description: xxxx
symbols:
  - name: xxxx
    description: xxxx
    type: xxxx
  - name: yyyy
    description: yyyy
    type: yyyy
<FILE_INFO_END>
"""
        response = model.chat(prompt)
        model.delete_chat()
        response = response.replace("<FILE_INFO_START>", "").replace("<FILE_INFO_END>", "")
        return yaml.safe_load(response)

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
            index_db.execute("CREATE TABLE files (file_path TEXT PRIMARY KEY, file_md5 TEXT, file_description TEXT)")
            index_db.execute("CREATE TABLE symbols (file_path TEXT, symbol_name TEXT, symbol_description TEXT, symbol_type TEXT)")
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
        cursor.execute("SELECT file_path FROM files WHERE file_md5 = ?", (file_md5,))
        result = cursor.fetchone()
        index_db.close()
        return result[0] if result else None
    
    def _update_file_path(self, index_db_path: str, file_path: str, file_md5: str):
        """更新文件路径"""
        index_db = sqlite3.connect(index_db_path)
        cursor = index_db.cursor()
        cursor.execute("UPDATE files SET file_path = ? WHERE file_md5 = ?", (file_path, file_md5))
        index_db.commit()
        index_db.close()

    def _insert_info(self, index_db_path: str, file_path: str, file_md5: str, file_description: str, symbols: List[Dict[str, Any]]):
        """插入文件信息"""
        index_db = sqlite3.connect(index_db_path)
        cursor = index_db.cursor()
        cursor.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
        cursor.execute("INSERT INTO files (file_path, file_md5, file_description) VALUES (?, ?, ?)", (file_path, file_md5, file_description))
        for symbol in symbols:
            cursor.execute("INSERT INTO symbols (file_path, symbol_name, symbol_description, symbol_type) VALUES (?, ?, ?, ?)", (file_path, symbol["name"], symbol["description"], symbol["type"]))
        index_db.commit()
        index_db.close()
    
    def _index_project(self, language: str):
        """建立代码库索引"""
        # 1. 创建索引数据库，位于root_dir/.index.db
        index_db_path = os.path.join(self.root_dir, ".index.db")
        self.db_path = index_db_path
        if not os.path.exists(index_db_path):
            self._create_index_db()
        
        # 2. 遍历文件
        for root, dirs, files in os.walk(self.root_dir):
            for file in files:
                if os.path.splitext(file)[1] in self._get_file_extensions(language):
                    # 计算文件MD5
                    file_path = os.path.join(root, file)
                    file_md5 = self._get_file_md5(file_path)

                    # 查找文件
                    file_path_in_db = self._find_file_by_md5(self.db_path, file_md5)
                    if file_path_in_db:
                        PrettyOutput.print(f"File {file_path} is duplicate, skip", OutputType.INFO)
                        if file_path_in_db != file_path:
                            self._update_file_path(self.db_path, file_path, file_md5)
                            PrettyOutput.print(f"File {file_path} is duplicate, update path to {file_path}", OutputType.INFO)
                        continue

                    with open(file_path, "r", encoding="utf-8") as f:
                        file_content = f.read()
                        key_info = self._get_key_info(file_path, file_content)
                        if not key_info:
                            PrettyOutput.print(f"File {file_path} index failed", OutputType.INFO)
                            continue
                        if "file_description" in key_info and "symbols" in key_info:
                            self._insert_info(self.db_path, file_path, file_md5, key_info["file_description"], key_info["symbols"])
                            PrettyOutput.print(f"File {file_path} is indexed", OutputType.INFO)
                        else:
                            PrettyOutput.print(f"File {file_path} is not a code file, skip", OutputType.INFO)
        PrettyOutput.print("Index project finished", OutputType.INFO)

    def _find_related_files(self, feature: str) -> List[str]:
        """根据需求描述，查找相关文件"""
        model = self._new_model()

        score = [[],[],[],[],[],[],[],[],[],[]]

        step = 50
        offset = 0

        # 每次从数据库中提取50条记录，循环提取，直到提取完所有记录
        while True:
            index_db = sqlite3.connect(self.db_path)
            cursor = index_db.cursor()
            cursor.execute(f"SELECT file_path, file_description FROM files LIMIT {step} OFFSET {offset}")
            result = cursor.fetchall()
            index_db.close()
            if not result:
                break
            offset += len(result)
            prompt = "你是资深程序员，请根据需求描述，分析文件的相关性，文件列表如下：\n"
            prompt += "<FILE_LIST_START>\n"
            # 为文件生成编号，提供的信息有，文件序号，文件名，文件描述，并生成prompt，输出每个编号的相关性[1~10]
            for i, file_path in enumerate(result):
                prompt += f"""{i}. {file_path[0]} : {file_path[1]}\n"""
            prompt += f"""需求描述: {feature}\n"""
            prompt += "<FILE_LIST_END>\n"
            prompt += "请根据需求描述，分析文件的相关性，输出每个编号的相关性[0~9]，仅输出以下格式内容(key为文件编号，value为相关性)\n"
            prompt += "<FILE_RELATION_START>\n"
            prompt += '''"0": 5'''
            prompt += '''"1": 3'''
            prompt += "<FILE_RELATION_END>\n"
            response = model.chat(prompt)
            model.delete_chat()
            response = response.replace("<FILE_RELATION_START>", "").replace("<FILE_RELATION_END>", "")
            file_relation = yaml.safe_load(response)
            if not file_relation:
                PrettyOutput.print("Response format error", OutputType.WARNING)
                continue
            for file_id, relation in file_relation.items():
                id = int(file_id)
                if relation>9:
                    relation = 9
                if relation<0:
                    relation = 0
                score[relation].append({"file_path": result[id][0], "file_description": result[id][1]})
        
        files = []
        score.reverse()
        for i in score:
            files.extend(i)
            if len(files) >= 10:
                break
        return files
        
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
                - changes: 修改内容
                - preview: 修改预览
                - results: 执行结果
        """
        self.feature = args["feature"]
        self.root_dir = args["root_dir"]
        self.language = args["language"]

        self.current_dir = os.getcwd()

        # 0. 判断语言是否支持
        if not self._get_file_extensions(self.language):
            PrettyOutput.print("Language not supported", OutputType.ERROR)
            return {"success": False, "changes": "", "preview": "", "results": ""}

        # 1. 判断代码库路径是否存在，如果不存在，创建
        if not os.path.exists(self.root_dir):
            PrettyOutput.print("Root directory does not exist, creating...", OutputType.INFO)
            os.makedirs(self.root_dir)
        
        # 2. 判断代码库是否是git仓库，如果不是，初始化git仓库
        if not os.path.exists(os.path.join(self.root_dir, ".git")):
            PrettyOutput.print("Git repository does not exist, initializing...", OutputType.INFO)
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
        PrettyOutput.print(f"Related files: {related_files}", OutputType.INFO)
        for file in related_files:
            with open(file["file_path"], "r", encoding="utf-8") as f:
                file_content = f.read()
                file["file_content"] = file_content

        # 6. 根据相关文件，生成修改方案
        patches = self._make_patch(related_files)
        PrettyOutput.print(f"生成{len(patches)}个patch", OutputType.INFO)

        if len(patches) == 0:
            PrettyOutput.print("No patch generated, skip", OutputType.INFO)
            return {"success": False, "changes": "", "preview": "", "results": ""}

        # 7. 应用修改方案
        self._apply_patch(related_files, patches)

        # 8. 用户确认修改
        user_confirm = input("是否确认修改？(y/n)")
        if user_confirm == "y":
            PrettyOutput.print("修改确认成功，提交修改", OutputType.INFO)
            os.chdir(self.root_dir)
            os.system(f"git add .")
            os.system(f"git commit -m '{self.feature}'")
            os.chdir(self.current_dir)
            # 9. 重新建立代码库索引
            self._index_project(self.language)
        else:
            PrettyOutput.print("修改确认失败，取消修改", OutputType.INFO)
            os.chdir(self.root_dir)
            os.system(f"git reset --hard")
            os.chdir(self.current_dir)

    def _apply_patch(self, related_files, patches):
        # patch格式 
        # >>>>>> [文件路径1]
        # [原文件内容]
        # [原文件内容]
        # ==========
        # [修改后的文件内容]
        # [修改后的文件内容]
        # <<<<<<

        file_map = {file["file_path"]: file["file_content"] for file in related_files}

        for i, patch in enumerate(patches):
            PrettyOutput.print(f"Apply patch {i+1} of {len(patches)}", OutputType.INFO)
            patch_line = patch.split("\n")
            file_name = ""
            old_code = []
            new_code = []
            old_code_flag = False
            new_code_flag = False
            for line in patch_line:
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
            if file_name not in file_map:
                PrettyOutput.print(f"File {file_name} not found in related files, create it", OutputType.WARNING)
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write("\n".join(new_code))
            else:
                old_code = "\n".join(old_code)
                new_code = "\n".join(new_code)
                if old_code in file_map[file_name]:
                    file_map[file_name] = file_map[file_name].replace(old_code, new_code)
                    with open(file_name, "w", encoding="utf-8") as f:
                        f.write(file_map[file_name])
                        PrettyOutput.print(f"File {file_name} apply patch success", OutputType.SUCCESS)
                else:
                    PrettyOutput.print(f"File {file_name} apply patch failed", OutputType.ERROR)
                    PrettyOutput.print(f"Old code: \n{old_code}\n", OutputType.INFO)
                    PrettyOutput.print(f"New code: \n{new_code}\n", OutputType.INFO)
        PrettyOutput.print("Apply patch finished", OutputType.INFO)
            

    def _make_patch(self, related_files):
        
        prompt = "你是一个资深程序员，请根据需求描述，修改文件内容，生成最小化的patch，文件列表如下：\n"
        prompt += "<FILE_RELATION_START>\n"
        for i, file in enumerate(related_files):
            prompt += f"""{i}. {file["file_path"]} : {file["file_description"]}\n"""
            prompt += f"""文件内容: \n"""
            prompt += f"<FILE_CONTENT_START>\n"
            prompt += f"{file["file_content"]}\n"
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
        prompt += f">>>>>> [文件路径2]\n"
        prompt += f"[原文件内容]\n"
        prompt += f"==========\n"
        prompt += f"[修改后的文件内容]\n"
        prompt += f"<<<<<<\n"
        response = self.main_model.chat(prompt)
        self.main_model.delete_chat()
        # 使用<FILE_EDIT_START>和<FILE_EDIT_END>提取所有的patch，可能除了patch
        patch = re.findall(r">>>>>>.*?<<<<<<", response, re.DOTALL)
        return patch


if __name__ == "__main__":
    tool = CodeEditTool()
    tool.execute({
        "feature": "将排序数据修改为随机生成",
        "root_dir": "/tmp/test",
        "language": "c"
    })
