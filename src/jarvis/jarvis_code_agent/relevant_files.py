import os
import re
from typing import Dict, List, Optional, Tuple

from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.utils import OutputType, PrettyOutput

def make_question(requirement: str) -> Optional[str]:
    """Generate structured questions to gather necessary information for the requirement.
    
    Args:
        requirement: The user's requirement description
        
    Returns:
        str: A formatted string containing relevant questions
    """
    prompt = """You are a helpful assistant that analyze the user's requirement and make a question to 
    gather necessary information for the requirement.

    To better understand and implement this requirement, please consider:

1. Code Structure Questions:
   - Which components or modules need to be modified?
   - Are there existing patterns or conventions to follow?
   - What interfaces or APIs are affected?

2. Implementation Details:
   - What are the specific changes needed?
   - Are there any dependencies to consider?
   - What error cases need to be handled?

3. Integration Concerns:
   - How will these changes affect other parts of the system?
   - Are there any backward compatibility issues?
   - What tests need to be updated?

4. Performance and Quality:
   - Are there any performance implications?
   - What edge cases should be considered?
   - How can we validate the changes?

Please analyze the requirement based on these questions.

User Requirement:
{requirement}

Output Format:
<QUESTION>
{question}
</QUESTION>
"""
    model = PlatformRegistry().get_thinking_platform()
    response = model.chat_until_success(prompt)
    response = re.search(r'<QUESTION>(.*?)</QUESTION>', response, re.DOTALL)
    if response is None:
        return None
    return response.group(1)


def find_relevant_information(user_input: str, root_dir: str) -> Tuple[List[Dict[str, str]], str]:
    try:
        PrettyOutput.print("Find files from codebase...", OutputType.INFO)
        codebase = CodeBase(root_dir)
        question = make_question(user_input)
        if question is None:
            return [], ""
        files_from_codebase, infomation = codebase.ask_codebase(question)
        PrettyOutput.print("Find files by agent...", OutputType.INFO)

        selected_files = select_files(files_from_codebase, os.getcwd())
        return selected_files, infomation
    except Exception:
        PrettyOutput.print("Failed to find relevant files", OutputType.ERROR)
        return [], ""