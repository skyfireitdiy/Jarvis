from datetime import datetime
from colorama import Fore, Style
import re

class Logger:
    def __init__(self):
        self.thought_process = []
        self.timestamps = []
    
    def log(self, category: str, message: str, is_error: bool = False, prefix: bool = True):
        """Log a message with optional error highlighting and prefix control"""
        timestamp = datetime.now().strftime('[%H:%M:%S]')
        self.timestamps.append(timestamp)
        
        # 根据类别选择图标和颜色
        icons = {
            'TASK': (f"{Fore.MAGENTA}🎯", "Task"),
            'ANALYSIS': (f"{Fore.BLUE}🔍", "Analysis"),
            'EXECUTE': (f"{Fore.CYAN}🔧", "Execute"),
            'RESULT': (f"{Fore.GREEN}📊", "Result"),
            'RETRY': (f"{Fore.YELLOW}🔄", "Retry"),
            'ERROR': (f"{Fore.RED}❌", "Error"),
            'CONCLUSION': (f"{Fore.GREEN}🎉", "Conclusion"),
            'INFO': (f"{Fore.BLUE}•", "Info"),
            'LLM-REQUEST': (f"{Fore.CYAN}🤖", "Prompt"),
            'LLM-RESPONSE': (f"{Fore.MAGENTA}💭", "Response"),
            'STATUS': (f"{Fore.BLUE}📌", "Status"),
            'EVIDENCE': (f"{Fore.GREEN}📝", "Evidence"),
            'REFLECTION': (f"{Fore.YELLOW}🤔", "Reflection")
        }
        
        icon, label = icons.get(category, ("•", category))
        
        if not prefix:
            # 不显示时间戳前缀，但仍然显示类别标签
            print(f"{icon} {label}: {message}")
        else:
            # 显示完整前缀
            print(f"{timestamp} {icon} {label}: {message}")
        
        self.thought_process.append({
            'timestamp': timestamp,
            'category': category,
            'message': self._strip_ansi(message),
            'is_error': is_error
        })
    
    def _get_icon(self, category: str, is_error: bool = False) -> str:
        """Get icon for message category"""
        if is_error:
            return f"{Fore.RED}❌{Style.RESET_ALL}"
            
        icons = {
            'TASK': f"{Fore.MAGENTA}🎯{Style.RESET_ALL}",
            'ANALYSIS': f"{Fore.BLUE}🔍{Style.RESET_ALL}",
            'EXECUTE': f"{Fore.CYAN}🔧{Style.RESET_ALL}",
            'RESULT': f"{Fore.GREEN}📊{Style.RESET_ALL}",
            'RETRY': f"{Fore.YELLOW}🔄{Style.RESET_ALL}",
            'ERROR': f"{Fore.RED}❌{Style.RESET_ALL}",
            'CONCLUSION': f"{Fore.GREEN}🎉{Style.RESET_ALL}",
            'INFO': f"{Fore.BLUE}•{Style.RESET_ALL}",
            'LLM-REQUEST': f"{Fore.MAGENTA}🤖{Style.RESET_ALL}",
            'LLM-RESPONSE': f"{Fore.CYAN}•{Style.RESET_ALL}"
        }
        return icons.get(category, "•")
    
    def _strip_ansi(self, text: str) -> str:
        """Remove ANSI color codes from text"""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

class ColorLogger(Logger):
    """Logger with color support"""
    def __init__(self):
        super().__init__()
    
    def log(self, category: str, message: str, is_error: bool = False, prefix: bool = True):
        """Log a message with color support"""
        timestamp = datetime.now().strftime('[%H:%M:%S]')
        self.timestamps.append(timestamp)
        
        # 根据类别选择图标、颜色和标签
        icons = {
            'TASK': (f"{Fore.MAGENTA}🎯", "Task", Fore.MAGENTA),
            'ANALYSIS': (f"{Fore.BLUE}🔍", "Analysis", Fore.BLUE),
            'EXECUTE': (f"{Fore.CYAN}🔧", "Execute", Fore.CYAN),
            'RESULT': (f"{Fore.GREEN}📊", "Result", Fore.GREEN),
            'RETRY': (f"{Fore.YELLOW}🔄", "Retry", Fore.YELLOW),
            'ERROR': (f"{Fore.RED}❌", "Error", Fore.RED),
            'CONCLUSION': (f"{Fore.GREEN}🎉", "Conclusion", Fore.GREEN),
            'INFO': (f"{Fore.BLUE}•", "Info", Fore.BLUE),
            'LLM-REQUEST': (f"{Fore.CYAN}🤖", "Prompt", Fore.CYAN),
            'LLM-RESPONSE': (f"{Fore.MAGENTA}💭", "Response", Fore.MAGENTA),
            'STATUS': (f"{Fore.BLUE}📌", "Status", Fore.BLUE),
            'EVIDENCE': (f"{Fore.GREEN}📝", "Evidence", Fore.GREEN),
            'REFLECTION': (f"{Fore.YELLOW}🤔", "Reflection", Fore.YELLOW)
        }
        
        icon, label, color = icons.get(category, ("•", category, Fore.WHITE))
        
        if not prefix:
            # 不显示时间戳前缀，但仍然显示类别标签
            print(f"{icon} {color}{label}:{Style.RESET_ALL} {message}")
        else:
            # 显示完整前缀
            print(f"{timestamp} {icon} {color}{label}:{Style.RESET_ALL} {message}")
        
        self.thought_process.append({
            'timestamp': timestamp,
            'category': category,
            'message': self._strip_ansi(message),
            'is_error': is_error
        })