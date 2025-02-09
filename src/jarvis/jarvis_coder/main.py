import os
import threading
from typing import Dict, Any, List, Optional
import re

from jarvis.jarvis_coder.file_select import select_files
from jarvis.utils import OutputType, PrettyOutput, find_git_root, get_max_context_length, is_long_context, load_env_from_file, while_success
from jarvis.models.registry import PlatformRegistry
from jarvis.jarvis_codebase.main import CodeBase
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
import fnmatch
from .patch_handler import PatchHandler
from .git_utils import generate_commit_message, save_edit_record
from .plan_generator import PlanGenerator

# 全局锁对象
index_lock = threading.Lock()

class JarvisCoder:
    def __init__(self, root_dir: str, language: Optional[str] = "python"):
        """Initialize code modification tool"""
        self.root_dir = root_dir
        self.language = language
        self._init_directories()
        self._init_codebase()
        
    def _init_directories(self):
        """Initialize directories"""
        self.max_context_length = get_max_context_length()

        root_dir = find_git_root(self.root_dir)
        if not root_dir:
            root_dir = self.root_dir

        self.root_dir = root_dir

        PrettyOutput.print(f"Git root directory: {self.root_dir}", OutputType.INFO)

        # 1. Check if the code repository path exists, if it does not exist, create it
        if not os.path.exists(self.root_dir):
            PrettyOutput.print(
                "Root directory does not exist, creating...", OutputType.INFO)
            os.makedirs(self.root_dir)

        os.chdir(self.root_dir)

        # 2. Create .jarvis-coder directory
        self.jarvis_dir = os.path.join(self.root_dir, ".jarvis-coder")
        if not os.path.exists(self.jarvis_dir):
            os.makedirs(self.jarvis_dir)

        self.record_dir = os.path.join(self.jarvis_dir, "record")
        if not os.path.exists(self.record_dir):
            os.makedirs(self.record_dir)

        # 3. Process .gitignore file
        gitignore_path = os.path.join(self.root_dir, ".gitignore")
        gitignore_modified = False
        jarvis_ignore_pattern = ".jarvis-*"

        # 3.1 If .gitignore does not exist, create it
        if not os.path.exists(gitignore_path):
            PrettyOutput.print("Create .gitignore file", OutputType.INFO)
            with open(gitignore_path, "w", encoding="utf-8") as f:
                f.write(f"{jarvis_ignore_pattern}\n")
            gitignore_modified = True
        else:
            # 3.2 Check if it already contains the .jarvis-* pattern
            with open(gitignore_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 3.2 Check if it already contains the .jarvis-* pattern
            if jarvis_ignore_pattern not in content.split("\n"):
                PrettyOutput.print("Add .jarvis-* to .gitignore", OutputType.INFO)
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    # Ensure the file ends with a newline
                    if not content.endswith("\n"):
                        f.write("\n")
                    f.write(f"{jarvis_ignore_pattern}\n")
                gitignore_modified = True

        # 4. Check if the code repository is a git repository, if not, initialize the git repository
        if not os.path.exists(os.path.join(self.root_dir, ".git")):
            PrettyOutput.print("Initialize Git repository", OutputType.INFO)
            os.system("git init")
            os.system("git add .")
            os.system("git commit -m 'Initial commit'")
        # 5. If .gitignore is modified, commit the changes
        elif gitignore_modified:
            PrettyOutput.print("Commit .gitignore changes", OutputType.INFO)
            os.system("git add .gitignore")
            os.system("git commit -m 'chore: update .gitignore to exclude .jarvis-* files'")
        # 6. Check if there are uncommitted files in the code repository, if there are, commit once
        elif self._has_uncommitted_files():
            PrettyOutput.print("Commit uncommitted changes", OutputType.INFO)
            os.system("git add .")
            git_diff = os.popen("git diff --cached").read()
            commit_message = generate_commit_message(git_diff)
            os.system(f"git commit -m '{commit_message}'")

    def _init_codebase(self):
        """Initialize codebase"""
        self._codebase = CodeBase(self.root_dir)

    def _has_uncommitted_files(self) -> bool:
        """Check if there are uncommitted files in the code repository"""
        # Get unstaged modifications
        unstaged = os.popen("git diff --name-only").read()
        # Get staged but uncommitted modifications
        staged = os.popen("git diff --cached --name-only").read()
        # Get untracked files
        untracked = os.popen("git ls-files --others --exclude-standard").read()
        
        return bool(unstaged or staged or untracked)

    def _prepare_execution(self) -> None:
        """Prepare execution environment"""
        self._codebase.generate_codebase()


    def _load_related_files(self, feature: str) -> List[str]:
        """Load related file content"""
        ret = []
        # Ensure the index database is generated
        if not self._codebase.is_index_generated():
            PrettyOutput.print("Index database not generated, generating...", OutputType.WARNING)
            self._codebase.generate_codebase()
            
        related_files = self._codebase.search_similar(feature)
        for file, score in related_files:
            PrettyOutput.print(f"Related file: {file} (score: {score:.3f})", OutputType.SUCCESS)
            ret.append(file)
        return ret


    def _finalize_changes(self, feature: str) -> None:
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
        user_confirm = input("Use this commit information? (y/n) [y]: ") or "y"
        
        if user_confirm.lower() != "y":
            commit_message = input("Please enter a new commit information: ")
        
        # No need to git add again, it has already been added
        os.system(f"git commit -m '{commit_message}'")
        save_edit_record(self.record_dir, commit_message, git_diff)

    def _revert_changes(self) -> None:
        """Revert all changes"""
        PrettyOutput.print("Modification cancelled, reverting changes", OutputType.INFO)
        os.system(f"git reset --hard")
        os.system(f"git clean -df")


    def execute(self, feature: str) -> Dict[str, Any]:
        """Execute code modification"""
        try:
            self._prepare_execution()
            
            # Get and select related files
            initial_files = self._load_related_files(feature)
            selected_files = select_files(initial_files, self.root_dir)

            # Whether it is a long context

            
            # Get modification plan
            structed_plan = PlanGenerator().generate_plan(feature, selected_files)
            if not structed_plan:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Failed to generate modification plan, please modify the requirement and try again",
                }
            
            # Execute modification
            if PatchHandler().handle_patch_application(feature, structed_plan):
                self._finalize_changes(feature)
                return {
                    "success": True,
                    "stdout": "Code modification successful",
                    "stderr": "",
                }
            else:
                self._revert_changes()
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Code modification failed, please modify the requirement and try again",
                }
                
        except Exception as e:
            self._revert_changes()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution failed: {str(e)}, please modify the requirement and try again",
                "error": e
            }

