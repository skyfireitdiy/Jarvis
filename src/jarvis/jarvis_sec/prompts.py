# -*- coding: utf-8 -*-
"""提示词构建模块"""

from jarvis.jarvis_utils.tag import ot


def build_summary_prompt() -> str:
    """
    构建摘要提示词：要求以 <REPORT>...</REPORT> 包裹的 JSON 输出（仅JSON）。
    系统提示词不强制规定主对话输出格式，仅在摘要中给出结构化结果。
    """
    return """
请将本轮"安全子任务（单点验证）"的结构化结果仅放入以下标记中，并使用 JSON 数组对象形式输出。
仅输出全局编号（gid）与详细理由（不含位置信息），gid 为全局唯一的数字编号。

示例1：有告警的情况（has_risk: true，单个gid）
<REPORT>
[
  {
    "gid": 1,
    "has_risk": true,
    "preconditions": "输入字符串 src 的长度大于等于 dst 的缓冲区大小",
    "trigger_path": "调用路径推导：main() -> handle_network_request() -> parse_packet() -> foobar() -> strcpy()。数据流：网络数据包通过 handle_network_request() 接收，传递给 parse_packet() 解析，parse_packet() 未对数据长度进行校验，直接将 src 传递给 foobar()，foobar() 调用 strcpy(dst, src) 时未检查 src 长度，可导致缓冲区溢出。关键调用点：parse_packet() 函数未对输入长度进行校验。",
    "consequences": "缓冲区溢出，可能引发程序崩溃或任意代码执行",
    "suggestions": "使用 strncpy_s 或其他安全的字符串复制函数"
  }
]
</REPORT>

示例2：有告警的情况（has_risk: true，多个gid合并，路径和原因一致）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "has_risk": true,
    "preconditions": "输入字符串 src 的长度大于等于 dst 的缓冲区大小",
    "trigger_path": "调用路径推导：main() -> handle_network_request() -> parse_packet() -> foobar() -> strcpy()。数据流：网络数据包通过 handle_network_request() 接收，传递给 parse_packet() 解析，parse_packet() 未对数据长度进行校验，直接将 src 传递给 foobar()，foobar() 调用 strcpy(dst, src) 时未检查 src 长度，可导致缓冲区溢出。关键调用点：parse_packet() 函数未对输入长度进行校验。",
    "consequences": "缓冲区溢出，可能引发程序崩溃或任意代码执行",
    "suggestions": "使用 strncpy_s 或其他安全的字符串复制函数"
  }
]
</REPORT>

示例3：误报或无问题（返回空数组）
<REPORT>
[]
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 JSON 数组，且不得出现其他文本。
- 若确认本批次全部为误报或无问题，请返回空数组 []。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号，单个告警时使用）
  - gids: 整数数组（全局唯一编号数组，多个告警合并时使用）
  - has_risk: 布尔值 (true/false)，表示该项是否存在真实安全风险。
  - preconditions: 字符串（触发漏洞的前置条件，仅当 has_risk 为 true 时必需）
  - trigger_path: 字符串（漏洞的触发路径，必须包含完整的调用路径推导，包括：1) 可控输入的来源；2) 从输入源到缺陷代码的完整调用链（函数调用序列）；3) 每个调用点的数据校验情况；4) 触发条件。格式示例："调用路径推导：函数A() -> 函数B() -> 函数C() -> 缺陷代码。数据流：输入来源 -> 传递路径。关键调用点：函数B()未做校验。"，仅当 has_risk 为 true 时必需）
  - consequences: 字符串（漏洞被触发后可能导致的后果，仅当 has_risk 为 true 时必需）
  - suggestions: 字符串（修复或缓解该漏洞的建议，仅当 has_risk 为 true 时必需）
- **合并格式优化**：如果多个告警（gid）的路径（trigger_path）、原因（preconditions/consequences/suggestions）完全一致，可以使用 gids 数组格式合并输出，减少重复内容。单个告警使用 gid，多个告警合并使用 gids。gid 和 gids 不能同时出现。
- 不要在数组元素中包含 file/line/pattern 等位置信息；写入 jsonl 时系统会结合原始候选信息。
- **关键**：仅当 `has_risk` 为 `true` 时，才会被记录为确认的问题。对于确认是误报的条目，请确保 `has_risk` 为 `false` 或不输出该条目。
- **输出格式**：有告警的条目必须包含所有字段（gid 或 gids, has_risk, preconditions, trigger_path, consequences, suggestions）；无告警的条目只需包含 gid 和 has_risk。
- **调用路径推导要求**：trigger_path 字段必须包含完整的调用路径推导，不能省略或简化。必须明确说明从可控输入到缺陷代码的完整调用链，以及每个调用点的校验情况。如果无法推导出完整的调用路径，应该判定为误报（has_risk: false）。
- 支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。
""".strip()


