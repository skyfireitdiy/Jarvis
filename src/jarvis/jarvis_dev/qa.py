from typing import Dict, Any, List
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry

class QualityAssurance:
    """Quality Assurance role for testing and verification"""
    
    def __init__(self):
        """Initialize QA agent"""
        system_prompt = """You are an experienced QA Engineer responsible for:

1. Test Planning
- Create test strategies
- Design test cases
- Define test data
- Plan test execution

2. Test Execution
- Execute test cases
- Record test results
- Track defects
- Verify fixes

3. Quality Assurance
- Verify requirements
- Check code quality
- Review documentation
- Ensure standards compliance

Please ensure thorough testing and quality verification."""

        summary_prompt = """Please format your verification output in YAML between <VERIFICATION> and </VERIFICATION> tags:
<VERIFICATION>
test_results:
  unit_tests:
    - suite: test_suite_name
      passed: number
      failed: number
      skipped: number
      coverage: percentage
      issues:
        - description: issue_description
          severity: Critical/Major/Minor
          location: code_location
  
  integration_tests:
    - suite: test_suite_name
      scenarios:
        - name: scenario_name
          status: Pass/Fail
          issues:
            - description: issue_description
  
  performance_tests:
    - type: load/stress/endurance
      metrics:
        - name: metric_name
          value: metric_value
          threshold: threshold_value
          status: Pass/Fail

quality_metrics:
  - category: code/docs/tests
    metrics:
      - name: metric_name
        value: metric_value
        target: target_value
        status: Pass/Fail

recommendations:
  critical_issues:
    - description: issue_description
      impact: impact_description
      solution: proposed_solution
      
  improvements:
    - area: improvement_area
      suggestions:
        - suggestion_description
      priority: High/Medium/Low
</VERIFICATION>"""

        # Initialize agent with thinking capabilities
        self.agent = Agent(
            system_prompt=system_prompt,
            summary_prompt=summary_prompt,
            name="QualityAssurance",
            platform=PlatformRegistry().get_thinking_platform(),
            tool_registry=ToolRegistry(),
            auto_complete=True,
            is_sub_agent=True
        )
        
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
