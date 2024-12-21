import yaml
from typing import Dict, Any, Optional
from datetime import datetime
from colorama import Fore, Style

from .base import BaseAgent
from utils import extract_yaml_from_response
from utils.logger import Logger
from llm import BaseLLM

class LlamaAgent(BaseAgent):
    """Main agent class that implements the core task loop"""
    
    def __init__(self, llm: BaseLLM, tool_registry=None, verbose: bool = False):
        super().__init__(llm=llm, verbose=verbose)
        self.logger = Logger()
        self.tool_registry = tool_registry
        self.task_context = {}
        self.current_task = None
    
    def process_input(self, task: str) -> Dict[str, Any]:
        """Process user input and return execution results
        
        Args:
            task: User input task description
            
        Returns:
            Dict containing:
                - success: bool, whether task completed successfully
                - result: Final result or error message
                - subtasks: List of subtask results if task was decomposed
                - evidence: List of evidence supporting the result
        """
        self.current_task = task
        self.task_context = {
            "execution_history": [],
            "subtasks": []
        }
        
        self.logger.info(f"\n{Fore.CYAN}🎯 Task:{Style.RESET_ALL}")
        self.logger.info(f"{Fore.CYAN}  {task}{Style.RESET_ALL}")
        
        # 1. Analyze if task needs decomposition
        decomposition_analysis = self._analyze_task_decomposition()
        needs_decomposition = decomposition_analysis.get("needs_decomposition", False)
        
        self.logger.info(f"\n{Fore.BLUE}📋 Task Analysis:{Style.RESET_ALL}")
        self.logger.info(f"{Fore.BLUE}  • Needs Decomposition: {needs_decomposition}{Style.RESET_ALL}")
        self.logger.info(f"{Fore.BLUE}  • Reason: {decomposition_analysis.get('reason')}{Style.RESET_ALL}")
        
        if needs_decomposition:
            # 2. Handle decomposed task
            return self._handle_decomposed_task(decomposition_analysis)
        else:
            # 3. Handle single tool task
            return self._handle_single_tool_task(decomposition_analysis)
    
    def _analyze_task_decomposition(self) -> Dict[str, Any]:
        """Analyze if task needs to be decomposed"""
        prompt_parts = [
            "# Task Decomposition Analysis",
            "",
            "## Task",
            self.current_task,
            "",
            "## CRITICAL Tool Rules",
            f"ONLY these tools are available: {', '.join(self.tool_registry.list_tools())}",
            "• MUST use exact tool names from the list",
            "• CANNOT use tools not in the list",
            "• MUST check tool availability before use",
            "",
            "## Tool Usage Examples:",
            "• Shell command execution:",
            "```yaml",
            "single_tool_execution:",
            "  tool: shell  # MUST use 'shell', not 'ping' or other names",
            "  parameters:",
            "    command: 'command arg1 ; command arg2'  # Multiple operations with ;",
            "  reason: Execute shell commands",
            "```",
            "",
            "• Math calculation:",
            "```yaml",
            "single_tool_execution:",
            "  tool: math  # MUST use 'math', not 'calculator' or other names",
            "  parameters:",
            "    expression: 'value1 + value2'",
            "  reason: Perform calculation",
            "```",
            "",
            "## Response Format",
            "```yaml",
            "needs_decomposition: false",
            "reason: Clear explanation why no decomposition needed",
            "",
            "single_tool_execution:",
            "  tool: exact_tool_name  # MUST be one of: " + ", ".join(self.tool_registry.list_tools()),
            "  parameters:  # ONLY include valid parameters for the tool",
            "    command: 'exact command'  # For shell tool",
            "    # OR",
            "    expression: 'exact expression'  # For math tool",
            "  reason: Why this tool can complete the task",
            "```",
            "",
            "## Parameter Examples:",
            "shell tool parameters:",
            "  ✓ command: 'command arg1 ; command arg2'  # Multiple operations",
            "  ✓ command: 'command path/to/target'  # Single operation",
            "",
            "math tool parameters:",
            "  ✓ expression: 'value1 + value2'",
            "  ✓ precision: 4",
            "",
            "## INCORRECT Examples:",
            "❌ Wrong tool name:",
            "```yaml",
            "single_tool_execution:",
            "  tool: ping  # WRONG: must use 'shell', not 'ping'",
            "```",
            "",
            "❌ Invalid tool:",
            "```yaml",
            "single_tool_execution:",
            "  tool: invalid_tool  # WRONG: tool not in available list",
            "```",
            "## Task Type Analysis Rules",
            "MUST decompose task when:",
            "• Need to SEARCH for data first",
            "• Need MULTIPLE VALUES for calculation",
            "• Need to TRANSFORM data before use",
            "• Results depend on PREVIOUS STEPS",
            "",
            "## Task Decomposition Examples",
            "Example 1: Calculate with searched values",
            "```yaml",
            "needs_decomposition: true",
            "reason: Need to search for values before calculation",
            "subtasks:",
            "  - '[WHAT] Search first value | [WHY] Need exact number | [GOAL] Get value | [DONE] Have number'",
            "  - '[WHAT] Search second value | [WHY] Need exact number | [GOAL] Get value | [DONE] Have number'",
            "  - '[WHAT] Calculate result | [WHY] Process values | [GOAL] Final answer | [DONE] Have result'",
            "```",
            "",
            "## Tool Selection Guide",
            "• Use SEARCH tool for:",
            "  - Finding specific values",
            "  - Getting real-world data",
            "  - Looking up information",
            "",
            "• Use MATH tool for:",
            "  - Calculations with KNOWN values",
            "  - Processing NUMERIC data",
            "  - Mathematical operations",
            "",
            "## Common Mistakes (DO NOT):",
            "❌ Using math tool without data:",
            "```yaml",
            "single_tool_execution:  # WRONG",
            "  tool: math",
            "  parameters:",
            "    expression: 'unknown_value + other_value'",
            "```",
            "",
            "✓ Correct approach:",
            "```yaml",
            "needs_decomposition: true  # Correct",
            "reason: Need to get values first",
            "subtasks:  # Search then calculate",
            "  - '[WHAT] Search values | [WHY] Need data | [GOAL] Get numbers | [DONE] Have data'",
            "  - '[WHAT] Calculate | [WHY] Process data | [GOAL] Get result | [DONE] Done'",
            "```"
        ]
        
        prompt = "\n".join(prompt_parts)
        
        while True:
            result = self._get_llm_yaml_response(prompt)
            if not result:
                continue
            
            # Validate response format
            if "needs_decomposition" not in result:
                self.logger.error(f"{Fore.RED}❌ Invalid response: Missing needs_decomposition field{Style.RESET_ALL}")
                self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                continue
            
            if "reason" not in result:
                self.logger.error(f"{Fore.RED}❌ Invalid response: Missing reason field{Style.RESET_ALL}")
                self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                continue
            
            # Check for mutually exclusive fields
            has_single_tool = "single_tool_execution" in result
            has_subtasks = "subtasks" in result
            
            if has_single_tool and has_subtasks:
                self.logger.error(f"{Fore.RED}❌ Invalid response: Contains both single_tool_execution and subtasks{Style.RESET_ALL}")
                self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                continue
            
            if not has_single_tool and not has_subtasks:
                self.logger.error(f"{Fore.RED}❌ Invalid response: Missing both single_tool_execution and subtasks{Style.RESET_ALL}")
                self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                continue
            
            # Validate needs_decomposition matches content
            needs_decomp = result["needs_decomposition"]
            if needs_decomp and not has_subtasks:
                self.logger.error(f"{Fore.RED}❌ Invalid response: needs_decomposition is true but no subtasks provided{Style.RESET_ALL}")
                self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                continue
            
            if not needs_decomp and not has_single_tool:
                self.logger.error(f"{Fore.RED}❌ Invalid response: needs_decomposition is false but no single_tool_execution provided{Style.RESET_ALL}")
                self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                continue
            
            # Validate tool name and parameters if single tool execution
            if has_single_tool:
                tool_exec = result["single_tool_execution"]
                if "tool" not in tool_exec:
                    self.logger.error(f"{Fore.RED}❌ Invalid response: Missing tool name in single_tool_execution{Style.RESET_ALL}")
                    self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                    continue
                
                if tool_exec["tool"] not in self.tool_registry.list_tools():
                    self.logger.error(f"{Fore.RED}❌ Invalid response: Unknown tool '{tool_exec['tool']}'{Style.RESET_ALL}")
                    self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                    continue
                
                if "parameters" not in tool_exec or not isinstance(tool_exec["parameters"], dict):
                    self.logger.error(f"{Fore.RED}❌ Invalid response: Missing or invalid parameters{Style.RESET_ALL}")
                    self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                    continue
            
            # Check subtasks format if present
            if has_subtasks:
                subtasks = result.get("subtasks", [])
                if not all(isinstance(task, str) for task in subtasks):
                    self.logger.error(f"{Fore.RED}❌ Invalid subtask format: All subtasks must be strings{Style.RESET_ALL}")
                    self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                    continue
                
                # Check if subtasks follow the required format
                for task in subtasks:
                    if not self._validate_subtask_format(task):
                        self.logger.error(f"{Fore.RED}❌ Invalid subtask format: Missing required sections{Style.RESET_ALL}")
                        self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
                        continue
            
            return result
    
    def _validate_subtask_format(self, task: str) -> bool:
        """Validate subtask format"""
        if not isinstance(task, str):
            self.logger.error(f"{Fore.RED}❌ Invalid subtask: Must be string, got {type(task)}{Style.RESET_ALL}")
            return False
        
        required_sections = ['[WHAT]', '[WHY]', '[GOAL]', '[DONE]']
        if not all(section in task for section in required_sections):
            self.logger.error(f"{Fore.RED}❌ Invalid subtask format: Missing required sections{Style.RESET_ALL}")
            self.logger.error(f"{Fore.RED}  Required format: [WHAT] action | [WHY] reason | [GOAL] target | [DONE] check{Style.RESET_ALL}")
            return False
        
        # Verify format with pipe separators
        parts = task.split('|')
        if len(parts) != 4:
            self.logger.error(f"{Fore.RED}❌ Invalid subtask format: Must have exactly 4 parts separated by |{Style.RESET_ALL}")
            return False
        
        return True
    
    def _handle_decomposed_task(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a task that needs to be decomposed into subtasks"""
        subtasks = analysis.get("subtasks", [])
        if not subtasks:
            return {
                "success": False,
                "result": "Failed to decompose task into subtasks",
                "subtasks": [],
                "evidence": []
            }
        
        # Print task decomposition details
        self.logger.info(f"\n{Fore.MAGENTA}🔄 Task Decomposition:{Style.RESET_ALL}")
        self.logger.info(f"{Fore.MAGENTA}  Total Subtasks: {len(subtasks)}{Style.RESET_ALL}")
        
        for i, subtask in enumerate(subtasks, 1):
            self.logger.info(f"\n{Fore.MAGENTA}  Subtask {i}:{Style.RESET_ALL}")
            self.logger.info(f"{Fore.CYAN}    • {subtask}{Style.RESET_ALL}")
        
        # Execute each subtask
        subtask_results = []
        completed_reports = []  # Store completed task reports
        collected_data = {}  # Store data between subtasks
        
        for i, subtask in enumerate(subtasks, 1):
            self.logger.info(f"\n{Fore.YELLOW}📎 Executing Subtask {i}/{len(subtasks)}:{Style.RESET_ALL}")
            self.logger.info(f"{Fore.YELLOW}  • {subtask}{Style.RESET_ALL}")
            
            # Add context for next subtask
            subtask_context = {
                "previous_results": completed_reports,
                "collected_data": collected_data
            }
            
            # Execute subtask with context
            subtask_result = self.process_input_with_context(subtask, subtask_context)
            
            # Store task report and extract data
            if isinstance(subtask_result, dict):
                if "task_report" in subtask_result:
                    report = subtask_result["task_report"]
                    completed_reports.append(report)
                    
                    # Extract and store relevant data
                    if "findings" in report:
                        for finding in report["findings"]:
                            if isinstance(finding, dict):
                                key = finding.get("item", "")
                                data = finding.get("data", {})
                                if key and data:
                                    collected_data[key] = data
            
            subtask_results.append({
                "subtask": subtask,
                "result": subtask_result,
                "context": subtask_context
            })
            
            # Print subtask result
            status = "✅" if subtask_result.get("success") else "❌"
            color = Fore.GREEN if subtask_result.get("success") else Fore.RED
            self.logger.info(f"\n{color}  {status} Subtask {i} Result:{Style.RESET_ALL}")
            self.logger.info(f"{color}    • Success: {subtask_result.get('success')}{Style.RESET_ALL}")
            self.logger.info(f"{color}    • Result: {subtask_result.get('result')}{Style.RESET_ALL}")
            
            # Track overall success
            if not subtask_result.get("success", False):
                self.logger.info(f"\n{Fore.RED}❌ Stopping due to subtask failure{Style.RESET_ALL}")
                break
        
        # Analyze final results with context
        final_analysis = self._analyze_results(subtask_results, {
            "completed_reports": completed_reports,
            "collected_data": collected_data
        })
        
        # Check if task is truly complete
        if final_analysis.get("success", False):
            completion_check = self._check_completion(final_analysis)
            is_complete = completion_check.get("is_complete", False)
            
            if not is_complete:
                self.logger.info(f"\n{Fore.YELLOW}⚠️ Task Incomplete:{Style.RESET_ALL}")
                self.logger.info(f"{Fore.YELLOW}  • Reason: {completion_check.get('reason')}{Style.RESET_ALL}")
                if completion_check.get('missing_requirements'):
                    self.logger.info(f"{Fore.YELLOW}  • Missing Requirements:{Style.RESET_ALL}")
                    for req in completion_check['missing_requirements']:
                        self.logger.info(f"{Fore.YELLOW}    - {req}{Style.RESET_ALL}")
                return {
                    "success": False,
                    "result": completion_check.get("reason", "Task incomplete"),
                    "subtasks": subtask_results,
                    "evidence": completion_check.get("evidence", []),
                    "task_report": final_analysis.get("task_report", {})
                }
        
        # Print final summary
        self.logger.info(f"\n{Fore.BLUE}📊 Task Summary:{Style.RESET_ALL}")
        self.logger.info(f"{Fore.BLUE}  • Total Subtasks: {len(subtasks)}{Style.RESET_ALL}")
        self.logger.info(f"{Fore.BLUE}  • Completed Successfully: {len([r for r in subtask_results if r['result'].get('success')])}/{len(subtasks)}{Style.RESET_ALL}")
        
        if final_analysis.get('task_report'):
            report = final_analysis['task_report']
            if report.get('conclusion'):
                self.logger.info(f"\n{Fore.GREEN}📝 Conclusion:{Style.RESET_ALL}")
                for line in report['conclusion'].splitlines():
                    self.logger.info(f"{Fore.GREEN}  {line}{Style.RESET_ALL}")
            
            if report.get('evidence'):
                self.logger.info(f"\n{Fore.CYAN}📌 Evidence:{Style.RESET_ALL}")
                for evidence in report['evidence']:
                    self.logger.info(f"{Fore.CYAN}  • {evidence}{Style.RESET_ALL}")
        
        # Print final task report
        self._print_task_report(final_analysis, "Final Task")
        
        return {
            "success": final_analysis.get("success", False),
            "result": final_analysis.get("task_report", {}).get("conclusion", ""),
            "subtasks": subtask_results,
            "evidence": final_analysis.get("task_report", {}).get("evidence", []),
            "task_report": final_analysis.get("task_report", {})
        }
    
    def process_input_with_context(self, task: str, previous_reports: list = None) -> Dict[str, Any]:
        """Process input with context from previous task reports"""
        self.current_task = task
        self.task_context = {
            "execution_history": [],
            "subtasks": [],
            "previous_reports": previous_reports or []
        }
        
        # Rest of the method remains the same as process_input
        return self.process_input(task)
    
    def _handle_single_tool_task(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a task that can be completed with a single tool"""
        tool_execution = analysis.get("single_tool_execution", {})
        
        # Print execution info
        self.logger.info(f"\n{Fore.BLUE}🔧 Executing Tool:{Style.RESET_ALL}")
        self.logger.info(f"{Fore.BLUE}  • Tool: {tool_execution.get('tool')}{Style.RESET_ALL}")
        self.logger.info(f"{Fore.BLUE}  • Reason: {tool_execution.get('reason')}{Style.RESET_ALL}")
        
        # Print parameters
        if parameters := tool_execution.get('parameters'):
            self.logger.info(f"{Fore.BLUE}  • Parameters:{Style.RESET_ALL}")
            for param_name, param_value in parameters.items():
                self.logger.info(f"{Fore.BLUE}    {param_name}: {param_value}{Style.RESET_ALL}")
        
        # Execute tool
        result = self.execute_step(tool_execution)
        
        # Check completion directly
        completion_check = self._check_completion(result)
        
        # Generate task report
        task_report = {
            "task_report": {
                "conclusion": completion_check.get("conclusion", ""),
                "findings": [
                    {
                        "item": "Tool Execution",
                        "status": "success" if result.get("success") else "failed",
                        "data": result.get("result", {}),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                ],
                "evidence": completion_check.get("evidence", []),
                "execution_summary": {
                    "success": result.get("success", False),
                    "total_steps": 1,
                    "completed_steps": 1,
                    "error_count": 0 if result.get("success") else 1
                }
            }
        }
        
        # Print task report
        self._print_task_report(task_report, "Single Tool Task")
        
        # Return results
        return {
            "success": completion_check.get("is_complete", False),
            "result": completion_check.get("conclusion", ""),
            "subtasks": [],
            "evidence": completion_check.get("evidence", []),
            "task_report": task_report["task_report"]
        }
    
    def execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single tool step"""
        # Validate step format
        if not isinstance(step, dict):
            return {"success": False, "error": "Invalid step format", "result": None}
        
        # Get tool name
        tool_name = step.get("tool", "")
        if not tool_name:
            return {"success": False, "error": "No tool specified", "result": None}
        
        # Get parameters
        parameters = step.get("parameters", {})
        if not isinstance(parameters, dict):
            return {"success": False, "error": "Invalid parameters format", "result": None}
        
        # Get tool
        tool = self.tool_registry.get_tool(tool_name.lower())
        if not tool:
            return {"success": False, "error": f"Tool not found: {tool_name}", "result": None}
        
        # Execute tool
        try:
            # Execute tool and get result
            tool_result = tool.execute(**parameters)
            
            # Print execution result immediately
            self.logger.info(f"\n{Fore.GREEN}✨ Tool Output:{Style.RESET_ALL}")
            
            if isinstance(tool_result, dict) and "result" in tool_result:
                result = tool_result["result"]
                if isinstance(result, dict):
                    # Print stdout if present
                    if stdout := result.get("stdout", "").strip():
                        self.logger.info(f"{Fore.GREEN}📝 stdout:{Style.RESET_ALL}")
                        for line in stdout.splitlines():
                            if line.strip():
                                self.logger.info(f"{Fore.GREEN}  {line}{Style.RESET_ALL}")
                
                    # Print stderr if present
                    if stderr := result.get("stderr", "").strip():
                        self.logger.info(f"{Fore.RED}❌ stderr:{Style.RESET_ALL}")
                        for line in stderr.splitlines():
                            if line.strip():
                                self.logger.info(f"{Fore.RED}  {line}{Style.RESET_ALL}")
                
                    # Print return code if present
                    if "returncode" in result:
                        status = "✅" if result["returncode"] == 0 else "❌"
                        color = Fore.GREEN if result["returncode"] == 0 else Fore.RED
                        self.logger.info(f"{color}{status} Return code: {result.get('returncode')}{Style.RESET_ALL}")
                
                    # Print command if present
                    if command := result.get("command"):
                        self.logger.info(f"{Fore.BLUE}🔧 Command: {command}{Style.RESET_ALL}")
            
            self.logger.info("")  # 空行分隔
            return tool_result
            
        except Exception as e:
            # Print error immediately
            self.logger.info(f"\n{Fore.RED}❌ Tool Error:{Style.RESET_ALL}")
            self.logger.info(f"{Fore.RED}  {str(e)}{Style.RESET_ALL}")
            self.logger.info("")  # 空行分隔
            
            return {
                "success": False,
                "error": str(e),
                "result": None
            }
    
    def _get_llm_yaml_response(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Get LLM response and parse as YAML"""
        while True:  # Keep trying until we get a valid response
            # Log prompt if verbose
            if self.verbose:
                self.logger.info(f"\n{Fore.CYAN}💭 Prompt to LLM:{Style.RESET_ALL}")
                for line in prompt.splitlines():
                    self.logger.info(f"{Fore.CYAN}  {line}{Style.RESET_ALL}")
            
            # Get response
            response = self.llm.get_completion(prompt)
            
            # Log response if verbose
            if self.verbose:
                self.logger.info(f"\n{Fore.MAGENTA} LLM Response:{Style.RESET_ALL}")
                for line in response.splitlines():
                    self.logger.info(f"{Fore.MAGENTA}  {line}{Style.RESET_ALL}")
            
            # Parse YAML
            result = extract_yaml_from_response(response)
            
            if result:
                return result
            
            # If parsing failed, log error and retry
            self.logger.error(f"{Fore.RED}❌ Failed to parse YAML from response{Style.RESET_ALL}")
            self.logger.info(f"{Fore.YELLOW}⚠️ Retrying...{Style.RESET_ALL}")
            continue
    
    def _check_completion(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Check if task is complete based on current information"""
        prompt_parts = [
            "# Completion Check",
            "",
            "## Original Task",
            self.current_task,
            "",
            "## Current Information",
            "```yaml",
            yaml.dump(analysis, default_flow_style=False, sort_keys=False),
            "```",
            "",
            "## CRITICAL Evaluation Rules",
            "1. ONLY use data from actual tool execution",
            "2. DO NOT make assumptions or inferences",
            "3. DO NOT add information not in results",
            "4. If data is missing, mark as incomplete",
            "",
            "## Data Usage Rules",
            "DO:",
            "• Use EXACT values from results",
            "• Quote SPECIFIC output lines",
            "• Reference ACTUAL measurements",
            "• Mark MISSING data as unknown",
            "",
            "DO NOT:",
            "• Invent or assume values",
            "• Round or approximate numbers",
            "• Fill in missing information",
            "• Make predictions or guesses",
            "",
            "## Response Format",
            "```yaml",
            "is_complete: true/false  # Based on having actual data",
            "",
            "reason: |",
            "  Explain completion status using only available data.",
            "  Quote specific values and outputs.",
            "",
            "conclusion: |",
            "  State only what is directly supported by results.",
            "  Use exact values and measurements.",
            "",
            "evidence:",
            "  - |",
            "    Command: <executed command>",
            "    Target: <checked target>",
            "    Result: |",
            "      <complete output>",
            "      <all relevant lines>",
            "    Status: <final status>",
            "",
            "missing_requirements: []  # Empty list if no missing data",
            "```",
            "",
            "## Example Good Response:",
            "```yaml",
            "is_complete: true",
            "reason: |",
            "  All required data is available in the output.",
            "  Both targets were checked successfully.",
            "",
            "conclusion: |",
            "  Target 1 is online with 2ms response time.",
            "  Target 2 is offline with 100% packet loss.",
            "",
            "evidence:",
            "  - |",
            "    Command: ping -c 1 192.168.1.1",
            "    Target: 192.168.1.1",
            "    Result: |",
            "      PING 192.168.1.1 (192.168.1.1) 56(84) bytes of data.",
            "      64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=2ms",
            "      1 packets transmitted, 1 received, 0% packet loss",
            "    Status: Online (0% packet loss)",
            "",
            "missing_requirements: []  # No missing data",
            "```",
            "",
            "## Example Incomplete Response:",
            "```yaml",
            "is_complete: false",
            "reason: |",
            "  Cannot determine status due to connection error.",
            "",
            "conclusion: |",
            "  Status check failed due to network issues.",
            "",
            "evidence:",
            "  - |",
            "    Command: ping -c 1 target",
            "    Target: target",
            "    Result: |",
            "      Network is unreachable",
            "    Status: Error (network unreachable)",
            "",
            "missing_requirements:",
            "  - Cannot reach target host",
            "  - No response data available",
            "```",
            "",
            "## Evidence Format",
            "• Use SUMMARY format:",
            "  'For <target>: <complete context and result>'",
            "",
            "## Example Good Evidence:",
            "```yaml",
            "evidence:",
            "  - 'For IP 192.168.1.1: Ping successful, responded in 2ms with 0% packet loss'",
            "  - 'For IP 192.168.1.2: Ping failed, 100% packet loss, no response received'",
            "```",
            "",
            "## Example Bad Evidence (DO NOT USE):",
            "```yaml",
            "evidence:",
            "  - 'time=2ms'  # BAD: No context",
            "  - 'ping failed'  # BAD: No details",
            "```",
            "",
            "## Evidence Requirements:",
            "1. MUST include:",
            "  • What was checked",
            "  • How it was checked",
            "  • Complete result",
            "  • Final status",
            "",
            "2. MUST be readable:",
            "  • Use complete sentences",
            "  • Include all context",
            "  • Be self-contained",
            "  • Be unambiguous",
        ]
        
        prompt = "\n".join(prompt_parts)
        while True:
            result = self._get_llm_yaml_response(prompt)
            if not result:
                continue
            
            # Print completion check conclusion
            self.logger.info(f"\n{Fore.BLUE}✅ Completion Check:{Style.RESET_ALL}")
            
            if is_complete := result.get("is_complete"):
                status = "Complete" if is_complete else "Incomplete"
                color = Fore.GREEN if is_complete else Fore.YELLOW
                self.logger.info(f"{color}  • Status: {status}{Style.RESET_ALL}")
            
            if reason := result.get("reason"):
                self.logger.info(f"{Fore.BLUE}  • Reason:{Style.RESET_ALL}")
                for line in reason.splitlines():
                    if line.strip():
                        self.logger.info(f"{Fore.BLUE}    {line}{Style.RESET_ALL}")
            
            if conclusion := result.get("conclusion"):
                self.logger.info(f"{Fore.GREEN}  • Conclusion:{Style.RESET_ALL}")
                for line in conclusion.splitlines():
                    if line.strip():
                        self.logger.info(f"{Fore.GREEN}    {line}{Style.RESET_ALL}")
            
            if evidence := result.get("evidence"):
                self.logger.info(f"{Fore.CYAN}  • Evidence:{Style.RESET_ALL}")
                for item in evidence:
                    self.logger.info(f"{Fore.CYAN}    - {item}{Style.RESET_ALL}")
            
            if missing := result.get("missing_requirements"):
                self.logger.info(f"{Fore.YELLOW}  • Missing Requirements:{Style.RESET_ALL}")
                for req in missing:
                    self.logger.info(f"{Fore.YELLOW}    - {req}{Style.RESET_ALL}")
            
            return result
    
    def _get_next_step_with_history(self, analysis: Dict[str, Any], execution_history: Dict[str, Any]) -> Dict[str, Any]:
        """Determine next step based on current analysis and execution history"""
        prompt_parts = [
            "# Next Step Analysis",
            "",
            "## Original Task",
            self.current_task,
            "",
            "## Execution History",
            "```yaml",
            yaml.dump(execution_history, default_flow_style=False, sort_keys=False),
            "```",
            "",
            "## Current Status",
            "```yaml",
            yaml.dump(analysis, default_flow_style=False, sort_keys=False),
            "```",
            "",
            "## CRITICAL Analysis Rules",
            "1. REVIEW previous execution attempts",
            "2. IDENTIFY what went wrong",
            "3. SUGGEST different approach if needed",
            "4. AVOID repeating failed strategies",
            "",
            "## Decision Requirements",
            "1. Should task be DECOMPOSED now?",
            "2. Can next step use a SINGLE tool?",
            "3. What SPECIFIC action is needed?",
            "4. How to AVOID previous failures?",
            "",
            "## Response Format",
            "```yaml",
            "needs_decomposition: true/false",
            "reason: |",
            "  Why decompose/continue with single tool",
            "  Address previous execution results",
            "  Explain new approach",
            "",
            "# If needs_decomposition is true:",
            "subtasks:",
            "  - '[WHAT] Specific action | [WHY] Purpose | [GOAL] Success criteria | [DONE] Completion check'",
            "",
            "# If needs_decomposition is false:",
            "single_tool_execution:",
            "  tool: exact_tool_name",
            "  parameters:",
            "    param1: value1",
            "  reason: |",
            "    Why this tool for next step",
            "    How this avoids previous issues",
            "```"
        ]
        
        prompt = "\n".join(prompt_parts)
        return self._get_llm_yaml_response(prompt)
    
    def _analyze_results(self, subtask_results: list, completed_reports: list) -> Dict[str, Any]:
        """Analyze results from all subtasks and provide final conclusion"""
        # Build subtask results section
        subtask_sections = []
        for i, result in enumerate(subtask_results):
            subtask_sections.extend([
                f"Subtask {i+1}:",
                f"Description: {result['subtask'].get('description')}",
                f"Success: {result['result'].get('success')}",
                f"Result: {result['result'].get('result')}",
                ""
            ])
        
        prompt_parts = [
            "# Task Report Generation",
            "",
            "## Original Task",
            self.current_task,
            "",
            "## Execution Results",
            *subtask_sections,
            "",
            "## Report Requirements",
            "1. CLEAR CONCLUSION",
            "  • Direct answer to original task",
            "  • Unambiguous status for each item",
            "  • No unexplained results",
            "",
            "2. SUPPORTING DATA",
            "   Real-time execution results",
            "  • Actual measurements/values",
            "  • Error messages if any",
            "",
            "3. EVIDENCE CHAIN",
            "  • Link data to conclusions",
            "  • Explain result interpretation",
            "  • Support each finding",
            "",
            "## Response Format",
            "```yaml",
            "task_report:",
            "  conclusion: |",
            "    Clear and complete answer to the original task.",
            "    Must be understandable on its own.",
            "",
            "  findings:",
            "    - item: Item being checked",
            "      status: Current status",
            "      data: Actual measurements/values",
            "      timestamp: When this was checked",
            "",
            "  evidence:",
            "    - type: Type of evidence",
            "      data: Raw data/measurements",
            "      source: Where this came from",
            "",
            "  execution_summary:",
            "    success: true/false",
            "    total_steps: number",
            "    completed_steps: number",
            "    error_count: number",
            "",
            "  issues:  # Only if relevant",
            "    - type: Issue type",
            "      description: Issue details",
            "      impact: How it affects results",
            "```",
            "",
            "## Example Report:",
            "```yaml",
            "task_report:",
            "  conclusion: |",
            "    Command execution completed with mixed results.",
            "    Operation A succeeded with value X.",
            "    Operation B failed due to Y.",
            "",
            "  findings:",
            "    - item: Operation A",
            "      status: success",
            "      data: 'value=X, time=123ms'",
            "      timestamp: '2024-01-01 12:00:00'",
            "",
            "  evidence:",
            "    - type: execution_result",
            "      data: 'stdout: ..., returncode: 0'",
            "      source: 'tool_execution'",
            "",
            "  execution_summary:",
            "    success: true",
            "    total_steps: 2",
            "    completed_steps: 2",
            "    error_count: 0",
            "```"
        ]
        
        prompt = "\n".join(prompt_parts)
        return self._get_llm_yaml_response(prompt)
    
    def _print_task_report(self, report: Dict[str, Any], task_type: str = "Task"):
        """Print formatted task report"""
        if not report or "task_report" not in report:
            return
        
        task_report = report["task_report"]
        
        # Print header
        self.logger.info(f"\n{Fore.BLUE}📋 {task_type} Report:{Style.RESET_ALL}")
        
        # Print conclusion
        if conclusion := task_report.get("conclusion"):
            self.logger.info(f"\n{Fore.GREEN}📝 Conclusion:{Style.RESET_ALL}")
            for line in conclusion.splitlines():
                if line.strip():
                    self.logger.info(f"{Fore.GREEN}  {line}{Style.RESET_ALL}")
        
        # Print evidence
        if evidence := task_report.get("evidence"):
            self.logger.info(f"\n{Fore.YELLOW}📌 Evidence:{Style.RESET_ALL}")
            for item in evidence:
                if isinstance(item, str):
                    self.logger.info(f"{Fore.YELLOW}  • {item}{Style.RESET_ALL}")
    
    def _validate_analysis_response(self, result: Dict[str, Any]) -> bool:
        """Validate analysis response format"""
        # Validate required sections
        if "result_analysis" not in result:
            self.logger.error(f"{Fore.RED}❌ Invalid response: Missing result_analysis section{Style.RESET_ALL}")
            return False
        
        if "task_progress" not in result:
            self.logger.error(f"{Fore.RED}❌ Invalid response: Missing task_progress section{Style.RESET_ALL}")
            return False
        
        # Validate result_analysis section
        result_analysis = result["result_analysis"]
        required_fields = ["success", "useful_data_found", "next_step_needed"]
        if not all(field in result_analysis for field in required_fields):
            self.logger.error(f"{Fore.RED}❌ Invalid response: Missing required fields in result_analysis{Style.RESET_ALL}")
            return False
        
        # Validate task_progress section
        task_progress = result["task_progress"]
        required_fields = ["has_required_info", "can_proceed", "completion_status"]
        if not all(field in task_progress for field in required_fields):
            self.logger.error(f"{Fore.RED}❌ Invalid response: Missing required fields in task_progress{Style.RESET_ALL}")
            return False
        
        return True