def build_verification_summary_prompt() -> str:
    """
    构建验证 Agent 的摘要提示词：验证分析 Agent 给出的结论是否正确。
    """
    return """
请将本轮"验证分析结论"的结构化结果仅放入以下标记中，并使用 JSON 数组对象形式输出。
你需要验证分析 Agent 给出的结论是否正确，包括前置条件、触发路径、后果和建议是否合理。

示例1：验证通过（is_valid: true，单个gid）
<REPORT>
[
  {
    "gid": 1,
    "is_valid": true,
    "verification_notes": "分析结论正确，前置条件合理，触发路径清晰，后果评估准确"
  }
]
</REPORT>

示例2：验证通过（is_valid: true，多个gid合并）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "is_valid": true,
    "verification_notes": "分析结论正确，前置条件合理，触发路径清晰，后果评估准确"
  }
]
</REPORT>

示例3：验证不通过（is_valid: false）
<REPORT>
[
  {
    "gid": 1,
    "is_valid": false,
    "verification_notes": "前置条件过于宽泛，实际代码中已有输入校验，触发路径不成立"
  }
]
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 JSON 数组，且不得出现其他文本。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号，对应分析 Agent 给出的 gid，单个告警时使用）
  - gids: 整数数组（全局唯一编号数组，对应分析 Agent 给出的 gids，多个告警合并时使用）
  - is_valid: 布尔值 (true/false)，表示分析 Agent 的结论是否正确
  - verification_notes: 字符串（验证说明，解释为什么结论正确或不正确）
- **合并格式优化**：如果多个告警（gid）的验证结果（is_valid）和验证说明（verification_notes）完全一致，可以使用 gids 数组格式合并输出，减少重复内容。单个告警使用 gid，多个告警合并使用 gids。gid 和 gids 不能同时出现。
- 必须对所有输入的 gid 进行验证，不能遗漏。
- 如果验证通过（is_valid: true），则保留该告警；如果验证不通过（is_valid: false），则视为误报，不记录为问题。
- 支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。
""".strip()


def get_review_system_prompt() -> str:
    """获取复核Agent的系统提示词"""
    return f"""
# 复核Agent约束
- 你的核心任务是复核聚类Agent给出的无效结论是否充分和正确。
- 你需要仔细检查聚类Agent提供的invalid_reason是否充分，是否真的考虑了所有可能的路径。
- 工具优先：使用 read_code 读取目标文件附近源码（行号前后各 ~50 行），必要时用 execute_script 辅助检索。
- 必要时需向上追溯调用者，查看完整的调用路径，以确认聚类Agent的结论是否成立。
- 禁止修改任何文件或执行写操作命令；仅进行只读分析与读取。
- 每次仅执行一个操作；等待工具结果后再进行下一步。
- **记忆使用**：
  - 在复核过程中，充分利用 retrieve_memory 工具检索已有的记忆，特别是与当前文件或函数相关的记忆。
  - 这些记忆可能包含函数的分析要点、指针判空情况、输入校验情况、调用路径分析结果等。
- **复核原则**：
  - 必须验证聚类Agent是否真的检查了所有可能的调用路径和调用者。
  - 必须验证聚类Agent是否真的确认了所有路径都有保护措施。
  - 如果发现聚类Agent遗漏了某些路径、调用者或边界情况，必须判定为理由不充分。
  - 保守策略：有疑问时，一律判定为理由不充分，将候选重新加入验证流程。
- 完成复核后，主输出仅打印结束符 {ot("!!!COMPLETE!!!")}，不要输出其他任何内容。任务总结将会在后面的交互中被询问。
    """.strip()


