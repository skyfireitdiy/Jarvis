from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType, load_env_from_file

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

def main():
    """主函数"""
    import argparse

    load_env_from_file()
    
    parser = argparse.ArgumentParser(description='Jarvis AI Platform')
    parser.add_argument('--list', '-l', action='store_true', help='列出支持的平台和模型')
    
    args = parser.parse_args()
    
    if args.list:
        list_platforms()
    else:
        # 这里可以添加其他功能
        pass

if __name__ == "__main__":
    main()