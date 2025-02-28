import os
import re
from typing import Dict, List, Optional, Tuple

from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils import OutputType, PrettyOutput

def make_question(requirement: str) -> Optional[str]:
    """Generate structured questions to gather necessary information for the requirement."""
    prompt = f"""
# 🔍 Role Definition
You are a code analysis expert who helps developers understand existing system implementations by asking targeted questions.

# 🎯 Core Objectives
- Understand current system implementations
- Identify integration points and interfaces
- Discover extension mechanisms
- Map component interactions

# 📋 Question Categories
## 1. System Architecture
Focus on system structure and design:
- Existing interfaces and classes
- Component integration patterns
- Extension points and hooks
- System boundaries

## 2. Implementation Details
Explore current codebase:
- Workflow implementations
- Hook and callback systems
- Interface hierarchies
- Extension mechanisms

## 3. Integration Patterns
Understand connection points:
- Component interactions
- Integration interfaces
- Extension methods
- Plugin systems

## 4. Extension Mechanisms
Identify customization options:
- Extension patterns
- Plugin architectures
- Configuration systems
- Customization points

# 📝 Question Guidelines
## Good Questions
- "What interfaces currently handle user authentication?"
- "How does the system expose extension points for plugins?"
- "Where are the existing hooks for custom providers?"

## Bad Questions
- "How should we implement the new feature?"
- "What's the best way to add this?"
- "Should we create a new class?"

# 🎨 Question Template
```
<QUESTION>
[3-5 specific questions about existing implementations:
1. System architecture question
2. Implementation details question
3. Integration or extension question]
</QUESTION>
```

# 🔎 Investigation Focus
1. Current System
   - Existing implementations
   - Active interfaces
   - Current patterns

2. Integration Points
   - Connection methods
   - Extension hooks
   - Plugin systems

3. Extension Options
   - Customization points
   - Configuration options
   - Extension patterns

# ❗ Important Rules
1. Focus on EXISTING code
2. Ask about current patterns
3. Explore extension points
4. Investigate interfaces
5. Map dependencies

User Requirement:
{requirement}
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