def get_review_summary_prompt() -> str:
    """获取复核Agent的摘要提示词"""
    return """
请将本轮"复核结论"的结构化结果仅放入以下标记中，并使用 JSON 数组对象形式输出。
你需要复核聚类Agent给出的无效理由是否充分，是否真的考虑了所有可能的路径。

示例1：理由充分（is_reason_sufficient: true，单个gid）
<REPORT>
[
  {
    "gid": 1,
    "is_reason_sufficient": true,
    "review_notes": "聚类Agent已检查所有调用路径，确认所有调用者都有输入校验，理由充分"
  }
]
</REPORT>

示例2：理由充分（is_reason_sufficient: true，多个gid合并）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "is_reason_sufficient": true,
    "review_notes": "聚类Agent已检查所有调用路径，确认所有调用者都有输入校验，理由充分"
  }
]
</REPORT>

示例3：理由不充分（is_reason_sufficient: false）
<REPORT>
[
  {
    "gid": 1,
    "is_reason_sufficient": false,
    "review_notes": "聚类Agent遗漏了函数X的调用路径，该路径可能未做校验，理由不充分，需要重新验证"
  }
]
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 JSON 数组，且不得出现其他文本。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号，对应无效聚类的gid，单个告警时使用）
  - gids: 整数数组（全局唯一编号数组，对应无效聚类的gids，多个告警合并时使用）
  - is_reason_sufficient: 布尔值 (true/false)，表示无效理由是否充分
  - review_notes: 字符串（复核说明，解释为什么理由充分或不充分）
- **合并格式优化**：如果多个告警（gid）的复核结果（is_reason_sufficient）和复核说明（review_notes）完全一致，可以使用 gids 数组格式合并输出，减少重复内容。单个告警使用 gid，多个告警合并使用 gids。gid 和 gids 不能同时出现。
- 必须对所有输入的gid进行复核，不能遗漏。
- 如果理由不充分（is_reason_sufficient: false），该候选将重新加入验证流程；如果理由充分（is_reason_sufficient: true），该候选将被确认为无效。
- 支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。
    """.strip()


def get_cluster_system_prompt() -> str:
    """获取聚类Agent的系统提示词"""
    return """
# 单Agent聚类约束
- 你的任务是对同一文件内的启发式候选进行聚类，将可以一起验证的问题归为一类。
- **聚类原则**：
  - 可以一起验证的问题归为一类，不一定是验证条件完全一致才能归为一类。
  - 如果多个候选问题可以通过同一个验证过程来确认，即使它们的验证条件略有不同，也可以归为一类。
  - 例如：多个指针解引用问题可以归为一类（验证"指针在解引用前非空"），即使它们涉及不同的指针变量。
  - 例如：多个缓冲区操作问题可以归为一类（验证"拷贝长度不超过目标缓冲区容量"），即使它们涉及不同的缓冲区。
- 验证条件：为了确认是否存在漏洞需要成立/验证的关键前置条件。例如："指针p在解引用前非空""拷贝长度不超过目标缓冲区容量"等。
- **完整性要求**：每个gid都必须出现在某个类别中，不能遗漏任何一个gid。所有输入的gid都必须被分类。
- 工具优先：如需核对上下文，可使用 read_code 读取相邻代码；避免过度遍历。
- 禁止写操作；仅只读分析。
- **重要：关于无效判断的保守策略**：
  - 在判断候选是否无效时，必须充分考虑所有可能的路径、调用链和边界情况。
  - 必须考虑：所有可能的调用者、所有可能的输入来源、所有可能的执行路径、所有可能的边界条件。
  - 只要存在任何可能性（即使很小）导致漏洞可被触发，就不应该标记为无效（is_invalid: false）。
  - 只有在完全确定、没有任何可能性、所有路径都已验证安全的情况下，才能标记为无效（is_invalid: true）。
  - 保守原则：有疑问时，一律标记为 false（需要进入后续验证阶段），让分析Agent和验证Agent进行更深入的分析。
  - 不要因为看到局部有保护措施就认为无效，要考虑是否有其他调用路径绕过这些保护。
  - 不要因为看到某些调用者已做校验就认为无效，要考虑是否有其他调用者未做校验。
- **记忆使用**：
  - 在聚类过程中，充分利用 retrieve_memory 工具检索已有的记忆，特别是与当前文件或函数相关的记忆。
  - 如果有必要，使用 save_memory 工具保存聚类过程中发现的函数或代码片段的要点，使用函数名或文件名作为 tag。
  - 记忆内容示例：某个函数的指针已经判空、某个函数已有输入校验、某个代码片段的上下文信息等。
  - 这些记忆可以帮助后续的分析Agent和验证Agent更高效地工作。
    """.strip()


