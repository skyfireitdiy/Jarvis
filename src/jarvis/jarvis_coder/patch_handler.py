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
    def __init__(self, start: int, end: int, new_code: str):
        self.start = start  # Line number where patch starts (inclusive)
        self.end = end      # Line number where patch ends (exclusive) 
        self.new_code = new_code  # New code to insert/replace

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
        """Extract patches from response with hexadecimal line numbers
        
        Args:
            response: Model response content
            
        Returns:
            List[Patch]: List of patches, each containing the line range and new code
        """
        fmt_pattern = r'<PATCH>\n\[([0-9a-f]+),([0-9a-f]+)\)\n(.*?\n)</PATCH>'
        ret = []
        for m in re.finditer(fmt_pattern, response, re.DOTALL):
            start = int(m.group(1), 16)  # Convert hex to decimal
            end = int(m.group(2), 16)
            new_code = m.group(3)
            ret.append(Patch(start, end, new_code))
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

    def _check_patches_overlap(self, patches: List[Patch]) -> bool:
        """Check if any patches overlap with each other
        
        Args:
            patches: List of patches to check
            
        Returns:
            bool: True if patches overlap, False otherwise
        """
        if not patches:
            return False
        
        # Sort patches by start line
        sorted_patches = sorted(patches, key=lambda x: x.start)
        
        # Check for overlaps
        for i in range(len(sorted_patches) - 1):
            current = sorted_patches[i]
            next_patch = sorted_patches[i + 1]
            
            if current.end > next_patch.start:
                PrettyOutput.print(
                    f"Overlapping patches detected: [{current.start:04x},{current.end:04x}) and [{next_patch.start:04x},{next_patch.end:04x})",
                    OutputType.WARNING
                )
                return True
            
        return False

    def apply_file_patch(self, file_path: str, patches: List[Patch]) -> bool:
        """Apply file patches using line numbers"""
        if not os.path.exists(file_path):
            base_dir = os.path.dirname(file_path)
            os.makedirs(base_dir, exist_ok=True)
            open(file_path, "w", encoding="utf-8").close()
        
        # Check for overlapping patches
        if self._check_patches_overlap(patches):
            PrettyOutput.print("Cannot apply overlapping patches", OutputType.ERROR)
            os.system(f"git reset {file_path}")
            os.system(f"git checkout -- {file_path}")
            return False
        
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Sort patches by start line in reverse order to apply from bottom to top
        patches.sort(key=lambda x: x.start, reverse=True)
        
        for i, patch in enumerate(patches):
            PrettyOutput.print(f"Applying patch {i+1}/{len(patches)} at lines [{patch.start},{patch.end})", OutputType.INFO)
            
            if patch.start > len(lines):
                PrettyOutput.print(f"Invalid patch: start line {patch.start} exceeds file length {len(lines)}", OutputType.WARNING)
                os.system(f"git reset {file_path}")
                os.system(f"git checkout -- {file_path}")
                return False
            
            if patch.new_code:
                new_lines = patch.new_code.splitlines(keepends=True)
                lines[patch.start:patch.end] = new_lines
            else:
                del lines[patch.start:patch.end]
                
        # Write modified content back to file
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        
        os.system(f"git add {file_path}")
        PrettyOutput.print(f"Successfully applied all patches to {file_path}", OutputType.SUCCESS)
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
        feedback = ""
        for file_path, current_plan in structed_plan.items():
            additional_info = self.additional_info  # Initialize with saved info
            while True:
                if os.path.exists(file_path):
                    # Read file and add line numbers
                    lines = []
                    with open(file_path, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            lines.append(f"{i:04x}{line}")  # Changed from i+1 to i for 0-based indexing
                    content = "".join(lines)
                else:
                    content = "<File does not exist, need to create>"
                    
                prompt = """You are a senior software development expert who can generate code patches based on the complete modification plan, current original code file path, code content, and current file's modification plan. The output format should be as follows:

                <PATCH>
                [start,end)
                new_code
                </PATCH>

                Example:
                <PATCH>
                [0004,0004)
                def new_function():
    pass
                </PATCH>

                means:
                Insert code BEFORE line 4:
                ```
                def new_function():
    pass
                ```
                
                Example 2:
                <PATCH>
                [0004,000b)
                aa
                bb
                cc
                </PATCH>

                means:
                Replace lines [4,11) with:
                ```
                aa
                bb
                cc
                ```

                Rules:
                1. start and end are hexadecimal line numbers (e.g., 000a)
                2. The patch will replace lines [start,end) with new_code (including start, excluding end)
                3. If start equals end, new_code will be inserted BEFORE that line
                4. If new_code is empty, lines [start,end) will be deleted
                5. Multiple patches can be generated
                6. Each line in the input file starts with its 4-digit hexadecimal line number (0-based)
                7. Your new_code should NOT include line numbers
                8. CRITICAL: Patches MUST NOT overlap - ensure each line is modified by at most one patch
                9. Generate patches from bottom to top of the file
                10. Ensure new_code maintains correct indentation and formatting
                11. Each patch should modify no more than 20 lines
                12. Include sufficient context in new_code to maintain code consistency
                13. `[` and `)` must be included in the line range
                14. Line numbers start from 0
                15. Example of INVALID overlapping patches:
                    <PATCH>
                    [0001,0005)
                    code1
                    </PATCH>
                    <PATCH>
                    [0003,0007)  # This overlaps with the previous patch
                    code2
                    </PATCH>
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
                        feedback += f"Skip file {file_path}\n"
                        feedback += "Reason: " + get_multiline_input("Please enter your reason:") + "\n"
                        break
                    else:
                        additional_info += msg + "\n"
                        continue
                else:
                    self._finalize_changes()
                    break
        
        return True, feedback



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
