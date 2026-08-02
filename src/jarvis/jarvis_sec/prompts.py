# -*- coding: utf-8 -*-
"""提示词构建模块"""

from jarvis.jarvis_utils.tag import ot


def build_summary_prompt() -> str:
    """
    构建摘要提示词：要求以 <REPORT>...</REPORT> 包裹的 JSON 输出（仅JSON）。
    系统提示词不强制规定主对话输出格式，仅在摘要中给出结构化结果。
    """
    return """
本轮"安全子任务（单点验证）"之结构结果，仅书于下述标记内，以 JSON 数组对象形出之。
仅出全局编号（gid）与详由（不含位置）；gid 为全局唯一数字。

示例1：有告警（has_risk: true，单gid）
<REPORT>
[
  {
    "gid": 1,
    "has_risk": true,
    "preconditions": "输入字符串 src 之长度不小于 dst 缓冲区大小",
    "trigger_path": "调用路径：main() -> handle_network_request() -> parse_packet() -> foobar() -> strcpy()；parse_packet() 未校验长，径传 src 于 foobar()，foobar() 调 strcpy(dst, src) 不察 src 长，可致缓冲区溢出。关键调用点：parse_packet() 未校验输入长。",
    "consequences": "缓冲区溢出，可致程序崩溃或任意代码执行",
    "suggestions": "用 strncpy_s 或他安全字符串复制函数"
  }
]
</REPORT>

示例2：有告警（has_risk: true，多gid合并，路径与因由一致）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "has_risk": true,
    "preconditions": "输入字符串 src 之长度不小于 dst 缓冲区大小",
    "trigger_path": "调用路径：main() -> handle_network_request() -> parse_packet() -> foobar() -> strcpy()；parse_packet() 未校验长，径传 src 于 foobar()，foobar() 调 strcpy(dst, src) 不察 src 长，可致缓冲区溢出。关键调用点：parse_packet() 未校验输入长。",
    "consequences": "缓冲区溢出，可致程序崩溃或任意代码执行",
    "suggestions": "用 strncpy_s 或他安全字符串复制函数"
  }
]
</REPORT>

示例3：误报或无虞（返空数组）
<REPORT>
[]
</REPORT>

要求：
- 仅可于 <REPORT> 与 </REPORT> 间出 JSON 数组，不得杂他文。
- 若确认本批尽为误报或无虞，返空数组 []。
- 数组元素为对象，含字段：
  - gid: 整数（全局唯一，单告警时用）
  - gids: 整数数组（全局唯一，多告警合并时用）
  - has_risk: 布尔（true/false），示该项有无真实安全风险。
  - preconditions: 字符串（触发漏洞之前置条件，唯 has_risk 为 true 时必须）
  - trigger_path: 字符串（漏洞触发路径，须含完整调用路径推导：1) 可控输入之源；2) 自输入源至缺陷代码之完整调用链（函数调用序列）；3) 各调用点之数据校验情形；4) 触发条件。格式示例："调用路径推导：函数A() -> 函数B() -> 函数C() -> 缺陷代码。数据流：输入来源 -> 传递路径。关键调用点：函数B()未做校验。"，唯 has_risk 为 true 时必须）
  - consequences: 字符串（漏洞触发后之可能后果，唯 has_risk 为 true 时必须）
  - suggestions: 字符串（修复或缓解之建议，唯 has_risk 为 true 时必须）
- **合并优化**：若多告警（gid）之路径（trigger_path）与因由（preconditions/consequences/suggestions）全然一致，可用 gids 数组合并，减重复。单告警用 gid，多告警合用 gids。gid 与 gids 不得并出。
- 勿于数组元素中混入 file/line/pattern 等位置信息；写 jsonl 时系统自合原始候选。
- **关键**：唯 `has_risk` 为 `true` 者，方录为确认之问题。确为误报者，令 `has_risk` 为 `false` 或不出该条。
- **输出格式**：有告警之条目，须含全字段（gid 或 gids, has_risk, preconditions, trigger_path, consequences, suggestions）；无告警之条目，仅含 gid 与 has_risk。
- **调用路径推导要求**：trigger_path 须含完整调用路径推导，不得省略精简。须明言自可控输入至缺陷代码之全调用链，及各调用点之校验情形。若不能推导完整调用路径，应判为误报（has_risk: false）。
""".strip()


