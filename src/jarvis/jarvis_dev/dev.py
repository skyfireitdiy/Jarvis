from typing import Dict, Any, List
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry

class Developer:
    """Developer role for code implementation"""
    
    def __init__(self):
        """Initialize Developer agent"""
        system_prompt = """You are an experienced Developer responsible for:

1. Code Implementation
- Write clean and efficient code
- Follow coding standards
- Implement design patterns
- Handle edge cases

2. Code Quality
- Write unit tests
- Perform code reviews
- Handle error cases
- Add documentation

3. Technical Integration
- Integrate components
- Handle dependencies
- Manage configurations
- Implement interfaces

Please implement code that is clean, maintainable and well-tested."""

        summary_prompt = """Please format your implementation output in YAML between <IMPLEMENTATION> and </IMPLEMENTATION> tags:
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

        # Initialize agent with thinking capabilities
        self.agent = Agent(
            system_prompt=system_prompt,
            summary_prompt=summary_prompt,
            name="Developer",
            platform=PlatformRegistry().get_codegen_platform(),
            tool_registry=ToolRegistry(),
            auto_complete=True,
            is_sub_agent=True
        )
        
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
