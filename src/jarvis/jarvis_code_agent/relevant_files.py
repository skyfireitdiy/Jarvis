import os
import re
from typing import Dict, List, Optional, Tuple

from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.utils import OutputType, PrettyOutput

def make_question(requirement: str) -> Optional[str]:
    """Generate structured questions to gather necessary information for the requirement."""
    prompt = f"""You are a code analysis expert who helps developers understand existing system implementations. Generate specific questions to investigate:
- Current system implementations
- Existing interfaces and integration points
- Extension mechanisms and patterns
- Related components and their interactions

Key Instructions:
1. Focus on understanding the EXISTING system
2. Ask about interfaces, hooks, and extension points
3. Investigate integration patterns and dependencies
4. Explore current implementation details

For example:
BAD: "How should we implement the new feature?"
GOOD: "What are the existing extension points in the authentication system that we can use to add the new OAuth provider? Specifically, how does AuthProvider interface work and where is it currently used?"

Consider these investigation aspects:

1. System Architecture:
   - "What are the existing interfaces/classes that handle [functionality]?"
   - "How is [feature] currently integrated with other components?"
   - "Where are the extension points for [system component]?"

2. Implementation Details:
   - "What is the current workflow for [operation] in the system?"
   - "How does the system expose hooks/callbacks for [functionality]?"
   - "Which interfaces/abstract classes are used for [feature] extensibility?"

3. Integration Patterns:
   - "How do existing components integrate with [system part]?"
   - "What are the current integration points for [feature]?"
   - "How does the system handle extensions to [component]?"

4. Extension Mechanisms:
   - "What patterns are used for extending [functionality]?"
   - "How do existing plugins/extensions connect to [system]?"
   - "Where are the configuration points for [feature] customization?"

User Requirement:
{requirement}

Output Format:
<QUESTION>
[Write 3-5 specific questions focusing on existing implementations and extension points. Each question should help understand how to integrate with or extend the current system]
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
        PrettyOutput.print("从代码库中查找文件...", OutputType.INFO)
        codebase = CodeBase(root_dir)
        question = make_question(user_input)
        if question is None:
            return [], ""
        files_from_codebase, infomation = codebase.ask_codebase(question)

        selected_files = select_files(files_from_codebase, os.getcwd())
        return selected_files, infomation
    except Exception:
        PrettyOutput.print("查找相关文件失败", OutputType.ERROR)
        return [], ""