def build_verification_summary_prompt() -> str:
    """
    构建验证 Agent 的摘要提示词：验证分析 Agent 给出的结论是否正确。
    """
    return """
本轮"验证分析结论"之结构结果，仅书于下述标记内，以 JSON 数组对象形出之。
汝须验分析 Agent 所给结论是否正确，含前置条件、触发路径、后果与建议是否合理。

示例1：验证通过（is_valid: true，单gid）
<REPORT>
[
  {
    "gid": 1,
    "is_valid": true,
    "verification_notes": "分析结论正确，前置条件合理，触发路径清晰，后果评估准确"
  }
]
</REPORT>

示例2：验证通过（is_valid: true，多gid合并）
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
- 仅可于 <REPORT> 与 </REPORT> 间出 JSON 数组，不得杂他文。
- 数组元素为对象，含字段：
  - gid: 整数（全局唯一，对应分析 Agent 所给 gid，单告警时用）
  - gids: 整数数组（全局唯一，对应分析 Agent 所给 gids，多告警合并时用）
  - is_valid: 布尔（true/false），示分析 Agent 结论是否正确
  - verification_notes: 字符串（验证说明，解何故正确或不正确）
- **合并优化**：若多告警（gid）之验证结果（is_valid）与验证说明（verification_notes）全然一致，可用 gids 数组合并，减重复。单告警用 gid，多告警合用 gids。gid 与 gids 不得并出。
- 须尽验所有输入之 gid，不得遗漏。
- 若验证通过（is_valid: true），则存该告警；若不通过（is_valid: false），视作误报，不录为问题。
""".strip()


def get_review_system_prompt() -> str:
    """获取复核Agent的系统提示词"""
    return f"""
# 复核Agent约束
- 汝之要务，在核聚类Agent所废之论，究其充分正确与否。
- 须细察聚类Agent所给invalid_reason是否充分，果曾尽虑诸般可能路径。
- 工具优先：以 read_code 读目标文件邻近源码（行号前后各 ~50 行），必要时以 execute_script 佐检。
- 必要时宜上溯调用者，览全调用路径，以定聚类Agent之论能否成立。
- 禁改任何文件或行写操作；唯许只读分析与读取。
- 每次仅行一操作；待工具果后始续。
- **记忆使用**：
  - 复核之际，善用 memory 工具（action=retrieve）检既有记忆，尤与当前文件或函数相关者。
  - 此类记忆或含函数分析要点、指针判空、输入校验、调用路径分析等。
- **复核原则**：
  - 须验聚类Agent果曾尽察诸般调用路径与调用者。
  - 须验聚类Agent果曾尽确认诸路径皆有护。
  - 若觉聚类Agent漏某路径、调用者或边界情形，必判其理由不足。
  - 保守之策：有疑时，尽判理由不足，将该候选复入验证流程。
- 复核毕，主输出唯刊结束符 {ot("!!!COMPLETE!!!")}，勿杂他辞。事之总结，待后询。
    """.strip()


def get_review_summary_prompt() -> str:
    """获取复核Agent的摘要提示词"""
    return """
本轮"复核结论"之结构结果，仅书于下述标记内，以 JSON 数组对象形出之。
汝须核聚类Agent所废之由是否充分，果曾尽虑诸般可能路径。

示例1：理由充分（is_reason_sufficient: true，单gid）
<REPORT>
[
  {
    "gid": 1,
    "is_reason_sufficient": true,
    "review_notes": "聚类Agent已察全调用路径，确认诸调用者皆有输入校验，理由充分"
  }
]
</REPORT>

示例2：理由充分（is_reason_sufficient: true，多gid合并）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "is_reason_sufficient": true,
    "review_notes": "聚类Agent已察全调用路径，确认诸调用者皆有输入校验，理由充分"
  }
]
</REPORT>

示例3：理由不充分（is_reason_sufficient: false）
<REPORT>
[
  {
    "gid": 1,
    "is_reason_sufficient": false,
    "review_notes": "聚类Agent漏函数X之调用路径，该路径或未校验，理由不充分，须复验"
  }
]
</REPORT>

要求：
- 仅可于 <REPORT> 与 </REPORT> 间出 JSON 数组，不得杂他文。
- 数组元素为对象，含字段：
  - gid: 整数（全局唯一，对应无效聚类之gid，单告警时用）
  - gids: 整数数组（全局唯一，对应无效聚类之gids，多告警合并时用）
  - is_reason_sufficient: 布尔（true/false），示无效理由是否充分
  - review_notes: 字符串（复核说明，解何故充分或不充分）
- **合并优化**：若多告警（gid）之复核结果（is_reason_sufficient）与复核说明（review_notes）全然一致，可用 gids 数组合并，减重复。单告警用 gid，多告警合用 gids。gid 与 gids 不得并出。
- 须尽核所有输入之gid，不得遗漏。
- 若理由不充分（is_reason_sufficient: false），该候选复入验证流程；若充分（true），则确认无效。
    """.strip()


