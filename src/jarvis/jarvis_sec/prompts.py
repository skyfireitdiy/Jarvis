# -*- coding: utf-8 -*-
"""提示词构建模块"""

from jarvis.jarvis_utils.tag import ot


def build_summary_prompt() -> str:
    """
    构建摘要提示词：要求以 <REPORT>...</REPORT> 包裹的 JSON 输出（仅JSON）。
    系统提示词不强制规定主对话输出格式，仅在摘要中给出结构化结果。
    """
    return """
本轮"安全子任务（单点验证）"的结构化结果，只写在下面标记内，用 JSON 数组对象的形式输出。
只输出全局编号（gid）与详细理由（不含位置信息）；gid 为全局唯一数字。

示例1：有告警（has_risk: true，单个 gid）
<REPORT>
[
  {
    "gid": 1,
    "has_risk": true,
    "preconditions": "输入字符串 src 的长度不小于 dst 缓冲区大小",
    "trigger_path": "调用路径：main() -> handle_network_request() -> parse_packet() -> foobar() -> strcpy()；parse_packet() 未校验长度，直接把 src 传给 foobar()，foobar() 调用 strcpy(dst, src) 未检查 src 长度，可能导致缓冲区溢出。关键调用点：parse_packet() 未校验输入长度。",
    "consequences": "缓冲区溢出，可能导致程序崩溃或任意代码执行",
    "suggestions": "使用 strncpy_s 或其他安全的字符串复制函数"
  }
]
</REPORT>

示例2：有告警（has_risk: true，多个 gid 合并，路径与理由一致）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "has_risk": true,
    "preconditions": "输入字符串 src 的长度不小于 dst 缓冲区大小",
    "trigger_path": "调用路径：main() -> handle_network_request() -> parse_packet() -> foobar() -> strcpy()；parse_packet() 未校验长度，直接把 src 传给 foobar()，foobar() 调用 strcpy(dst, src) 未检查 src 长度，可能导致缓冲区溢出。关键调用点：parse_packet() 未校验输入长度。",
    "consequences": "缓冲区溢出，可能导致程序崩溃或任意代码执行",
    "suggestions": "使用 strncpy_s 或其他安全的字符串复制函数"
  }
]
</REPORT>

示例3：误报或没有问题（返回空数组）
<REPORT>
[]
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 之间输出 JSON 数组，不得混入其他文字。
- 如果确认本批全部为误报或没有问题，返回空数组 []。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一，单个告警时使用）
  - gids: 整数数组（全局唯一，多个告警合并时使用）
  - has_risk: 布尔（true/false），表示该项是否存在真实安全风险。
  - preconditions: 字符串（触发漏洞的前置条件，仅当 has_risk 为 true 时必需）
  - trigger_path: 字符串（漏洞触发路径，必须包含完整的调用路径推导：1) 可控输入的来源；2) 从输入源到缺陷代码的完整调用链（函数调用序列）；3) 各调用点的数据校验情况；4) 触发条件。格式示例："调用路径推导：函数A() -> 函数B() -> 函数C() -> 缺陷代码。数据流：输入来源 -> 传递路径。关键调用点：函数B()未做校验。"，仅当 has_risk 为 true 时必需）
  - consequences: 字符串（漏洞触发后可能造成的后果，仅当 has_risk 为 true 时必需）
  - suggestions: 字符串（修复或缓解建议，仅当 has_risk 为 true 时必需）
- **合并优化**：如果多个告警（gid）的路径（trigger_path）与理由（preconditions/consequences/suggestions）完全一致，可以用 gids 数组合并，减少重复。单个告警用 gid，多个告警合并用 gids。gid 与 gids 不能同时出现。
- 不要在数组元素中混入 file/line/pattern 等位置信息；写 jsonl 时系统会自动合并原始候选。
- **关键**：只有 `has_risk` 为 `true` 的，才记录为确认的问题。确认是误报的，令 `has_risk` 为 `false` 或不输出该条。
- **输出格式**：有告警的条目，必须包含全部字段（gid 或 gids, has_risk, preconditions, trigger_path, consequences, suggestions）；无告警的条目，只包含 gid 与 has_risk。
- **调用路径推导要求**：trigger_path 必须包含完整的调用路径推导，不得省略精简。必须说明从可控输入到缺陷代码的完整调用链，以及各调用点的校验情况。如果不能推导出完整调用路径，应判定为误报（has_risk: false）。
""".strip()


