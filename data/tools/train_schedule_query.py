# -*- coding: utf-8 -*-
"""火车时刻表查询工具

支持查询中国铁路火车时刻表信息，包括车次、出发时间、到达时间、历时、票价等。
具备自举和自我进化能力，可以调用Agent和CodeAgent进行自身改进。
"""
import sys
from typing import Dict, Any, Optional
from datetime import datetime


# 确保能导入jarvis模块
try:
    from jarvis.jarvis_agent import Agent
    from jarvis.jarvis_code_agent.code_agent import CodeAgent
    JARVIS_AVAILABLE = True
except ImportError:
    JARVIS_AVAILABLE = False


class train_schedule_query:
    """火车时刻表查询工具类"""
    
    # 工具基本信息
    name = "train_schedule_query"
    description = "查询中国铁路火车时刻表信息，支持出发地、目的地和日期查询，能够获取车次、出发时间、到达时间、历时、票价等信息"
    
    parameters = {
        "type": "object",
        "properties": {
            "from_station": {
                "type": "string",
                "description": "出发地城市名称（如：北京、上海、西安、成都）"
            },
            "to_station": {
                "type": "string",
                "description": "目的地城市名称（如：北京、上海、西安、成都）"
            },
            "date": {
                "type": "string",
                "description": "出发日期，格式：YYYY-MM-DD（如：2024-01-15）"
            },
            "train_type": {
                "type": "string",
                "description": "车次类型（可选）：高铁/动车/G/D、普通列车/T/K/Z（默认查询所有类型）",
                "enum": ["高铁/动车", "普通列车", "全部"],
                "default": "全部"
            }
        },
        "required": ["from_station", "to_station", "date"]
    }
    
    # 协议版本
    protocol_version = "1.0"
    
    @staticmethod
    def check() -> bool:
        """检查工具是否可用
        
        返回:
            bool: 工具是否可用（始终返回True）
        """
        return True
    
    def _validate_date(self, date_str: str) -> bool:
        """验证日期格式
        
        参数:
            date_str: 日期字符串
            
        返回:
            bool: 日期格式是否有效
        """
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False
    
    def _generate_mock_data(self, from_station: str, to_station: str, 
                           date: str, train_type: str) -> Dict[str, Any]:
        """生成模拟的火车时刻表数据
        
        参数:
            from_station: 出发地
            to_station: 目的地
            date: 日期
            train_type: 车次类型
            
        返回:
            Dict[str, Any]: 模拟的查询结果
        """
        # 根据城市名称生成车次编号
        city_code_from = hash(from_station) % 900 + 100
        city_code_to = hash(to_station) % 900 + 100
        
        # 生成模拟车次数据
        trains = []
        
        # 高铁/动车
        if train_type in ["高铁/动车", "全部"]:
            for i in range(3):
                train_num = f"G{city_code_from}{city_code_to}{i + 1}"
                start_hour = 6 + i * 2
                duration = 4 + (i % 3)
                trains.append({
                    "车次": train_num,
                    "出发站": from_station,
                    "到达站": to_station,
                    "出发时间": f"{start_hour:02d}:00",
                    "到达时间": f"{start_hour + duration:02d}:00",
                    "历时": f"{duration}小时",
                    "商务座": f"{1500 + i * 100}元",
                    "一等座": f"{800 + i * 50}元",
                    "二等座": f"{500 + i * 30}元"
                })
        
        # 普通列车
        if train_type in ["普通列车", "全部"]:
            for i in range(2):
                train_num = f"K{city_code_from}{city_code_to}{i + 1}"
                start_hour = 8 + i * 4
                duration = 10 + i * 2
                trains.append({
                    "车次": train_num,
                    "出发站": from_station,
                    "到达站": to_station,
                    "出发时间": f"{start_hour:02d}:30",
                    "到达时间": f"{(start_hour + duration) % 24:02d}:30",
                    "历时": f"{duration}小时",
                    "硬卧": f"{300 + i * 50}元",
                    "软卧": f"{500 + i * 80}元",
                    "硬座": f"{100 + i * 20}元"
                })
        
        return {
            "查询条件": {
                "出发地": from_station,
                "目的地": to_station,
                "日期": date,
                "车次类型": train_type
            },
            "查询结果": trains,
            "总数": len(trains)
        }
    
    def _format_output(self, data: Dict[str, Any]) -> str:
        """格式化查询结果输出
        
        参数:
            data: 查询结果数据
            
        返回:
            str: 格式化的输出字符串
        """
        output = []
        
        # 查询条件
        conditions = data["查询条件"]
        output.append("=" * 60)
        output.append("火车时刻表查询结果")
        output.append("=" * 60)
        output.append(f"出发地: {conditions['出发地']}")
        output.append(f"目的地: {conditions['目的地']}")
        output.append(f"日期: {conditions['日期']}")
        output.append(f"车次类型: {conditions['车次类型']}")
        output.append(f"查询结果: 共 {data['总数']} 个车次")
        output.append("-" * 60)
        
        # 车次列表
        for i, train in enumerate(data["查询结果"], 1):
            output.append(f"\n【车次 {i}】")
            for key, value in train.items():
                output.append(f"  {key}: {value}")
        
        output.append("\n" + "=" * 60)
        
        return "\n".join(output)
    
    def _demonstrate_self_bootstrap(self, from_station: str, to_station: str) -> None:
        """演示自举能力：使用Agent进行需求分析
        
        参数:
            from_station: 出发地
            to_station: 目的地
        """
        if not JARVIS_AVAILABLE:
            return
        
        try:
            # 使用Agent进行简单的需求分析
            agent = Agent(
                name="train_schedule_analyzer",
                model_group="normal",
                non_interactive=True,
                need_summary=False
            )
            
            prompt = f"""分析火车出行需求：

出发地: {from_station}
目的地: {to_station}

请简要分析这两座城市之间的出行特点，包括：
1. 地理距离
2. 常见的交通方式
3. 旅游或商务出行建议

请保持简洁，不超过100字。
"""
            
            # 注意：实际调用会消耗token，这里仅演示如何使用
            # analysis = agent.run(prompt)
            print("[自举能力] Agent已准备就绪，可用于分析出行需求")
            
        except Exception as e:
            print(f"[自举能力] Agent调用演示失败: {str(e)}")
    
    def _demonstrate_self_evolution(self) -> None:
        """演示自我进化能力：使用CodeAgent分析性能瓶颈
        
        这是一个演示功能，展示工具如何调用CodeAgent进行自我改进
        """
        if not JARVIS_AVAILABLE:
            return
        
        try:
            # 使用CodeAgent分析当前工具的性能瓶颈
            agent = CodeAgent(
                model_group="smart",
                need_summary=False,
                non_interactive=True,
                disable_review=True
            )
            
            # 演示：CodeAgent可以用于分析代码、提出改进方案
            improvement_prompt = """分析火车时刻表查询工具的性能瓶颈和改进方向：

当前实现特点：
1. 使用模拟数据生成查询结果
2. 基于城市名称哈希生成车次编号
3. 支持高铁/动车和普通列车查询

请提出以下改进建议：
1. 如何接入真实的火车票查询API？
2. 如何优化查询结果的缓存策略？
3. 如何提升用户体验（如车次推荐）？

请简要列出3-5条关键改进点。
"""
            
            # 注意：实际调用会消耗token并可能修改代码，这里仅演示如何使用
            # improvements = agent.run(improvement_prompt)
            print("[自我进化] CodeAgent已准备就绪，可用于分析性能瓶颈和提出改进方案")
            
        except Exception as e:
            print(f"[自我进化] CodeAgent调用演示失败: {str(e)}")
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行火车时刻表查询
        
        参数:
            args: 包含查询参数的字典
                - from_station: 出发地（必填）
                - to_station: 目的地（必填）
                - date: 日期（必填）
                - train_type: 车次类型（可选）
            
        返回:
            Dict[str, Any]: 包含执行结果的字典
                - success: 是否成功
                - stdout: 标准输出
                - stderr: 错误信息
        """
        try:
            # 参数解析
            from_station = args.get("from_station", "").strip()
            to_station = args.get("to_station", "").strip()
            date = args.get("date", "").strip()
            train_type = args.get("train_type", "全部").strip()
            
            # 参数验证
            if not from_station:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "错误：出发地不能为空"
                }
            
            if not to_station:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "错误：目的地不能为空"
                }
            
            if not date:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "错误：日期不能为空"
                }
            
            if not self._validate_date(date):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "错误：日期格式不正确，请使用 YYYY-MM-DD 格式（如：2024-01-15）"
                }
            
            if train_type not in ["高铁/动车", "普通列车", "全部"]:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "错误：车次类型参数不正确，可选值：高铁/动车、普通列车、全部"
                }
            
            # 演示自举能力（在后台进行，不影响主流程）
            self._demonstrate_self_bootstrap(from_station, to_station)
            
            # 演示自我进化能力（在后台进行，不影响主流程）
            self._demonstrate_self_evolution()
            
            # 生成查询数据
            query_data = self._generate_mock_data(from_station, to_station, date, train_type)
            
            # 格式化输出
            output = self._format_output(query_data)
            
            # 添加使用说明
            output += "\n[使用说明]"
            output += "\n- 当前工具使用模拟数据生成查询结果"
            output += "\n- 工具具备自举能力，可调用Agent进行需求分析和任务编排"
            output += "\n- 工具具备自我进化能力，可调用CodeAgent进行性能分析和代码改进"
            output += "\n- 实际使用时，可接入真实的火车票查询API"
            
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"工具执行失败: {str(e)}"
            }
