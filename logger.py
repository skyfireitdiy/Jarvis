from datetime import datetime

class ColorLogger:
    """Colored console logger"""
    
    COLORS = {
        'HEADER': '\033[95m',      # Purple
        'BLUE': '\033[94m',        # Blue
        'CYAN': '\033[96m',        # Cyan
        'GREEN': '\033[92m',       # Green
        'YELLOW': '\033[93m',      # Yellow
        'RED': '\033[91m',         # Red
        'BOLD': '\033[1m',         # Bold
        'UNDERLINE': '\033[4m',    # Underline
        'END': '\033[0m'           # Reset
    }
    
    ICONS = {
        'TASK': '🎯',
        'ANALYSIS': '🔍',
        'PLAN': '📋',
        'STEP': '▶️',
        'RESULT': '📊',
        'RETRY': '🔄',
        'ERROR': '❌',
        'DONE': '✅',
        'CONCLUSION': '🏁'
    }
    
    STYLES = {
        'TASK': COLORS['BOLD'] + COLORS['CYAN'],
        'ANALYSIS': COLORS['BLUE'],
        'PLAN': COLORS['YELLOW'],
        'STEP': COLORS['GREEN'],
        'RESULT': COLORS['CYAN'],
        'RETRY': COLORS['YELLOW'],
        'ERROR': COLORS['RED'],
        'DONE': COLORS['GREEN'],
        'CONCLUSION': COLORS['BOLD'] + COLORS['GREEN']
    }
    
    def _format_message(self, category: str, message: str, is_error: bool = False) -> str:
        """Format message with color and icon"""
        timestamp = self._get_timestamp()
        style = self.STYLES.get(category, '')
        icon = self.ICONS.get(category, '•')
        
        # Special formatting for different categories
        if category == 'TASK':
            header = f"{style}{icon} Task{self.COLORS['END']}"
            message = f"{self.COLORS['BOLD']}{message}{self.COLORS['END']}"
        elif category == 'ANALYSIS':
            header = f"{style}{icon} Analysis{self.COLORS['END']}"
            if message.startswith("Status:"):
                message = f"{self.COLORS['BOLD']}{message}{self.COLORS['END']}"
        elif category == 'CONCLUSION':
            header = f"{style}{icon} Conclusion{self.COLORS['END']}"
            if message.startswith("Final conclusion:"):
                message = f"{self.COLORS['BOLD']}{message}{self.COLORS['END']}"
            elif message.startswith("Evidence:"):
                message = f"{self.COLORS['UNDERLINE']}{message}{self.COLORS['END']}"
        elif category == 'PLAN':
            header = f"{style}{icon} Plan{self.COLORS['END']}"
            if message.startswith("Success criteria:"):
                message = f"{self.COLORS['CYAN']}{message}{self.COLORS['END']}"
        elif category == 'RESULT':
            header = f"{style}{icon} Result{self.COLORS['END']}"
            message = f"{self.COLORS['CYAN']}{message}{self.COLORS['END']}"
        elif category == 'ERROR':
            header = f"{self.COLORS['RED']}{icon} Error{self.COLORS['END']}"
            message = f"{self.COLORS['RED']}{message}{self.COLORS['END']}"
        else:
            header = f"{style}{icon} {category}{self.COLORS['END']}"
        
        # Add indentation for better readability
        indent = "  " if category in ['ANALYSIS', 'PLAN', 'STEP', 'RESULT'] else ""
        
        return f"{timestamp} {header}: {indent}{message}"
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        return f"{self.COLORS['BOLD']}[{datetime.now().strftime('%H:%M:%S')}]{self.COLORS['END']}"
    
    def log(self, category: str, message: str, is_error: bool = False):
        """Log a message with color and formatting"""
        print(self._format_message(category.upper(), message, is_error))
        
    def log_model_interaction(self, prompt: str, response: str):
        """Log model interaction with color"""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        print(f"{timestamp} {self.COLORS['BLUE']}[MODEL_IN]{self.COLORS['END']} {prompt}")
        print(f"{timestamp} {self.COLORS['CYAN']}[MODEL_OUT]{self.COLORS['END']} {response}") 