import os
import threading
from typing import Dict, Any, List, Optional
import re

from jarvis.jarvis_coder.file_select import select_files
from jarvis.utils import OutputType, PrettyOutput, find_git_root, get_max_context_length, is_long_context, init_env, while_success
from jarvis.models.registry import PlatformRegistry
from jarvis.jarvis_codebase.main import CodeBase
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
import fnmatch
from .patch_handler import PatchHandler
from .git_utils import generate_commit_message, init_git_repo, save_edit_record
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
        self.root_dir = init_git_repo(self.root_dir)

    def _init_codebase(self):
        """Initialize codebase"""
        self._codebase = CodeBase(self.root_dir)


    def _load_related_files(self, feature: str) -> List[str]:
        """Load related file content"""
        ret = []
        # Ensure the index database is generated
        if not self._codebase.is_index_generated():
            PrettyOutput.print("Index database not generated, generating...", OutputType.WARNING)
            self._codebase.generate_codebase()
            
        related_files = self._codebase.search_similar(feature)
        for file in related_files:
            PrettyOutput.print(f"Related file: {file}", OutputType.SUCCESS)
            ret.append(file)
        return ret



    def execute(self, feature: str) -> Dict[str, Any]:
        """Execute code modification"""
        try:
            # Get and select related files
            initial_files = self._load_related_files(feature)
            selected_files = select_files(initial_files, self.root_dir)

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
                return {
                    "success": True,
                    "stdout": "Code modification successful",
                    "stderr": "",
                }
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Code modification failed, please modify the requirement and try again",
                }
                
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution failed: {str(e)}, please modify the requirement and try again",
            }

def main():
    """Command line entry"""
    import argparse

    init_env()
    
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