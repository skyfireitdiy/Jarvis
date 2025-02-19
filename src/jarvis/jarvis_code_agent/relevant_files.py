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
    prompt = f"""You are a helpful assistant that analyzes user requirements and generates SPECIFIC questions about implementation details.

Key Instructions:
1. Focus on the SPECIFIC details of THIS requirement
2. Ask about CONCRETE implementation aspects
3. DO NOT use generic/abstract questions
4. Questions should help understand HOW to implement the requirement

For example:
BAD (too generic): "What components need to be modified?"
GOOD (specific): "How does the current error handling mechanism work in the file_handler.py module?"

Consider these aspects when forming questions:

1. Current Implementation:
   - What specific functions/methods handle this functionality now?
   - How is the data currently structured in relevant modules?
   - What existing patterns or utilities are used for similar features?

2. Technical Details:
   - What exact parameters need to be added/modified?
   - Which specific error cases occur in this context?
   - What data types and structures should be used?

3. Integration Points:
   - Which specific functions call this code?
   - What exact dependencies need to be updated?
   - How do related modules interact with this code?

4. Validation Requirements:
   - What specific test cases should be added?
   - Which edge cases are particularly relevant?
   - How can we verify the changes work correctly?

User Requirement:
{requirement}

Output Format:
<QUESTION>
[Write 3-5 specific, concrete questions that directly relate to implementing this requirement]
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