def get_cluster_system_prompt() -> str:
    """获取聚类Agent的系统提示词"""
    return """
# 单Agent聚类约束
- 汝之要务，在聚类同文件之启发式候选，将可同验之问题归为一类。
- **聚类原则**：
  - 可同验之问题归一类，不必验证条件全然一致。
  - 若数候选可经同一验证过程确认，纵其验证条件略异，亦可归为一类。
  - 例：数处指针解引用问题可归一类（验"指针于解引用前非空"），纵涉异指针。
  - 例：数处缓冲区操作问题可归一类（验"拷贝长不逾目标缓冲区容"），纵涉异缓冲区。
- 验证条件：为定有无漏洞须成立/验证之关键前置条件。例："指针p于解引用前非空""拷贝长不逾目标缓冲区容"等。
- **完整性要求**：每个gid必现于某类，不得漏一。凡输入之gid，皆须归类。
- 工具优先：如需核上下文，可读 read_code 读邻码；勿过遍历。
- 禁写操作；唯只读分析。
- **重要：无效判断之保守策**：
  - 判候选无效之际，须尽虑诸般可能路径、调用链与边界情形。
  - 须虑：诸般调用者、诸般输入之源、诸般执行路径、诸般边界条件。
  - 苟有任何可能（纵微）致漏洞可触，不可标无效（is_invalid: false）。
  - 唯全然确定、无任何可能、诸路径皆验安全者，方得标无效（is_invalid: true）。
  - 保守之则：有疑时，尽标 false（入后验阶段），任分析Agent与验证Agent深究。
  - 勿因见局部有护遂判无效，须虑有无他路绕此护。
  - 勿因见某调用者已校遂判无效，须虑有无他调用者未校。
- **记忆使用**：
  - 聚类之际，善用 memory 工具（action=retrieve）检既有记忆，尤与当前文件或函数相关者。
  - 如须，用 memory 工具（action=save）存聚类中所见函数或代码片段之要点，以函数名或文件名作 tag。
  - 记忆内容示例：某函数之指针已判空、某函数已有输入校验、某代码片段之上下文等。
  - 此类记忆可助后之分析Agent与验证Agent更效其工。
    """.strip()


def get_cluster_summary_prompt() -> str:
    """获取聚类Agent的摘要提示词"""
    return """
仅于 <CLUSTERS> 与 </CLUSTERS> 间出 JSON 数组：
- 每元素含（诸字段皆必填）：
  - verification: 字符串（该聚类之验证条件描述，简洁明确，可直接用于后Agent验证）
  - gids: 整数数组（候选之全局唯一编号；输入JSON每元素含 gid，可直接对应填入）
  - is_invalid: 布尔（必填，true 或 false）。若为 true，示该聚类中诸候选已确认无效/误报，不入后验；若为 false，示须入后验。
  - invalid_reason: 字符串（is_invalid 为 true 时必填，false 时可略）。须详言诸候选何故无效，含：
    * 已察之全调用路径与调用者
    * 已确认之保护措施与校验逻辑
    * 何故此等护于诸路径皆效
    * 何故绝无可触之路径
    * 须足详，俾复核Agent可验汝判
- 要求：
  - 严限：唯出 <CLUSTERS> 与 </CLUSTERS> 间之 JSON 数组，他处不出一文
  - **完整性要求（至要）**：输入JSON中之全gid皆须归类，不得漏一。凡gid必现于某聚类之gids数组。此为强令，须严遵。
  - **聚类原则**：可同验之问题归一类，不必验证条件全然一致。若数候选可经同一验证过程确认，纵其验证条件略异，亦可归一类。
  - **必填要求**：每聚类元素必含 is_invalid 字段，值必为 true 或 false，不可省。
  - **必填要求**：is_invalid 为 true 时，必供 invalid_reason 字段，且理由须足详。
  - 无需解释与长文，唯给可执行之验证条件短句
  - 若不能聚类，将各候选独成一族，verification 为该候选之最小确认条件
  - **is_invalid 之保守判则**：
    - 须尽虑诸般路径、调用链、输入之源与边界情形。
    - 苟有任何可能（纵微）致漏洞可触，必置 is_invalid: false。
    - 唯全然确定、无任何可能、诸路径皆验安全者，方置 is_invalid: true。
    - 保守之策：有疑时，尽置 false，任后之分析Agent与验证Agent深究。
    - 勿因见局部有护遂置 true，须虑有无他路绕护。
    - 勿因某调用者已校遂置 true，须虑有无他调用者未校。
    - 若置 true，必于 invalid_reason 中详言已察之诸路径与因由。
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