def build_verification_summary_prompt() -> str:
    """
    构建验证 Agent 的摘要提示词：验证分析 Agent 给出的结论是否正确。
    """
    return """
本轮"验证分析结论"的结构化结果，只写在下面标记内，用 JSON 数组对象的形式输出。
你需要验证分析 Agent 给出的结论是否正确，包括前置条件、触发路径、后果与建议是否合理。

示例1：验证通过（is_valid: true，单个 gid）
<REPORT>
[
  {
    "gid": 1,
    "is_valid": true,
    "verification_notes": "分析结论正确，前置条件合理，触发路径清晰，后果评估准确"
  }
]
</REPORT>

示例2：验证通过（is_valid: true，多个 gid 合并）
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
- 只能在 <REPORT> 与 </REPORT> 之间输出 JSON 数组，不得混入其他文字。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一，对应分析 Agent 给出的 gid，单个告警时使用）
  - gids: 整数数组（全局唯一，对应分析 Agent 给出的 gids，多个告警合并时使用）
  - is_valid: 布尔（true/false），表示分析 Agent 的结论是否正确
  - verification_notes: 字符串（验证说明，解释为什么正确或不正确）
- **合并优化**：如果多个告警（gid）的验证结果（is_valid）与验证说明（verification_notes）完全一致，可以用 gids 数组合并，减少重复。单个告警用 gid，多个告警合并用 gids。gid 与 gids 不能同时出现。
- 必须验证所有输入的 gid，不得遗漏。
- 如果验证通过（is_valid: true），则保留该告警；如果不通过（is_valid: false），视为误报，不记录为问题。
""".strip()


def get_review_system_prompt() -> str:
    """获取复核Agent的系统提示词"""
    return f"""
# 复核Agent约束
- 你的主要任务，是复核聚类Agent判定为无效的结论，检查其是否充分且正确。
- 必须仔细检查聚类Agent给出的 invalid_reason 是否充分，是否确实考虑了各种可能的路径。
- 工具优先：用 read_code 读取目标文件邻近的源码（行号前后各 ~50 行），必要时用 execute_script 辅助检查。
- 必要时应当向上追溯调用者，查看完整调用路径，以判断聚类Agent的结论能否成立。
- 禁止修改任何文件或执行写操作；只允许只读分析与读取。
- 每次只执行一个操作；等工具返回结果后再继续。
- **记忆使用**：
  - 复核时，善用 memory 工具（action=retrieve）检索已有记忆，尤其是与当前文件或函数相关的。
  - 这类记忆可能包含函数分析要点、指针判空、输入校验、调用路径分析等。
- **复核原则**：
  - 必须验证聚类Agent是否确实检查了各种调用路径与调用者。
  - 必须验证聚类Agent是否确实确认了各路径都有防护。
  - 如果发现聚类Agent遗漏了某条路径、某个调用者或某种边界情况，必须判定其理由不充分。
  - 保守策略：有疑问时，一律判定理由不充分，将该候选重新纳入验证流程。
- 复核完成后，主输出只输出结束符 {ot("!!!COMPLETE!!!")}，不要夹杂其他内容。事项的总结，等待后续询问。
    """.strip()


def get_review_summary_prompt() -> str:
    """获取复核Agent的摘要提示词"""
    return """
本轮"复核结论"的结构化结果，只写在下面标记内，用 JSON 数组对象的形式输出。
你需要复核聚类Agent判定为无效的理由是否充分，是否确实考虑了各种可能的路径。

示例1：理由充分（is_reason_sufficient: true，单个 gid）
<REPORT>
[
  {
    "gid": 1,
    "is_reason_sufficient": true,
    "review_notes": "聚类Agent已检查全部调用路径，确认各调用者都有输入校验，理由充分"
  }
]
</REPORT>

示例2：理由充分（is_reason_sufficient: true，多个 gid 合并）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "is_reason_sufficient": true,
    "review_notes": "聚类Agent已检查全部调用路径，确认各调用者都有输入校验，理由充分"
  }
]
</REPORT>

示例3：理由不充分（is_reason_sufficient: false）
<REPORT>
[
  {
    "gid": 1,
    "is_reason_sufficient": false,
    "review_notes": "聚类Agent遗漏了函数X的调用路径，该路径可能未校验，理由不充分，需重新验证"
  }
]
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 之间输出 JSON 数组，不得混入其他文字。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一，对应无效聚类的 gid，单个告警时使用）
  - gids: 整数数组（全局唯一，对应无效聚类的 gids，多个告警合并时使用）
  - is_reason_sufficient: 布尔（true/false），表示无效理由是否充分
  - review_notes: 字符串（复核说明，解释为什么充分或不充分）
- **合并优化**：如果多个告警（gid）的复核结果（is_reason_sufficient）与复核说明（review_notes）完全一致，可以用 gids 数组合并，减少重复。单个告警用 gid，多个告警合并用 gids。gid 与 gids 不能同时出现。
- 必须复核所有输入的 gid，不得遗漏。
- 如果理由不充分（is_reason_sufficient: false），该候选重新纳入验证流程；如果充分（true），则确认无效。
    """.strip()


