from typing import Dict, Any, List, Callable
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_dev.team_role import TeamRole
from jarvis.jarvis_dev.message import Message

class QualityAssurance(TeamRole):
    """Quality Assurance role for testing and verification"""
    
    def __init__(self, message_handler: Callable[[Message], Dict[str, Any]]):
        """Initialize QA agent"""
        system_prompt = """You are an experienced QA Engineer responsible for:

1. Quality Strategy
- Define test strategies
- Set quality standards
- Plan test coverage
- Manage test data

2. Testing Process
- Design test cases
- Execute test suites
- Track defects
- Verify fixes

3. Team Collaboration
- Review BA's requirements
- Validate TL's design
- Test SA's components
- Guide Dev testing
- Report to PM

4. Quality Metrics
- Monitor code quality
- Track test coverage
- Measure performance
- Assess reliability

When testing:
1. First understand requirements from BA
2. Review TL's technical guidelines
3. Follow SA's component design
4. Verify Dev's implementation
5. Report issues clearly

You can communicate with team members:
- Clarify requirements with BA
- Discuss standards with TL
- Review design with SA
- Guide Dev on testing
- Update PM on quality

Please ensure thorough testing and quality verification."""

        super().__init__("QualityAssurance", system_prompt, message_handler)
        
    def _get_platform(self):
        """Get agent platform"""
        return PlatformRegistry().get_thinking_platform()
        
    def _get_tools(self):
        """Get agent tools"""
        tools = ToolRegistry()
        tools.use_tools([
            # 基础工具
            "ask_user",
            "methodology",
            "execute_shell",
            # 测试工具
            "read_code",
            "ask_codebase",
            "code_review",
            "lsp_get_diagnostics",
            "lsp_get_document_symbols",
            "file_operation"
        ])
        return tools
        
    def verify(self, implementation: str) -> Dict[str, Any]:
        """Verify implementation quality
        
        Args:
            implementation: Developer's implementation
            
        Returns:
            Dict containing verification results
        """
        try:
            # Create verification prompt
            prompt = f"""Please verify this implementation:

Implementation:
{implementation}

Please provide:
1. Test Results
- Unit test results
- Integration test results
- Performance test results
- Security test results

2. Quality Analysis
- Code quality metrics
- Documentation quality
- Test coverage
- Technical debt

3. Recommendations
- Critical issues
- Improvement suggestions
- Best practices
- Risk assessment
"""

            # Get verification result
            result = self.agent.run(prompt)
            
            # Extract YAML content between tags
            import re
            import yaml
            
            yaml_match = re.search(r'<VERIFICATION>\s*(.*?)\s*</VERIFICATION>', result, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                try:
                    verification = yaml.safe_load(yaml_content)
                    test_results = verification.get("test_results", {})
                    quality_metrics = verification.get("quality_metrics", [])
                    recommendations = verification.get("recommendations", {})
                except:
                    test_results = {}
                    quality_metrics, recommendations = [], {}
            else:
                test_results = {}
                quality_metrics, recommendations = [], {}
            
            return {
                "success": True,
                "verification": result,
                "test_results": test_results,
                "quality_metrics": quality_metrics,
                "recommendations": recommendations
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Verification failed: {str(e)}"
            }