def main():
    """Command line entry"""
    import argparse

    load_env_from_file()
    
    parser = argparse.ArgumentParser(description='Code modification tool')
    parser.add_argument('-d', '--dir', help='Project root directory', default=os.getcwd())
    parser.add_argument('-l', '--language', help='Programming language', default="python")
    args = parser.parse_args()
    
    tool = JarvisCoder(args.dir, args.language)
    
    # Loop through requirements
    while True:
        try:
            # Get requirements, pass in project root directory
            feature = get_multiline_input("Please enter the development requirements (input empty line to exit):", tool.root_dir)
            
            if not feature or feature == "__interrupt__":
                break
                
            # Execute modification
            result = tool.execute(feature)
            
            # Display results
            if result["success"]:
                PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
            else:
                if result.get("stderr"):
                    PrettyOutput.print(result["stderr"], OutputType.WARNING)
                if result.get("error"):  # Use get() method to avoid KeyError
                    error = result["error"]
                    PrettyOutput.print(f"Error type: {type(error).__name__}", OutputType.WARNING)
                    PrettyOutput.print(f"Error information: {str(error)}", OutputType.WARNING)
                # Prompt user to continue input
                PrettyOutput.print("\nYou can modify the requirements and try again", OutputType.INFO)
                
        except KeyboardInterrupt:
            print("\nUser interrupted execution")
            break
        except Exception as e:
            PrettyOutput.print(f"Execution failed: {str(e)}", OutputType.ERROR)
            PrettyOutput.print("\nYou can modify the requirements and try again", OutputType.INFO)
            continue
            
    return 0