def get_cluster_system_prompt() -> str:
    """获取聚类Agent的系统提示词"""
    return """
# 单Agent聚类约束
- 你的主要任务，是聚类同一文件内的启发式候选，把可以一起验证的问题归为一类。
- **聚类原则**：
  - 可以一起验证的问题归为一类，验证条件不必完全一致。
  - 如果多个候选可以通过同一验证过程确认，即使它们的验证条件略有差异，也可以归为一类。
  - 例：多处指针解引用问题可以归为一类（验证"指针在解引用前非空"），即使涉及不同的指针。
  - 例：多处缓冲区操作问题可以归为一类（验证"拷贝长度不超过目标缓冲区容量"），即使涉及不同的缓冲区。
- 验证条件：为判定是否存在漏洞而必须成立/验证的关键前置条件。例："指针p在解引用前非空""拷贝长度不超过目标缓冲区容量"等。
- **完整性要求**：每个 gid 必须出现在某一类中，不得遗漏。所有输入的 gid，都必须归类。
- 工具优先：如果需要检查上下文，可以用 read_code 读取邻近代码；不要过度遍历。
- 禁止写操作；只允许只读分析。
- **重要：无效判断的保守策略**：
  - 判定候选无效时，必须考虑各种可能的路径、调用链与边界情况。
  - 必须考虑：各种调用者、各种输入来源、各种执行路径、各种边界条件。
  - 只要有任何可能（哪怕很微小）导致漏洞可被触发，就不能标记为无效（is_invalid: false）。
  - 只有完全确定、没有任何可能、所有路径都验证为安全的，才能标记为无效（is_invalid: true）。
  - 保守原则：有疑问时，一律标记 false（进入后续验证阶段），让分析Agent与验证Agent深入检查。
  - 不要因为看到局部有防护就判定无效，必须考虑是否存在其他路径绕过该防护。
  - 不要因为看到某个调用者已做校验就判定无效，必须考虑是否存在其他调用者未做校验。
- **记忆使用**：
  - 聚类时，善用 memory 工具（action=retrieve）检索已有记忆，尤其是与当前文件或函数相关的。
  - 如有需要，用 memory 工具（action=save）保存聚类中见到的函数或代码片段的要点，以函数名或文件名作为 tag。
  - 记忆内容示例：某函数的指针已判空、某函数已有输入校验、某代码片段的上下文等。
  - 这类记忆可以帮助后续的分析Agent与验证Agent更高效地工作。
    """.strip()


def get_cluster_summary_prompt() -> str:
    """获取聚类Agent的摘要提示词"""
    return """
只在 <CLUSTERS> 与 </CLUSTERS> 之间输出 JSON 数组：
- 每个元素包含（所有字段均必填）：
  - verification: 字符串（该聚类的验证条件描述，简洁明确，可直接用于后续Agent验证）
  - gids: 整数数组（候选的全局唯一编号；输入JSON每个元素含 gid，可直接对应填入）
  - is_invalid: 布尔（必填，true 或 false）。如果为 true，表示该聚类中所有候选已确认无效/误报，不进入后续验证；如果为 false，表示需要进入后续验证。
  - invalid_reason: 字符串（is_invalid 为 true 时必填，false 时可省略）。必须详细说明各候选为什么无效，包含：
    * 已检查的全部调用路径与调用者
    * 已确认的保护措施与校验逻辑
    * 为什么这些防护在所有路径上都有效
    * 为什么绝对没有可触发的路径
    * 必须足够详细，以便复核Agent可以验证你的判断
- 要求：
  - 严格限制：只在 <CLUSTERS> 与 </CLUSTERS> 之间输出 JSON 数组，其他位置不输出任何文字
  - **完整性要求（最重要）**：输入JSON中的所有 gid 都必须归类，不得遗漏。每个 gid 必须出现在某个聚类的 gids 数组中。这是强制要求，必须严格遵守。
  - **聚类原则**：可以一起验证的问题归为一类，验证条件不必完全一致。如果多个候选可以通过同一验证过程确认，即使它们的验证条件略有差异，也可以归为一类。
  - **必填要求**：每个聚类元素必须包含 is_invalid 字段，值必须为 true 或 false，不可省略。
  - **必填要求**：is_invalid 为 true 时，必须提供 invalid_reason 字段，且理由必须足够详细。
  - 无需解释与长文，只给出可执行的验证条件短句
  - 如果不能聚类，将各候选单独作为一类，verification 为该候选的最小确认条件
  - **is_invalid 的保守判定原则**：
    - 必须考虑各种路径、调用链、输入来源与边界情况。
    - 只要有任何可能（哪怕很微小）导致漏洞可被触发，必须置 is_invalid: false。
    - 只有完全确定、没有任何可能、所有路径都验证为安全的，才能置 is_invalid: true。
    - 保守策略：有疑问时，一律置 false，让后续的分析Agent与验证Agent深入检查。
    - 不要因为看到局部有防护就置 true，必须考虑是否存在其他路径绕过防护。
    - 不要因为某个调用者已做校验就置 true，必须考虑是否存在其他调用者未做校验。
    - 如果置 true，必须在 invalid_reason 中详细说明已检查的所有路径与理由。
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
