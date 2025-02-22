from typing import Dict, Any, List, Callable
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_dev.sa import SystemAnalyst
from jarvis.jarvis_dev.message import Message
from jarvis.jarvis_dev.team_role import TeamRole

class Developer(TeamRole):
    """Developer role for code implementation"""
    
    def __init__(self, message_handler: Callable[[Message], Dict[str, Any]]):
        """Initialize Developer agent"""
        system_prompt = """You are an experienced Developer responsible for:

1. Code Understanding
- Study existing codebase
- Analyze code patterns
- Review dependencies
- Map code flows

2. Integration Development
- Write compatible code
- Follow existing patterns
- Integrate with APIs
- Handle data migrations

3. Code Quality
- Match coding style
- Maintain consistency
- Write unit tests
- Update documentation

4. Team Collaboration
- Learn from codebase
- Follow SA's design
- Address QA feedback
- Share code insights

When implementing:
1. First study existing code:
   - Read related modules
   - Understand patterns
   - Check dependencies
   - Note coding style
2. Plan implementation:
   - Match existing patterns
   - Reuse components
   - Follow conventions
   - Consider impact
3. Write and test code:
   - Maintain consistency
   - Add proper tests
   - Update docs
   - Verify integration

You can communicate with team members:
- Ask SA about system design
- Consult TL on patterns
- Discuss tests with QA
- Report progress to PM

Please ensure code quality and seamless integration."""

        # Initialize agent with thinking capabilities
        super().__init__("Developer", system_prompt, message_handler)
        
    def _get_platform(self):
        return PlatformRegistry().get_codegen_platform()
        
    def _get_tools(self):
        tools = ToolRegistry()
        tools.use_tools([
            # 基础工具
            "ask_user",
            "methodology",
            "execute_shell",
            # 开发工具
            "read_code",
            "ask_codebase",
            "lsp_validate_edit",
            "lsp_get_document_symbols",
            "code_review",
            "file_operation",
            "create_code_agent"
        ])
        return tools

    def implement(self, sa_design: str) -> Dict[str, Any]:
        """Implement system design
        
        Args:
            sa_design: SA's system design
            
        Returns:
            Dict containing implementation results
        """
        try:
            # Create implementation prompt
            prompt = f"""Please implement the code based on this system design:

System Design:
{sa_design}

Please provide:
1. Code Implementation
- Component implementations
- Interface implementations
- Data model implementations
- Error handling implementations

2. Unit Tests
- Test cases
- Test data
- Edge cases
- Error cases

3. Documentation
- Code comments
- API documentation
- Usage examples
- Setup instructions

Please format the output in YAML:
<IMPLEMENTATION>
components:
  - name: component_name
    files:
      - path: file_path
        content: |
          # Code implementation
          class ClassName:
              # Implementation details
              pass
    
    tests:
      - path: test_file_path
        content: |
          # Test implementation
          class TestClassName:
              # Test cases
              pass
    
    documentation:
      - type: readme/api/usage
        content: |
          # Documentation
          ## Usage
          ...

dependencies:
  - name: dependency_name
    version: version_number
    purpose: dependency_purpose
    
configuration:
  - file: config_file_path
    content: |
      # Configuration
      key: value
</IMPLEMENTATION>"""

            # Get implementation result
            result = self.agent.run(prompt)
            
            # Extract YAML content between tags
            import re
            import yaml
            
            yaml_match = re.search(r'<IMPLEMENTATION>\s*(.*?)\s*</IMPLEMENTATION>', result, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                try:
                    impl = yaml.safe_load(yaml_content)
                    components = impl.get("components", [])
                    dependencies = impl.get("dependencies", [])
                    configuration = impl.get("configuration", [])
                except:
                    components, dependencies = [], []
                    configuration = []
            else:
                components, dependencies = [], []
                configuration = []
            
            return {
                "success": True,
                "implementation": result,
                "components": components,
                "dependencies": dependencies,
                "configuration": configuration
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Implementation failed: {str(e)}"
            }
