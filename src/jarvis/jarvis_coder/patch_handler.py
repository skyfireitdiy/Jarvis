import re
import os
from typing import List, Tuple, Dict
import yaml
from pathlib import Path

from jarvis.jarvis_coder.git_utils import generate_commit_message, init_git_repo, save_edit_record
from jarvis.models.base import BasePlatform
from jarvis.models.registry import PlatformRegistry
from jarvis.utils import OutputType, PrettyOutput, get_multiline_input, get_single_line_input, while_success

class Patch:
    def __init__(self, old_code: str, new_code: str):
        self.old_code = old_code
        self.new_code = new_code

class PatchHandler:
    def __init__(self):
        self.prompt_file = Path.home() / ".jarvis-coder-patch-prompt"
        self.additional_info = self._load_additional_info()
        self.root_dir = init_git_repo(os.getcwd())
        self.record_dir = os.path.join(self.root_dir, ".jarvis-coder", "record")
        if not os.path.exists(self.record_dir):
            os.makedirs(self.record_dir)
    def _load_additional_info(self) -> str:
        """Load saved additional info from prompt file"""
        if not self.prompt_file.exists():
            return ""
        try:
            with open(self.prompt_file, 'r') as f:
                data = yaml.safe_load(f)
                return data.get('additional_info', '') if data else ''
        except Exception as e:
            PrettyOutput.print(f"Failed to load additional info: {e}", OutputType.WARNING)
            return ""

    def _save_additional_info(self, info: str):
        """Save additional info to prompt file"""
        try:
            with open(self.prompt_file, 'w') as f:
                yaml.dump({'additional_info': info}, f)
        except Exception as e:
            PrettyOutput.print(f"Failed to save additional info: {e}", OutputType.WARNING)

    def _extract_patches(self, response: str) -> List[Patch]:
        """Extract patches from response
        
        Args:
            response: Model response content
            
        Returns:
            List[Tuple[str, str, str]]: Patch list, each patch is a tuple of (format, file path, patch content)
        """
        # 修改后的正则表达式匹配三种补丁格式
        fmt_pattern = r'<PATCH>\n>>>>>> SEARCH\n(.*?)\n?(={5,})\n(.*?)\n?<<<<<< REPLACE\n</PATCH>'
        ret = []
        for m in re.finditer(fmt_pattern, response, re.DOTALL):
            ret.append(Patch(m.group(1), m.group(3)))   
        return ret


    def _confirm_and_apply_changes(self, file_path: str) -> bool:
        """Confirm and apply changes"""
        os.system(f"git diff --cached {file_path}")
        confirm = get_single_line_input(f"Accept {file_path} changes? (y/n) [y]").lower() or "y"
        if confirm == "y":
            return True
        else:
            # Rollback changes
            os.system(f"git reset {file_path}")
            os.system(f"git checkout -- {file_path}")
            PrettyOutput.print(f"Changes to {file_path} have been rolled back", OutputType.WARNING)
            return False
        
    

    def _finalize_changes(self) -> None:
        """Complete changes and commit"""
        PrettyOutput.print("Modification confirmed, committing...", OutputType.INFO)

        # Add only modified files under git control
        os.system("git add -u")
        
        # Then get git diff
        git_diff = os.popen("git diff --cached").read()
        
        # Automatically generate commit information, pass in feature
        commit_message = generate_commit_message(git_diff)
        
        # Display and confirm commit information
        PrettyOutput.print(f"Automatically generated commit information: {commit_message}", OutputType.INFO)
        user_confirm = get_single_line_input("Use this commit information? (y/n) [y]").lower() or "y"
        
        if user_confirm.lower() != "y":
            commit_message = get_single_line_input("Please enter a new commit information")
        
        # No need to git add again, it has already been added
        os.system(f"git commit -m '{commit_message}'")
        save_edit_record(self.record_dir, commit_message, git_diff)

    def _revert_changes(self) -> None:
        """Revert all changes"""
        PrettyOutput.print("Modification cancelled, reverting changes", OutputType.INFO)
        os.system(f"git reset --hard")
        os.system(f"git clean -df")

    
    def apply_file_patch(self, file_path: str, patches: List[Patch]) -> bool:
        """Apply file patch"""
        if not os.path.exists(file_path):
            base_dir = os.path.dirname(file_path)
            os.makedirs(base_dir, exist_ok=True)
            open(file_path, "w", encoding="utf-8").close()
        file_content = open(file_path, "r", encoding="utf-8").read()
        for i, patch in enumerate(patches):
            if patch.old_code == "" and patch.new_code == "":
                PrettyOutput.print(f"Apply patch {i+1}/{len(patches)}: Delete file {file_path}", OutputType.INFO)
                file_content = ""
                os.system(f"git rm {file_path}")
                PrettyOutput.print(f"Apply patch {i+1}/{len(patches)} successfully", OutputType.SUCCESS)
            elif patch.old_code == "":
                PrettyOutput.print(f"Apply patch {i+1}/{len(patches)}: Replace file {file_path} content: \n{patch.new_code}", OutputType.INFO)
                file_content = patch.new_code
                open(file_path, "w", encoding="utf-8").write(patch.new_code)
                os.system(f"git add {file_path}")
                PrettyOutput.print(f"Apply patch {i+1}/{len(patches)} successfully", OutputType.SUCCESS)
            else:
                PrettyOutput.print(f"Apply patch {i+1}/{len(patches)}: File original content: \n{patch.old_code}\nReplace with: \n{patch.new_code}", OutputType.INFO)
                if file_content.find(patch.old_code) == -1:
                    PrettyOutput.print(f"File {file_path} does not contain {patch.old_code}", OutputType.WARNING)
                    os.system(f"git reset {file_path}")
                    os.system(f"git checkout -- {file_path}")
                    return False
                else:
                    file_content = file_content.replace(patch.old_code, patch.new_code, 1)
                    open(file_path, "w", encoding="utf-8").write(file_content)
                    os.system(f"git add {file_path}")
                    PrettyOutput.print(f"Apply patch {i+1}/{len(patches)} successfully", OutputType.SUCCESS)
        return True
            
    
    def retry_comfirm(self) -> Tuple[str, str]:
        choice = get_single_line_input("\nPlease choose an action: (1) Retry (2) Skip (3) Completely stop [1]: ") or "1"
        if choice == "2":
            return "skip", ""
        if choice == "3":
            return "break", ""
            
        feedback = get_multiline_input("Please enter additional information and requirements:")
        if feedback:
            save_prompt = get_single_line_input("Would you like to save this as general feedback for future patches? (y/n) [n]: ").lower() or "n"
            if save_prompt == "y":
                self._save_additional_info(feedback)
                PrettyOutput.print("Feedback saved for future use", OutputType.SUCCESS)
            
        return "continue", feedback

    def apply_patch(self, feature: str, structed_plan: Dict[str, str]) -> Tuple[bool, str]:
        """Apply patch (main entry)"""
        for file_path, current_plan in structed_plan.items():
            additional_info = self.additional_info  # Initialize with saved info
            while True:
                
                if os.path.exists(file_path):
                    content = open(file_path, "r", encoding="utf-8").read()
                else:
                    content = "<File does not exist, need to create>"
                prompt = """You are a senior software development expert who can generate code patches based on the complete modification plan, current original code file path, code content, and current file's modification plan. The output format should be as follows:
                        <PATCH>
                        >>>>>> SEARCH
                        old_code
                        ======
                        new_code
                        <<<<<< REPLACE
                        </PATCH>
                        Rules:
                        1. When old_code is empty, it means replace everything from start to end
                        2. When new_code is empty, it means delete old_code
                        3. When both old_code and new_code are empty, it means delete the file
                        Notes:
                        1. Multiple patches can be generated
                        2. old_code will be replaced with new_code, pay attention to context continuity
                        3. Avoid breaking existing code logic when generating patches, e.g., don't insert function definitions inside existing function bodies
                        4. Include sufficient context to avoid ambiguity
                        5. Patches will be merged using file_content.replace(patch.old_code, patch.new_code, 1), so old_code and new_code need to match exactly, including EMPTY LINES, LINE BREAKS, WHITESPACE, TABS, and COMMENTS
                        6. Ensure generated code has correct format (syntax, indentation, line breaks)
                        7. Ensure new_code's indentation and format matches old_code
                        8. Ensure code is inserted in appropriate locations, e.g., code using variables should be after declarations/definitions
                        9. Provide at least 3 lines of context before and after modified code for location
                        10. Each patch should be no more than 20 lines of code, if it is more than 20 lines, split it into multiple patches
                        11. old code's line breaks should be consistent with the original code


                        """
                prompt += f"""# Original requirement: {feature}
                    # Current file path: {file_path}
                    # Current file content:
                    <CONTENT>
                    {content}
                    </CONTENT>
                    # Current file modification plan:
                    {current_plan}
                    { "# Additional information: " + additional_info if additional_info else "" }
                    """


                PrettyOutput.print(f"Generating formatted patches for {file_path}...", OutputType.PROGRESS)
                response = PlatformRegistry.get_global_platform_registry().get_codegen_platform().chat_until_success(prompt)
                patches = self._extract_patches(response)

                if not patches or not self.apply_file_patch(file_path, patches) or not self._confirm_and_apply_changes(file_path):
                    os.system(f"git reset {file_path}")
                    os.system(f"git checkout -- {file_path}")
                    PrettyOutput.print("Patch generation failed", OutputType.WARNING)
                    act, msg = self.retry_comfirm()
                    if act == "break":
                        PrettyOutput.print("Terminate patch application", OutputType.WARNING)
                        additional_info = get_multiline_input("Please enter your additional information or suggestions (press Enter to cancel):")
                        return False, additional_info
                    if act == "skip":
                        PrettyOutput.print(f"Skip file {file_path}", OutputType.WARNING)
                        break
                    else:
                        additional_info += msg + "\n"
                        continue
                else:
                    self._finalize_changes()
                    break
        
        return True, ""



    def handle_patch_application(self, feature: str, structed_plan: Dict[str,str]) -> Tuple[bool, str]:
        """Process patch application process
        
        Args:
            related_files: Related files list
            feature: Feature description
            modification_plan: Modification plan
            
        Returns:
            bool: Whether patch application is successful
        """
        PrettyOutput.print("\nThe following modification plan will be applied:", OutputType.INFO)
        for file_path, patches_code in structed_plan.items():
            PrettyOutput.print(f"\nFile: {file_path}", OutputType.INFO)
            PrettyOutput.print(f"Modification plan: \n{patches_code}", OutputType.INFO)
        # 3. Apply patches
        success, additional_info = self.apply_patch(feature, structed_plan)
        if not success:
            os.system("git reset --hard")
            return False, additional_info
        # 6. Apply successfully, let user confirm changes
        PrettyOutput.print("\nPatches applied, please check the modification effect.", OutputType.SUCCESS)
        return True, "Modification applied successfully"
