from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType, load_env_from_file, get_multiline_input

def list_platforms():
    """列出所有支持的平台和模型"""
    registry = PlatformRegistry.get_global_platform_registry()
    platforms = registry.get_available_platforms()
    
    PrettyOutput.section("支持的平台和模型", OutputType.SUCCESS)
    
    for platform_name in platforms:
        # 创建平台实例
        platform = registry.create_platform(platform_name)
        if not platform:
            continue
            
        # 获取平台支持的模型列表
        try:
            models = platform.get_model_list()
            
            # 打印平台名称
            PrettyOutput.section(f"{platform_name}", OutputType.SUCCESS)
            
            # 打印模型列表
            if models:
                for model_name, description in models:
                    if description:
                        PrettyOutput.print(f"  • {model_name} - {description}", OutputType.SUCCESS)
                    else:
                        PrettyOutput.print(f"  • {model_name}", OutputType.SUCCESS)
            else:
                PrettyOutput.print("  没有可用的模型信息", OutputType.WARNING)
                
        except Exception as e:
            PrettyOutput.print(f"获取 {platform_name} 平台模型列表失败: {str(e)}", OutputType.ERROR)

def chat_with_model(platform_name: str, model_name: str):
    """与指定平台和模型进行对话"""
    registry = PlatformRegistry.get_global_platform_registry()
    
    # 创建平台实例
    platform = registry.create_platform(platform_name)
    if not platform:
        PrettyOutput.print(f"创建平台 {platform_name} 失败", OutputType.ERROR)
        return
    
    try:
        # 设置模型
        platform.set_model_name(model_name)
        PrettyOutput.print(f"已连接到 {platform_name} 平台的 {model_name} 模型", OutputType.SUCCESS)
        
        # 开始对话循环
        while True:
            # 获取用户输入
            user_input = get_multiline_input("")
            
            # 检查是否取消输入
            if user_input == "__interrupt__":
                break
                
            # 检查是否为空输入
            if not user_input.strip():
                continue
                
            try:
                # 发送到模型并获取回复
                response = platform.chat(user_input)
                if not response:
                    PrettyOutput.print("未获得有效回复", OutputType.WARNING)
                    
            except Exception as e:
                PrettyOutput.print(f"对话失败: {str(e)}", OutputType.ERROR)
                
    except Exception as e:
        PrettyOutput.print(f"初始化对话失败: {str(e)}", OutputType.ERROR)
    finally:
        # 清理资源
        try:
            platform.delete_chat()
        except:
            pass

def info_command(args):
    """处理 info 子命令"""
    list_platforms()

def chat_command(args):
    """处理 chat 子命令"""
    if not args.platform or not args.model:
        PrettyOutput.print("请指定平台和模型。使用 'jarvis info' 查看可用的平台和模型。", OutputType.ERROR)
        return
    chat_with_model(args.platform, args.model)

def main():
    """主函数"""
    import argparse

    load_env_from_file()
    
    parser = argparse.ArgumentParser(description='Jarvis AI Platform')
    subparsers = parser.add_subparsers(dest='command', help='可用的子命令')
    
    # info 子命令
    info_parser = subparsers.add_parser('info', help='显示支持的平台和模型信息')
    
    # chat 子命令
    chat_parser = subparsers.add_parser('chat', help='与指定的平台和模型进行对话')
    chat_parser.add_argument('--platform', '-p', help='指定要使用的平台')
    chat_parser.add_argument('--model', '-m', help='指定要使用的模型')
    
    args = parser.parse_args()
    
    if args.command == 'info':
        info_command(args)
    elif args.command == 'chat':
        chat_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()