from datetime import datetime
from colorama import Fore, Style, Back

class ColorLogger:
    """Logger with color support"""
    
    def __init__(self):
        # Define color schemes for different message categories
        self.color_schemes = {
            'TASK': {
                'header': Fore.GREEN + Style.BRIGHT,
                'prefix': '🎯 Task'
            },
            'ANALYSIS': {
                'header': Fore.BLUE + Style.BRIGHT,
                'prefix': '🔍 Analysis'
            },
            'PLAN': {
                'header': Fore.CYAN + Style.BRIGHT,
                'prefix': '📋 Plan'
            },
            'STEP': {
                'header': Fore.MAGENTA + Style.BRIGHT,
                'prefix': '🔨 Step'
            },
            'RESULT': {
                'header': Fore.YELLOW + Style.BRIGHT,
                'prefix': '📊 Result'
            },
            'ERROR': {
                'header': Fore.RED + Style.BRIGHT,
                'prefix': '❌ Error'
            },
            'RETRY': {
                'header': Fore.YELLOW + Style.BRIGHT,
                'prefix': '🔄 Retry'
            },
            'DONE': {
                'header': Fore.GREEN + Style.BRIGHT,
                'prefix': '✅ Done'
            },
            'CONCLUSION': {
                'header': Fore.GREEN + Style.BRIGHT,
                'prefix': '🎉 Conclusion'
            },
            'LLM-REQUEST': {
                'header': Fore.CYAN,
                'prefix': '• LLM-REQUEST'
            },
            'LLM-RESPONSE': {
                'header': Fore.YELLOW,
                'prefix': '• LLM-RESPONSE'
            },
            'ANALYSIS-RESULT': {
                'header': Fore.BLUE,
                'prefix': '• ANALYSIS-RESULT'
            },
            'ANALYSIS-ERROR': {
                'header': Fore.RED,
                'prefix': '• ANALYSIS-ERROR'
            },
            'TOOL-ANALYSIS': {
                'header': Fore.MAGENTA,
                'prefix': '• TOOL-ANALYSIS'
            },
            'TOOL-SUMMARY': {
                'header': Fore.CYAN,
                'prefix': '• TOOL-SUMMARY'
            }
        }
        
        # Default color scheme for unknown categories
        self.default_scheme = {
            'header': Fore.WHITE + Style.BRIGHT,
            'prefix': '• Info'
        }
    
    def _format_message(self, category: str, message: str, is_error: bool = False) -> str:
        """Format message with timestamp and category"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Get color scheme for category
        scheme = self.color_schemes.get(category, self.default_scheme)
        
        # Add indentation for better readability
        indent = "  " if category in ['ANALYSIS', 'PLAN', 'STEP', 'RESULT'] else ""
        
        # Format the header with color
        header = f"{scheme['header']}{scheme['prefix']}{Style.RESET_ALL}"
        
        # For errors, add red background
        if is_error:
            message = f"{Back.RED}{Fore.WHITE}{message}{Style.RESET_ALL}"
        
        return f"[{timestamp}] {header}: {indent}{message}"
    
    def log(self, category: str, message: str, is_error: bool = False):
        """Log a message with category"""
        formatted = self._format_message(category, message, is_error)
        print(formatted)
        
    def log_model_interaction(self, prompt: str, response: str):
        """Log model interaction with color"""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        print(f"{timestamp} {self.COLORS['BLUE']}[MODEL_IN]{self.COLORS['END']} {prompt}")
        print(f"{timestamp} {self.COLORS['CYAN']}[MODEL_OUT]{self.COLORS['END']} {response}") 