if __name__ == "__main__":
    exit(main())

class FilePathCompleter(Completer):
    """File path auto-completer"""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self._file_list = None
        
    def _get_files(self) -> List[str]:
        """Get the list of files managed by git"""
        if self._file_list is None:
            try:
                # Switch to project root directory
                old_cwd = os.getcwd()
                os.chdir(self.root_dir)
                
                # Get the list of files managed by git
                self._file_list = os.popen("git ls-files").read().splitlines()
                
                # Restore working directory
                os.chdir(old_cwd)
            except Exception as e:
                PrettyOutput.print(f"Failed to get file list: {str(e)}", OutputType.WARNING)
                self._file_list = []
        return self._file_list
    
    def get_completions(self, document, complete_event):
        """Get completion suggestions"""
        text_before_cursor = document.text_before_cursor
        
        # Check if @ was just entered
        if text_before_cursor.endswith('@'):
            # Display all files
            for path in self._get_files():
                yield Completion(path, start_position=0)
            return
            
        # Check if there was an @ before, and get the search word after @
        at_pos = text_before_cursor.rfind('@')
        if at_pos == -1:
            return
            
        search = text_before_cursor[at_pos + 1:].lower().strip()
        
        # Provide matching file suggestions
        for path in self._get_files():
            path_lower = path.lower()
            if (search in path_lower or  # Directly included
                search in os.path.basename(path_lower) or  # File name included
                any(fnmatch.fnmatch(path_lower, f'*{s}*') for s in search.split())): # Wildcard matching
                # Calculate the correct start_position
                yield Completion(path, start_position=-(len(search)))

class SmartCompleter(Completer):
    """Smart auto-completer, combine word and file path completion"""
    
    def __init__(self, word_completer: WordCompleter, file_completer: FilePathCompleter):
        self.word_completer = word_completer
        self.file_completer = file_completer
        
    def get_completions(self, document, complete_event):
        """Get completion suggestions"""
        # If the current line ends with @, use file completion
        if document.text_before_cursor.strip().endswith('@'):
            yield from self.file_completer.get_completions(document, complete_event)
        else:
            # Otherwise, use word completion
            yield from self.word_completer.get_completions(document, complete_event)

def get_multiline_input(prompt_text: str, root_dir: Optional[str] = ".") -> str:
    """Get multi-line input, support file path auto-completion function
    
    Args:
        prompt_text: Prompt text
        root_dir: Project root directory, for file completion
        
    Returns:
        str: User input text
    """
    # Create file completion
    file_completer = FilePathCompleter(root_dir or os.getcwd())
    
    # Create prompt style
    style = Style.from_dict({
        'prompt': 'ansicyan bold',
        'input': 'ansiwhite',
    })
    
    # Create session
    session = PromptSession(
        completer=file_completer,
        style=style,
        multiline=False,
        enable_history_search=True,
        complete_while_typing=True
    )
    
    # Display initial prompt text
    print(f"\n{prompt_text}")
    
    # Create prompt
    prompt = FormattedText([
        ('class:prompt', ">>> ")
    ])
    
    # Get input
    lines = []
    try:
        while True:
            line = session.prompt(prompt).strip()
            if not line:  # Empty line means input end
                break
            lines.append(line)
    except KeyboardInterrupt:
        return "__interrupt__"
    except EOFError:
        pass
    
    return "\n".join(lines)