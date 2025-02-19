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
    prompt = f"""You are a helpful assistant that generates SPECIFIC questions in English for a code analysis team. The analysis team:
- Has access to the codebase but NO CONTEXT about the requirement
- Will search and analyze code based on your questions
- Needs complete context to understand what to look for

Key Instructions:
1. Write questions in clear, professional English
2. Include necessary CONTEXT in each question
3. Be SPECIFIC about what needs to be found/analyzed
4. Provide enough background for someone with no prior knowledge

For example:
BAD: "How is error handling implemented?"
GOOD: "Given that we need to add retry logic to the file upload feature, how does the current error handling work in upload_handler.py, specifically around network failures and timeout scenarios?"

Consider these aspects when forming questions:

1. Implementation Context:
   - "What is the current implementation of [specific feature]?"
   - "Which modules/classes handle [specific functionality]?"
   - "What is the existing workflow for [specific operation]?"

2. Technical Investigation:
   - "How does the system currently handle [specific scenario]?"
   - "What patterns are used for [specific behavior]?"
   - "Where are the configuration settings for [specific feature]?"

3. Integration Details:
   - "Which components call or depend on [specific module]?"
   - "What is the data flow between [component A] and [component B]?"
   - "How are errors propagated from [specific component]?"

4. Requirements Context:
   - "Given [specific requirement], what are the current limitations?"
   - "For [specific change], what validation rules apply?"
   - "In the context of [feature], what edge cases exist?"

User Requirement:
{requirement}

Output Format:
<QUESTION>
[Write 3-5 specific questions in English, ensuring each includes full context for someone with no prior knowledge of the requirement]
</QUESTION>
"""
    model = PlatformRegistry().get_normal_platform()
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