def get_cluster_summary_prompt() -> str:
    """获取聚类Agent的摘要提示词"""
    return """
请仅在 <CLUSTERS> 与 </CLUSTERS> 中输出 JSON 数组：
- 每个元素包含（所有字段均为必填）：
  - verification: 字符串（对该聚类的验证条件描述，简洁明确，可直接用于后续Agent验证）
  - gids: 整数数组（候选的全局唯一编号；输入JSON每个元素含 gid，可直接对应填入）
  - is_invalid: 布尔值（必填，true 或 false）。如果为 true，表示该聚类中的所有候选已被确认为无效/误报，将不会进入后续验证阶段；如果为 false，表示该聚类中的候选需要进入后续验证阶段。
  - invalid_reason: 字符串（当 is_invalid 为 true 时必填，当 is_invalid 为 false 时可省略）。必须详细说明为什么这些候选是无效的，包括：
    * 已检查的所有调用路径和调用者
    * 已确认的保护措施和校验逻辑
    * 为什么这些保护措施在所有路径上都有效
    * 为什么不存在任何可能的触发路径
    * 必须足够详细，以便复核Agent能够验证你的判断
- 要求：
  - 严格要求：仅输出位于 <CLUSTERS> 与 </CLUSTERS> 间的 JSON 数组，其他位置不输出任何文本
  - **完整性要求（最重要）**：输入JSON中的所有gid都必须被分类，不能遗漏任何一个gid。所有gid必须出现在某个聚类的gids数组中。这是强制要求，必须严格遵守。
  - **聚类原则**：可以一起验证的问题归为一类，不一定是验证条件完全一致才能归为一类。如果多个候选问题可以通过同一个验证过程来确认，即使它们的验证条件略有不同，也可以归为一类。
  - **必须要求**：每个聚类元素必须包含 is_invalid 字段，且值必须为 true 或 false，不能省略。
  - **必须要求**：当 is_invalid 为 true 时，必须提供 invalid_reason 字段，且理由必须充分详细。
  - 不需要解释与长文本，仅给出可执行的验证条件短句
  - 若无法聚类，请将每个候选单独成组，verification 为该候选的最小确认条件
  - **关于 is_invalid 的保守判断原则**：
    - 必须充分考虑所有可能的路径、调用链、输入来源和边界情况。
    - 只要存在任何可能性（即使很小）导致漏洞可被触发，必须设置 is_invalid: false。
    - 只有在完全确定、没有任何可能性、所有路径都已验证安全的情况下，才能设置 is_invalid: true。
    - 保守策略：有疑问时，一律设置为 false，让后续的分析Agent和验证Agent进行更深入的分析。
    - 不要因为局部有保护措施就设置为 true，要考虑是否有其他路径绕过保护。
    - 不要因为某些调用者已做校验就设置为 true，要考虑是否有其他调用者未做校验。
    - 如果设置为 true，必须在 invalid_reason 中详细说明已检查的所有路径和原因。
  - 支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。
<CLUSTERS>
[
  {
    "verification": "",
    "gids": [],
    "is_invalid": false
  }
]
</CLUSTERS>
    """.strip()
