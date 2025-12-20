# 安全问题分析报告（聚合）

- 检出问题总数: 123

## 统计概览
- 按语言: c/cpp=102, rust=21
- 按类别：
  - unsafe_api: 0
  - buffer_overflow: 1
  - memory_mgmt: 94
  - error_handling: 14
  - unsafe_usage: 9
  - concurrency: 0
  - ffi: 4
- Top 风险文件：
  - interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp
  - interfaces/rust/innerkits/src/sys_event_manager.rs
  - interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp
  - interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp
  - interfaces/js/kits/napi/src/napi_hisysevent_querier.cpp
  - interfaces/native/innerkits/hisysevent_easy/easy_socket_writer.c
  - frameworks/native/c_wrapper/source/hisysevent_rust_querier.cpp
  - interfaces/ets/ani/hisysevent/include/hisysevent_ani_util.h
  - interfaces/ets/ani/hisysevent/src/hisysevent_ani.cpp
  - interfaces/js/kits/napi/src/napi_hisysevent_js.cpp

## 详细问题
### [1] frameworks/native/c_wrapper/source/hisysevent_rust_querier.cpp:48 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (sysEvents == nullptr || sysEvents->empty()) {`
- 前置条件: sysEvents指针可能为nullptr
- 触发路径: 调用路径推导：HiSysEventManager::Query() -> HiSysEventBaseManager::Query() -> HiSysEventDelegate::Query() -> HiSysEventQueryProxy::OnQuery() -> HiSysEventBaseQueryCallback::OnQuery() -> HiSysEventRustQuerier::OnQuery()。数据流：查询结果通过IPC传递，最终回调到OnQuery()。关键调用点：测试用例中直接传入nullptr，生产代码路径中未对所有调用路径进行空指针校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在HiSysEventRustQuerier::OnQuery()入口处增加sysEvents指针的非空校验
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [2] frameworks/native/c_wrapper/source/hisysevent_rust_querier.cpp:52 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `size_t size = sysEvents->size();`
- 前置条件: sysEvents指针可能为nullptr
- 触发路径: 调用路径推导：HiSysEventManager::Query() -> HiSysEventBaseManager::Query() -> HiSysEventDelegate::Query() -> HiSysEventQueryProxy::OnQuery() -> HiSysEventBaseQueryCallback::OnQuery() -> HiSysEventRustQuerier::OnQuery()。数据流：查询结果通过IPC传递，最终回调到OnQuery()。关键调用点：测试用例中直接传入nullptr，生产代码路径中未对所有调用路径进行空指针校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在HiSysEventRustQuerier::OnQuery()入口处增加sysEvents指针的非空校验
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [3] frameworks/native/c_wrapper/source/hisysevent_rust_querier.cpp:59 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (HiSysEventRecordConvertor::ConvertRecord(sysEvents->at(i), records[i]) != 0) {`
- 前置条件: sysEvents指针可能为nullptr
- 触发路径: 调用路径推导：HiSysEventManager::Query() -> HiSysEventBaseManager::Query() -> HiSysEventDelegate::Query() -> HiSysEventQueryProxy::OnQuery() -> HiSysEventBaseQueryCallback::OnQuery() -> HiSysEventRustQuerier::OnQuery()。数据流：查询结果通过IPC传递，最终回调到OnQuery()。关键调用点：测试用例中直接传入nullptr，生产代码路径中未对所有调用路径进行空指针校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在HiSysEventRustQuerier::OnQuery()入口处增加sysEvents指针的非空校验
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [4] frameworks/native/c_wrapper/source/hisysevent_rust_manager.cpp:178 (c/cpp, buffer_overflow)
- 模式: vector_bounds_check
- 证据: `int OhHiSysEventAddRustWatcher(HiSysEventRustWatcherC* watcher, const HiSysEventWatchRule watchRules[],`
- 前置条件: 调用者未正确验证 ruleSize 参数与 rules 数组长度的匹配关系
- 触发路径: 调用路径推导：OhHiSysEventAddRustWatcher() -> HiSysEventAddWatcher()。数据流：外部传入的 watchRules 数组和 ruleSize 参数直接传递给 HiSysEventAddWatcher。关键调用点：HiSysEventAddWatcher() 函数未验证 ruleSize 与 rules 数组的实际长度关系，仅检查了 watcher 的有效性。
- 后果: 可能导致数组越界访问，引发程序崩溃或内存破坏
- 建议: 在 HiSysEventAddWatcher 中添加对 ruleSize 和 rules 数组长度的验证逻辑，或确保所有调用者正确维护参数一致性
- 置信度: 0.6, 严重性: medium, 评分: 1.2

### [5] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:66 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_ARRAY, &cls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [6] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:96 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_BIGINT, &cls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [7] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:116 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_BOOLEAN, &cls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [8] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:136 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_INT, &cls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [9] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:156 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_DOUBLE, &cls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [10] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:301 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_RESULTINNER, &cls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [11] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:340 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_DOUBLE, &personCls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [12] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:360 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_DOUBLE, &personCls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [13] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:380 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_BOOLEAN, &personCls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [14] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:400 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_DOUBLE, &personCls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [15] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:420 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_DOUBLE, &personCls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [16] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:461 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_DOUBLE, &personCls)) {`
- 前置条件: 调用者传入的 ani_env *env 参数为 null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil 类方法（如 IsArray(), ParseBigintValue() 等）。数据流：env 指针作为参数直接传递给 HiSysEventAniUtil 类方法，这些方法直接调用 env->FindClass() 而未检查 env 是否为 null。关键调用点：所有 HiSysEventAniUtil 方法都未对 env 参数进行空指针检查。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有 HiSysEventAniUtil 方法开始处添加 env 指针的非空检查，如：if (env == nullptr) { return ...; }
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [17] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:82 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `env->Reference_IsUndefined(ref, &isUndefined);`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [18] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:176 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_CallMethodByName_Ref(static_cast<ani_object>(recordRef), "    ",`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [19] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:184 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_CallMethodByName_Ref(static_cast<ani_object>(keys), "    ", nullptr, &next)) {`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [20] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:201 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_CallMethodByName_Ref(static_cast<ani_object>(recordRef),`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [21] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:219 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->String_GetUTF8Size(static_cast<ani_string>(aniStrRef), &strSize)) {`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [22] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:226 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->String_GetUTF8(static_cast<ani_string>(aniStrRef), utf8Buffer, strSize + 1, &bytesWritten)) {`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [23] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:328 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `env->String_NewUTF8(message.c_str(), message.size(), &message_string);`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [24] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:444 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `ani_int enumIndex = static_cast<ani_int>(it->second);`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [25] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:446 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindEnum(ENUM_NAME_EVENT_TYPE, &aniEnum)) {`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [26] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:450 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (env->Enum_GetEnumItemByIndex(aniEnum, enumIndex, &aniEnumItem)) {`
- 前置条件: env 指针为 null 或无效
- 触发路径: 调用路径推导：ANI框架 -> HiSysEvent接口函数 -> HiSysEventAniUtil类方法。数据流：env指针由ANI框架传入，在调用链中未进行空指针校验，直接传递给HiSysEventAniUtil类方法使用。关键调用点：所有使用env指针的HiSysEventAniUtil方法均未对env指针进行校验。
- 后果: 可能导致程序崩溃或未定义行为
- 建议: 1. 在所有使用env指针的函数入口处添加空指针检查；2. 或明确文档说明env指针由框架保证非空
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [27] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:466 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Class_FindMethod(personCls, "      ", "   ", &personInfoCtor)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [28] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:470 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_New(personCls, personInfoCtor, &personInfoObj, static_cast<ani_double>(number))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [29] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:480 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->String_NewUTF8(value.c_str(), value.size(), &valueStr)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [30] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:490 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_BUSINESSERROR, &cls)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [31] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:495 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Class_FindMethod(cls, "      ", "  ", &ctor)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [32] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:500 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_New(cls, ctor, &error)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [33] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:504 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_SetPropertyByName_Double(error, "    ", static_cast<ani_double>(code))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [34] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:509 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->String_NewUTF8(message.c_str(), message.size(), &messageRef)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [35] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:513 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_SetPropertyByName_Ref(error, "       ", static_cast<ani_ref>(messageRef))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [36] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:517 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->ThrowError(static_cast<ani_error>(error))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [37] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:546 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_SYSEVENTINFOANI, &cls)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [38] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:551 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_SetPropertyByName_Ref(sysEventInfo, "         ", static_cast<ani_ref>(eventType_ctor))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [39] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:560 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_SYSEVENTINFOANI, &cls)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [40] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:567 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_SetPropertyByName_Ref(sysEventInfo, "      ", static_cast<ani_ref>(domain_ctor))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [41] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:572 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_SetPropertyByName_Ref(sysEventInfo, "    ", static_cast<ani_ref>(name_ctor))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [42] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:630 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_SYSEVENTINFOANI, &cls)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [43] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:635 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Array_New_Ref(cls, len, initial_array, &array)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [44] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:644 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Array_Set_Ref(array, i, static_cast<ani_ref>(item))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [45] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:649 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_SetPropertyByName_Ref(sysEventInfo, "      ", static_cast<ani_ref>(array))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [46] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:664 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_SetPropertyByName_Ref(sysEventInfo, "      ", static_cast<ani_ref>(property))) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [47] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:679 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->FindClass(CLASS_NAME_SYSEVENTINFOANI, &cls)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [48] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:685 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Class_FindMethod(cls, "      ", nullptr, &ctor)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [49] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:690 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK != env->Object_New(cls, ctor, &sysEventInfo)) {`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [50] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:695 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `ani_status ret = env->Array_Set_Ref(sysEventInfoJsArray, i, static_cast<ani_ref>(sysEventInfo));`
- 前置条件: 传入的env指针为null
- 触发路径: 调用路径推导：外部调用者 -> HiSysEventAniUtil类的静态方法（如CreateDoubleUint32/CreateStringValue/ThrowAniError等）。数据流：env指针作为参数直接传入静态方法，方法内部未进行空指针检查直接使用。关键调用点：所有HiSysEventAniUtil类的静态方法都未对env指针进行校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在所有JNI方法调用前添加env指针的非空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [51] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:741 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `env->String_GetUTF8Size(aniStr, &strSize);`
- 前置条件: ani_string参数为null
- 触发路径: 调用路径推导：HiSysEventAni::WriteInner() -> GetStack() -> HiSysEventAniUtil::AniStringToStdString()。数据流：stackTraceStr来自Object_CallMethodByName_Ref调用，未检查返回值是否为null。关键调用点：Object_CallMethodByName_Ref调用后未检查stackTraceStr是否为null。
- 后果: 空指针解引用，可能导致程序崩溃
- 建议: 在调用AniStringToStdString前检查aniStr参数是否为null，或在该函数内部添加参数校验
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [52] interfaces/ets/ani/hisysevent/src/hisysevent_ani_util.cpp:745 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `env->String_GetUTF8(aniStr, utf8Buffer, strSize + 1, &bytesWritten);`
- 前置条件: ani_string参数为null
- 触发路径: 调用路径推导：HiSysEventAni::WriteInner() -> GetStack() -> HiSysEventAniUtil::AniStringToStdString()。数据流：stackTraceStr来自Object_CallMethodByName_Ref调用，未检查返回值是否为null。关键调用点：Object_CallMethodByName_Ref调用后未检查stackTraceStr是否为null。
- 后果: 空指针解引用，可能导致程序崩溃
- 建议: 在调用AniStringToStdString前检查aniStr参数是否为null，或在该函数内部添加参数校验
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [53] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:46 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK == callbackContextAni->vm->GetEnv(ANI_VERSION_1, &env) && env != nullptr) {`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [54] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:46 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (ANI_OK == callbackContextAni->vm->GetEnv(ANI_VERSION_1, &env) && env != nullptr) {`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [55] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:47 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `env->GlobalReference_Delete(callbackContextAni->ref);`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [56] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:47 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `env->GlobalReference_Delete(callbackContextAni->ref);`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [57] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:48 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `} else if (ANI_OK == callbackContextAni->vm->AttachCurrentThread(&aniArgs, ANI_VERSION_1, &env) && env != nullptr) {`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [58] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:48 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `} else if (ANI_OK == callbackContextAni->vm->AttachCurrentThread(&aniArgs, ANI_VERSION_1, &env) && env != nullptr) {`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [59] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:49 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `env->GlobalReference_Delete(callbackContextAni->ref);`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [60] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:49 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `env->GlobalReference_Delete(callbackContextAni->ref);`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [61] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:50 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `callbackContextAni->vm->DetachCurrentThread();`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [62] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:50 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `callbackContextAni->vm->DetachCurrentThread();`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [63] interfaces/ets/ani/hisysevent/src/ani_hisysevent_querier.cpp:124 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `this->onCompleteHandler(vm, this->callbackContextAni->ref);`
- 前置条件: callbackContextAni或其成员(vm, ref)在使用前被意外置为null
- 触发路径: 调用路径推导：hisysevent_ani.cpp创建CallbackContextAni -> AniHiSysEventQuerier构造函数 -> 析构函数/OnComplete使用。数据流：vm参数通过hisysevent_ani.cpp传入，querierRef通过env->GlobalReference_Create创建。关键调用点：AniHiSysEventQuerier构造函数接收callbackContextAni后未做空指针检查，直接存储使用。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在AniHiSysEventQuerier构造函数中添加空指针检查；2. 使用智能指针管理callbackContextAni生命周期；3. 在析构函数和OnComplete中添加防御性空指针检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [64] interfaces/ets/ani/hisysevent/src/hisysevent_ani.cpp:598 (c/cpp, memory_mgmt)
- 模式: alloc_no_null_check
- 证据: `CallbackContextAni *callbackContextAni = new CallbackContextAni();`
- 前置条件: 系统内存不足导致new操作返回nullptr
- 触发路径: 调用路径推导：1) 可控输入来源：外部调用AddWatcher/Query API；2) 调用链：AddWatcher/Query -> new CallbackContextAni()；3) 调用点校验：入口函数检查了调用者权限但未检查内存分配情况；4) 触发条件：内存不足时new失败返回nullptr，后续立即解引用
- 后果: 空指针解引用导致程序崩溃或未定义行为
- 建议: 1) 对new操作添加nullptr检查；2) 使用std::nothrow版本的new操作；3) 考虑使用智能指针管理内存
- 置信度: 0.8, 严重性: high, 评分: 2.4

### [65] interfaces/ets/ani/hisysevent/src/hisysevent_ani.cpp:655 (c/cpp, memory_mgmt)
- 模式: alloc_no_null_check
- 证据: `CallbackContextAni *callbackContextAni = new CallbackContextAni();`
- 前置条件: 系统内存不足导致new操作返回nullptr
- 触发路径: 调用路径推导：1) 可控输入来源：外部调用AddWatcher/Query API；2) 调用链：AddWatcher/Query -> new CallbackContextAni()；3) 调用点校验：入口函数检查了调用者权限但未检查内存分配情况；4) 触发条件：内存不足时new失败返回nullptr，后续立即解引用
- 后果: 空指针解引用导致程序崩溃或未定义行为
- 建议: 1) 对new操作添加nullptr检查；2) 使用std::nothrow版本的new操作；3) 考虑使用智能指针管理内存
- 置信度: 0.8, 严重性: high, 评分: 2.4

### [66] interfaces/ets/ani/hisysevent/include/hisysevent_ani_util.h:121 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (iter->second.first != getproctid()) {`
- 前置条件: env指针来自AttachAniEnv可能返回nullptr，或iter指针等于resources.end()时被解引用
- 触发路径: 调用路径推导：1) 可控输入来源：通过AttachAniEnv获取的env指针；2) 调用链：AttachAniEnv() -> CompareAndReturnCacheItem() -> 解引用操作；3) 校验情况：AttachAniEnv可能返回nullptr但调用点未检查，CompareAndReturnCacheItem内部未检查env和iter指针；4) 触发条件：当AttachAniEnv返回nullptr或iter等于end()时解引用
- 后果: 空指针解引用可能导致程序崩溃或未定义行为
- 建议: 1) 在调用AttachAniEnv后检查返回值；2) 在CompareAndReturnCacheItem函数内部添加对env和iter指针的校验
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [67] interfaces/ets/ani/hisysevent/include/hisysevent_ani_util.h:124 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `ani_ref val = iter->first;`
- 前置条件: env指针来自AttachAniEnv可能返回nullptr，或iter指针等于resources.end()时被解引用
- 触发路径: 调用路径推导：1) 可控输入来源：通过AttachAniEnv获取的env指针；2) 调用链：AttachAniEnv() -> CompareAndReturnCacheItem() -> 解引用操作；3) 校验情况：AttachAniEnv可能返回nullptr但调用点未检查，CompareAndReturnCacheItem内部未检查env和iter指针；4) 触发条件：当AttachAniEnv返回nullptr或iter等于end()时解引用
- 后果: 空指针解引用可能导致程序崩溃或未定义行为
- 建议: 1) 在调用AttachAniEnv后检查返回值；2) 在CompareAndReturnCacheItem函数内部添加对env和iter指针的校验
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [68] interfaces/ets/ani/hisysevent/include/hisysevent_ani_util.h:126 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `ani_status ret = env->Reference_StrictEquals(standard, static_cast<ani_object>(val), &isEquals);`
- 前置条件: env指针来自AttachAniEnv可能返回nullptr，或iter指针等于resources.end()时被解引用
- 触发路径: 调用路径推导：1) 可控输入来源：通过AttachAniEnv获取的env指针；2) 调用链：AttachAniEnv() -> CompareAndReturnCacheItem() -> 解引用操作；3) 校验情况：AttachAniEnv可能返回nullptr但调用点未检查，CompareAndReturnCacheItem内部未检查env和iter指针；4) 触发条件：当AttachAniEnv返回nullptr或iter等于end()时解引用
- 后果: 空指针解引用可能导致程序崩溃或未定义行为
- 建议: 1) 在调用AttachAniEnv后检查返回值；2) 在CompareAndReturnCacheItem函数内部添加对env和iter指针的校验
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [69] interfaces/native/innerkits/hisysevent_easy/easy_socket_writer.c:69 (c/cpp, error_handling)
- 模式: io_call
- 证据: `close(socketId);`
- 前置条件: socketId为无效文件描述符或close操作失败
- 触发路径: 调用路径推导：Write() -> close(socketId)。数据流：socketId来自TEMP_FAILURE_RETRY(socket(...))调用，在错误处理路径中直接调用close。关键调用点：行69在socketId<0时错误地调用close；其他close调用点未检查返回值。
- 后果: 可能导致资源泄漏或掩盖底层错误情况
- 建议: 1. 移除行69的无效close调用；2. 其他close调用应检查返回值并记录错误；3. 建议使用包装函数安全关闭socket
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [70] interfaces/native/innerkits/hisysevent_easy/easy_socket_writer.c:74 (c/cpp, error_handling)
- 模式: io_call
- 证据: `close(socketId);`
- 前置条件: socketId为无效文件描述符或close操作失败
- 触发路径: 调用路径推导：Write() -> close(socketId)。数据流：socketId来自TEMP_FAILURE_RETRY(socket(...))调用，在错误处理路径中直接调用close。关键调用点：行69在socketId<0时错误地调用close；其他close调用点未检查返回值。
- 后果: 可能导致资源泄漏或掩盖底层错误情况
- 建议: 1. 移除行69的无效close调用；2. 其他close调用应检查返回值并记录错误；3. 建议使用包装函数安全关闭socket
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [71] interfaces/native/innerkits/hisysevent_easy/easy_socket_writer.c:80 (c/cpp, error_handling)
- 模式: io_call
- 证据: `close(socketId);`
- 前置条件: socketId为无效文件描述符或close操作失败
- 触发路径: 调用路径推导：Write() -> close(socketId)。数据流：socketId来自TEMP_FAILURE_RETRY(socket(...))调用，在错误处理路径中直接调用close。关键调用点：行69在socketId<0时错误地调用close；其他close调用点未检查返回值。
- 后果: 可能导致资源泄漏或掩盖底层错误情况
- 建议: 1. 移除行69的无效close调用；2. 其他close调用应检查返回值并记录错误；3. 建议使用包装函数安全关闭socket
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [72] interfaces/native/innerkits/hisysevent_easy/easy_socket_writer.c:92 (c/cpp, error_handling)
- 模式: io_call
- 证据: `close(socketId);`
- 前置条件: socketId为无效文件描述符或close操作失败
- 触发路径: 调用路径推导：Write() -> close(socketId)。数据流：socketId来自TEMP_FAILURE_RETRY(socket(...))调用，在错误处理路径中直接调用close。关键调用点：行69在socketId<0时错误地调用close；其他close调用点未检查返回值。
- 后果: 可能导致资源泄漏或掩盖底层错误情况
- 建议: 1. 移除行69的无效close调用；2. 其他close调用应检查返回值并记录错误；3. 建议使用包装函数安全关闭socket
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [73] interfaces/native/innerkits/hisysevent_easy/easy_socket_writer.c:95 (c/cpp, error_handling)
- 模式: io_call
- 证据: `close(socketId);`
- 前置条件: socketId为无效文件描述符或close操作失败
- 触发路径: 调用路径推导：Write() -> close(socketId)。数据流：socketId来自TEMP_FAILURE_RETRY(socket(...))调用，在错误处理路径中直接调用close。关键调用点：行69在socketId<0时错误地调用close；其他close调用点未检查返回值。
- 后果: 可能导致资源泄漏或掩盖底层错误情况
- 建议: 1. 移除行69的无效close调用；2. 其他close调用应检查返回值并记录错误；3. 建议使用包装函数安全关闭socket
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [74] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:151 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `GetParamNames(*record, names, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [75] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:151 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `GetParamNames(*record, names, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [76] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:156 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamInt64Value(*record, name, *value);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [77] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:156 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamInt64Value(*record, name, *value);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [78] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:161 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamUint64Value(*record, name, *value);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [79] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:161 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamUint64Value(*record, name, *value);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [80] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:166 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamDoubleValue(*record, name, *value);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [81] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:166 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamDoubleValue(*record, name, *value);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [82] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:171 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamStringValue(*record, name, value);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [83] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:176 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamInt64Values(*record, name, value, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [84] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:176 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamInt64Values(*record, name, value, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [85] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:181 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamUint64Values(*record, name, value, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [86] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:181 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamUint64Values(*record, name, value, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [87] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:186 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamDoubleValues(*record, name, value, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [88] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:186 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamDoubleValues(*record, name, value, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [89] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:191 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamStringValues(*record, name, value, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [90] interfaces/native/innerkits/hisysevent_manager/hisysevent_record_c.cpp:191 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `return GetParamStringValues(*record, name, value, *len);`
- 前置条件: record指针为nullptr
- 触发路径: 调用路径推导：外部调用 -> OH_HiSysEvent_GetParam*() -> GetParam*()。数据流：record指针可能来自外部输入，直接传递给OH_HiSysEvent_GetParam*()函数，这些函数内部直接解引用record指针而未做空指针检查。关键调用点：所有OH_HiSysEvent_GetParam*()函数均未对record指针进行空指针验证。
- 后果: 空指针解引用，导致程序崩溃
- 建议: 在所有OH_HiSysEvent_GetParam*()函数入口处添加对record指针的非空检查，并在指针为null时返回错误码
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [91] interfaces/native/innerkits/hisysevent/event_socket_factory.cpp:106 (c/cpp, type_safety)
- 模式: reinterpret_cast_unsafe
- 证据: `struct HiSysEventHeader header = *(reinterpret_cast<struct HiSysEventHeader*>(originalData + sizeof(int32_t)));`
- 前置条件: 原始数据长度足够(sizeof(int32_t) + sizeof(HiSysEventHeader))但未正确对齐或内容无效
- 触发路径: 调用路径推导：EventSocketFactory::GetEventSocket() -> ParseEventInfo() -> reinterpret_cast转换。数据流：RawData对象通过GetEventSocket()接收，传递给ParseEventInfo()解析，ParseEventInfo()检查了数据长度但未验证对齐和内容，直接使用reinterpret_cast转换指针。关键调用点：ParseEventInfo()函数未对指针对齐和结构内容进行校验。
- 后果: 内存访问错误或未定义行为，可能导致程序崩溃或信息泄露
- 建议: 1. 添加指针对齐检查；2. 使用memcpy代替指针转换；3. 验证结构体字段有效性（如字符串null终止符）
- 置信度: 0.7999999999999999, 严重性: high, 评分: 2.4

### [92] interfaces/native/innerkits/hisysevent/hisysevent_c.cpp:36 (c/cpp, error_handling)
- 模式: io_call
- 证据: `return HiSysEvent::Write(func, line, domain, name, HiSysEvent::EventType(type), params, size);`
- 前置条件: 传入的HiSysEventParam结构体中的字符串指针(s)或数组指针(array)为nullptr，且arraySize参数超出合理范围
- 触发路径: 调用路径推导：HiSysEvent_Write() -> HiSysEventInnerWrite() -> HiSysEvent::Write() -> HiSysEvent::InnerWrite()。数据流：外部输入通过HiSysEvent_Write接收，传递到HiSysEvent::InnerWrite处理。关键调用点：HiSysEvent::InnerWrite未检查HiSysEventParam结构体中的字符串指针和数组指针是否为nullptr，也未验证arraySize参数的合理性。
- 后果: 可能导致空指针解引用或数组越界访问，引发程序崩溃或内存破坏
- 建议: 1. 在HiSysEvent::InnerWrite中添加对HiSysEventParam结构体中指针的null检查；2. 添加对arraySize参数的边界检查；3. 对字符串参数使用安全处理函数
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [93] interfaces/js/kits/napi/src/napi_hisysevent_querier.cpp:46 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `jsCallbackManager->Release();`
- 前置条件: callbackContext指针为空
- 触发路径: 调用路径推导：NapiHiSysEventQuerier构造函数 -> 析构函数/OnQuery/OnComplete方法。数据流：callbackContext通过构造函数参数传入，但在析构函数和成员方法中使用前未进行判空检查。关键调用点：NapiHiSysEventQuerier构造函数未对callbackContext参数进行非空校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在构造函数中添加callbackContext参数的非空校验；2. 在所有使用callbackContext的成员方法中添加判空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [94] interfaces/js/kits/napi/src/napi_hisysevent_querier.cpp:48 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (callbackContext->threadId == getproctid()) {`
- 前置条件: callbackContext指针为空
- 触发路径: 调用路径推导：NapiHiSysEventQuerier构造函数 -> 析构函数/OnQuery/OnComplete方法。数据流：callbackContext通过构造函数参数传入，但在析构函数和成员方法中使用前未进行判空检查。关键调用点：NapiHiSysEventQuerier构造函数未对callbackContext参数进行非空校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在构造函数中添加callbackContext参数的非空校验；2. 在所有使用callbackContext的成员方法中添加判空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [95] interfaces/js/kits/napi/src/napi_hisysevent_querier.cpp:49 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `napi_delete_reference(callbackContext->env, callbackContext->ref);`
- 前置条件: callbackContext指针为空
- 触发路径: 调用路径推导：NapiHiSysEventQuerier构造函数 -> 析构函数/OnQuery/OnComplete方法。数据流：callbackContext通过构造函数参数传入，但在析构函数和成员方法中使用前未进行判空检查。关键调用点：NapiHiSysEventQuerier构造函数未对callbackContext参数进行非空校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在构造函数中添加callbackContext参数的非空校验；2. 在所有使用callbackContext的成员方法中添加判空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [96] interfaces/js/kits/napi/src/napi_hisysevent_querier.cpp:57 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `jsCallbackManager->Add(callbackContext,`
- 前置条件: callbackContext指针为空
- 触发路径: 调用路径推导：NapiHiSysEventQuerier构造函数 -> 析构函数/OnQuery/OnComplete方法。数据流：callbackContext通过构造函数参数传入，但在析构函数和成员方法中使用前未进行判空检查。关键调用点：NapiHiSysEventQuerier构造函数未对callbackContext参数进行非空校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在构造函数中添加callbackContext参数的非空校验；2. 在所有使用callbackContext的成员方法中添加判空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [97] interfaces/js/kits/napi/src/napi_hisysevent_querier.cpp:80 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `jsCallbackManager->Add(callbackContext,`
- 前置条件: callbackContext指针为空
- 触发路径: 调用路径推导：NapiHiSysEventQuerier构造函数 -> 析构函数/OnQuery/OnComplete方法。数据流：callbackContext通过构造函数参数传入，但在析构函数和成员方法中使用前未进行判空检查。关键调用点：NapiHiSysEventQuerier构造函数未对callbackContext参数进行非空校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在构造函数中添加callbackContext参数的非空校验；2. 在所有使用callbackContext的成员方法中添加判空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [98] interfaces/js/kits/napi/src/napi_hisysevent_querier.cpp:106 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `this->onCompleteHandler(this->callbackContext->env, this->callbackContext->ref);`
- 前置条件: callbackContext指针为空
- 触发路径: 调用路径推导：NapiHiSysEventQuerier构造函数 -> 析构函数/OnQuery/OnComplete方法。数据流：callbackContext通过构造函数参数传入，但在析构函数和成员方法中使用前未进行判空检查。关键调用点：NapiHiSysEventQuerier构造函数未对callbackContext参数进行非空校验。
- 后果: 空指针解引用导致程序崩溃
- 建议: 1. 在构造函数中添加callbackContext参数的非空校验；2. 在所有使用callbackContext的成员方法中添加判空检查
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [99] interfaces/js/kits/napi/src/napi_hisysevent_listener.cpp:47 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `if (callbackContext->threadId == getproctid()) {`
- 前置条件: callbackContext指针被意外修改为nullptr或析构函数被异常调用
- 触发路径: 调用路径推导：AddWatcher() -> std::make_shared<NapiHiSysEventListener>() -> ~NapiHiSysEventListener()。数据流：callbackContext在AddWatcher函数中通过new创建并初始化，传递给NapiHiSysEventListener构造函数，存储在成员变量中。在析构函数中直接解引用callbackContext而未检查空指针。关键调用点：析构函数未对callbackContext进行空指针检查。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在析构函数中对callbackContext添加空指针检查，例如：if (callbackContext != nullptr) {...}
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [100] interfaces/js/kits/napi/src/napi_hisysevent_listener.cpp:48 (c/cpp, memory_mgmt)
- 模式: possible_null_deref
- 证据: `napi_delete_reference(callbackContext->env, callbackContext->ref);`
- 前置条件: callbackContext指针被意外修改为nullptr或析构函数被异常调用
- 触发路径: 调用路径推导：AddWatcher() -> std::make_shared<NapiHiSysEventListener>() -> ~NapiHiSysEventListener()。数据流：callbackContext在AddWatcher函数中通过new创建并初始化，传递给NapiHiSysEventListener构造函数，存储在成员变量中。在析构函数中直接解引用callbackContext而未检查空指针。关键调用点：析构函数未对callbackContext进行空指针检查。
- 后果: 空指针解引用导致程序崩溃
- 建议: 在析构函数中对callbackContext添加空指针检查，例如：if (callbackContext != nullptr) {...}
- 置信度: 0.6, 严重性: high, 评分: 1.8

### [101] interfaces/js/kits/napi/src/napi_hisysevent_js.cpp:144 (c/cpp, memory_mgmt)
- 模式: alloc_no_null_check
- 证据: `CallbackContext* callbackContext = new CallbackContext();`
- 前置条件: 内存分配失败
- 触发路径: 调用路径推导：Write()/AddWatcher()/Query() -> new 操作。数据流：直接调用 new 分配内存。关键调用点：AddWatcher() 和 Query() 函数未对 new 操作结果进行 null 检查
- 后果: 内存分配失败导致空指针解引用，可能引发程序崩溃
- 建议: 1. 使用 new(std::nothrow) 替代 new 2. 添加 null 检查逻辑
- 置信度: 0.8, 严重性: high, 评分: 2.4

### [102] interfaces/js/kits/napi/src/napi_hisysevent_js.cpp:232 (c/cpp, memory_mgmt)
- 模式: alloc_no_null_check
- 证据: `CallbackContext* callbackContext = new CallbackContext();`
- 前置条件: 内存分配失败
- 触发路径: 调用路径推导：Write()/AddWatcher()/Query() -> new 操作。数据流：直接调用 new 分配内存。关键调用点：AddWatcher() 和 Query() 函数未对 new 操作结果进行 null 检查
- 后果: 内存分配失败导致空指针解引用，可能引发程序崩溃
- 建议: 1. 使用 new(std::nothrow) 替代 new 2. 添加 null 检查逻辑
- 置信度: 0.8, 严重性: high, 评分: 2.4

### [103] interfaces/rust/innerkits/src/sys_event_manager.rs:212 (rust, unsafe_usage)
- 模式: unsafe
- 证据: `let level_arr = unsafe {`
- 前置条件: self.level, self.tag 或 self.json_str 指针为空或指向无效的C字符串
- 触发路径: 调用路径推导：外部调用 -> get_level()/get_tag()/get_json_str() -> unsafe CString::from_raw。数据流：原始指针通过结构体字段传递到方法中，方法直接使用unsafe块转换指针为CString，未进行有效性检查。关键调用点：get_level()/get_tag()/get_json_str()方法未对原始指针进行有效性验证。
- 后果: 可能导致未定义行为，包括程序崩溃或内存安全问题
- 建议: 1. 在调用CString::from_raw前验证指针非空；2. 确保指针指向有效的以null结尾的C字符串；3. 考虑使用Option<*mut c_char>类型明确表示可能为空的指针
- 置信度: 0.8, 严重性: high, 评分: 2.4

### [104] interfaces/rust/innerkits/src/sys_event_manager.rs:221 (rust, unsafe_usage)
- 模式: unsafe
- 证据: `let tag_arr = unsafe {`
- 前置条件: self.level, self.tag 或 self.json_str 指针为空或指向无效的C字符串
- 触发路径: 调用路径推导：外部调用 -> get_level()/get_tag()/get_json_str() -> unsafe CString::from_raw。数据流：原始指针通过结构体字段传递到方法中，方法直接使用unsafe块转换指针为CString，未进行有效性检查。关键调用点：get_level()/get_tag()/get_json_str()方法未对原始指针进行有效性验证。
- 后果: 可能导致未定义行为，包括程序崩溃或内存安全问题
- 建议: 1. 在调用CString::from_raw前验证指针非空；2. 确保指针指向有效的以null结尾的C字符串；3. 考虑使用Option<*mut c_char>类型明确表示可能为空的指针
- 置信度: 0.8, 严重性: high, 评分: 2.4

### [105] interfaces/rust/innerkits/src/sys_event_manager.rs:231 (rust, unsafe_usage)
- 模式: unsafe
- 证据: `let json_str_arr = unsafe {`
- 前置条件: self.level, self.tag 或 self.json_str 指针为空或指向无效的C字符串
- 触发路径: 调用路径推导：外部调用 -> get_level()/get_tag()/get_json_str() -> unsafe CString::from_raw。数据流：原始指针通过结构体字段传递到方法中，方法直接使用unsafe块转换指针为CString，未进行有效性检查。关键调用点：get_level()/get_tag()/get_json_str()方法未对原始指针进行有效性验证。
- 后果: 可能导致未定义行为，包括程序崩溃或内存安全问题
- 建议: 1. 在调用CString::from_raw前验证指针非空；2. 确保指针指向有效的以null结尾的C字符串；3. 考虑使用Option<*mut c_char>类型明确表示可能为空的指针
- 置信度: 0.8, 严重性: high, 评分: 2.4

### [106] interfaces/rust/innerkits/src/sys_event_manager.rs:213 (rust, unsafe_usage)
- 模式: raw_pointer
- 证据: `std::ffi::CString::from_raw(self.level as *mut std::ffi::c_char)`
- 前置条件: self.level, self.tag 或 self.json_str 指针为空或指向无效的C字符串
- 触发路径: 调用路径推导：外部调用 -> get_level()/get_tag()/get_json_str() -> unsafe CString::from_raw。数据流：原始指针通过结构体字段传递到方法中，方法直接使用unsafe块转换指针为CString，未进行有效性检查。关键调用点：get_level()/get_tag()/get_json_str()方法未对原始指针进行有效性验证。
- 后果: 可能导致未定义行为，包括程序崩溃或内存安全问题
- 建议: 1. 在调用CString::from_raw前验证指针非空；2. 确保指针指向有效的以null结尾的C字符串；3. 考虑使用Option<*mut c_char>类型明确表示可能为空的指针
- 置信度: 0.75, 严重性: medium, 评分: 1.5

### [107] interfaces/rust/innerkits/src/sys_event_manager.rs:222 (rust, unsafe_usage)
- 模式: raw_pointer
- 证据: `std::ffi::CString::from_raw(self.tag as *mut std::ffi::c_char)`
- 前置条件: self.level, self.tag 或 self.json_str 指针为空或指向无效的C字符串
- 触发路径: 调用路径推导：外部调用 -> get_level()/get_tag()/get_json_str() -> unsafe CString::from_raw。数据流：原始指针通过结构体字段传递到方法中，方法直接使用unsafe块转换指针为CString，未进行有效性检查。关键调用点：get_level()/get_tag()/get_json_str()方法未对原始指针进行有效性验证。
- 后果: 可能导致未定义行为，包括程序崩溃或内存安全问题
- 建议: 1. 在调用CString::from_raw前验证指针非空；2. 确保指针指向有效的以null结尾的C字符串；3. 考虑使用Option<*mut c_char>类型明确表示可能为空的指针
- 置信度: 0.75, 严重性: medium, 评分: 1.5

### [108] interfaces/rust/innerkits/src/sys_event_manager.rs:232 (rust, unsafe_usage)
- 模式: raw_pointer
- 证据: `std::ffi::CString::from_raw(self.json_str as *mut std::ffi::c_char)`
- 前置条件: self.level, self.tag 或 self.json_str 指针为空或指向无效的C字符串
- 触发路径: 调用路径推导：外部调用 -> get_level()/get_tag()/get_json_str() -> unsafe CString::from_raw。数据流：原始指针通过结构体字段传递到方法中，方法直接使用unsafe块转换指针为CString，未进行有效性检查。关键调用点：get_level()/get_tag()/get_json_str()方法未对原始指针进行有效性验证。
- 后果: 可能导致未定义行为，包括程序崩溃或内存安全问题
- 建议: 1. 在调用CString::from_raw前验证指针非空；2. 确保指针指向有效的以null结尾的C字符串；3. 考虑使用Option<*mut c_char>类型明确表示可能为空的指针
- 置信度: 0.75, 严重性: medium, 评分: 1.5

### [109] interfaces/rust/innerkits/src/sys_event_manager.rs:143 (rust, error_handling)
- 模式: unwrap/expect
- 证据: `std::str::from_utf8(&self.domain).expect("                       ")`
- 前置条件: 输入的字节数组包含非UTF-8编码数据
- 触发路径: 调用路径推导：外部输入 -> HiSysEventRecord结构体初始化 -> get_domain()/get_event_name()/get_time_zone() -> std::str::from_utf8().expect()。数据流：外部输入直接填充到HiSysEventRecord的domain/event_name/tz数组字段，调用getter方法时未验证UTF-8有效性直接转换。关键调用点：所有getter方法都未对字节数组进行UTF-8有效性校验。
- 后果: 当输入包含无效UTF-8序列时会导致panic，可能造成服务中断
- 建议: 使用from_utf8_lossy()替代expect()，或在使用前验证UTF-8有效性
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [110] interfaces/rust/innerkits/src/sys_event_manager.rs:149 (rust, error_handling)
- 模式: unwrap/expect
- 证据: `std::str::from_utf8(&self.event_name).expect("                           ")`
- 前置条件: 输入的字节数组包含非UTF-8编码数据
- 触发路径: 调用路径推导：外部输入 -> HiSysEventRecord结构体初始化 -> get_domain()/get_event_name()/get_time_zone() -> std::str::from_utf8().expect()。数据流：外部输入直接填充到HiSysEventRecord的domain/event_name/tz数组字段，调用getter方法时未验证UTF-8有效性直接转换。关键调用点：所有getter方法都未对字节数组进行UTF-8有效性校验。
- 后果: 当输入包含无效UTF-8序列时会导致panic，可能造成服务中断
- 建议: 使用from_utf8_lossy()替代expect()，或在使用前验证UTF-8有效性
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [111] interfaces/rust/innerkits/src/sys_event_manager.rs:171 (rust, error_handling)
- 模式: unwrap/expect
- 证据: `std::str::from_utf8(&self.tz).expect("                          ")`
- 前置条件: 输入的字节数组包含非UTF-8编码数据
- 触发路径: 调用路径推导：外部输入 -> HiSysEventRecord结构体初始化 -> get_domain()/get_event_name()/get_time_zone() -> std::str::from_utf8().expect()。数据流：外部输入直接填充到HiSysEventRecord的domain/event_name/tz数组字段，调用getter方法时未验证UTF-8有效性直接转换。关键调用点：所有getter方法都未对字节数组进行UTF-8有效性校验。
- 后果: 当输入包含无效UTF-8序列时会导致panic，可能造成服务中断
- 建议: 使用from_utf8_lossy()替代expect()，或在使用前验证UTF-8有效性
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [112] interfaces/rust/innerkits/src/sys_event_manager.rs:215 (rust, error_handling)
- 模式: unwrap/expect
- 证据: `std::str::from_utf8(level_arr.to_bytes()).expect("                        ")`
- 前置条件: 从C指针转换的字符串包含非UTF-8编码数据或空指针
- 触发路径: 调用路径推导：C层输入 -> HiSysEventRecord结构体初始化 -> get_level()/get_tag()/get_json_str() -> std::str::from_utf8().expect()。数据流：C指针通过FFI传递给Rust层，在getter方法中未验证指针有效性直接转换。关键调用点：unsafe块中未对CString::from_raw的结果进行有效性检查。
- 后果: 当C层传入无效指针或非UTF-8数据时会导致panic，可能造成服务中断
- 建议: 添加指针非空检查，使用from_utf8_lossy()替代expect()，或在使用前验证UTF-8有效性
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [113] interfaces/rust/innerkits/src/sys_event_manager.rs:224 (rust, error_handling)
- 模式: unwrap/expect
- 证据: `let tag = std::str::from_utf8(tag_arr.to_bytes()).expect("                      ")`
- 前置条件: 从C指针转换的字符串包含非UTF-8编码数据或空指针
- 触发路径: 调用路径推导：C层输入 -> HiSysEventRecord结构体初始化 -> get_level()/get_tag()/get_json_str() -> std::str::from_utf8().expect()。数据流：C指针通过FFI传递给Rust层，在getter方法中未验证指针有效性直接转换。关键调用点：unsafe块中未对CString::from_raw的结果进行有效性检查。
- 后果: 当C层传入无效指针或非UTF-8数据时会导致panic，可能造成服务中断
- 建议: 添加指针非空检查，使用from_utf8_lossy()替代expect()，或在使用前验证UTF-8有效性
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [114] interfaces/rust/innerkits/src/sys_event_manager.rs:234 (rust, error_handling)
- 模式: unwrap/expect
- 证据: `let json_str = std::str::from_utf8(json_str_arr.to_bytes()).expect("                           ")`
- 前置条件: 从C指针转换的字符串包含非UTF-8编码数据或空指针
- 触发路径: 调用路径推导：C层输入 -> HiSysEventRecord结构体初始化 -> get_level()/get_tag()/get_json_str() -> std::str::from_utf8().expect()。数据流：C指针通过FFI传递给Rust层，在getter方法中未验证指针有效性直接转换。关键调用点：unsafe块中未对CString::from_raw的结果进行有效性检查。
- 后果: 当C层传入无效指针或非UTF-8数据时会导致panic，可能造成服务中断
- 建议: 添加指针非空检查，使用from_utf8_lossy()替代expect()，或在使用前验证UTF-8有效性
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [115] interfaces/rust/innerkits/src/sys_event_manager.rs:373 (rust, error_handling)
- 模式: unwrap/expect
- 证据: `let condition_wrapper = CString::new(query_rules[i].condition).expect("                           ");`
- 前置条件: query_rules[i].condition包含null字节
- 触发路径: 调用路径推导：外部输入 -> query() -> CString::new().expect()。数据流：外部输入的查询条件字符串直接用于创建CString。关键调用点：未检查输入字符串是否包含null字节。
- 后果: 当条件字符串包含null字节时会导致panic，可能造成查询失败
- 建议: 使用CString::new().unwrap_or_default()或过滤掉null字节
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [116] interfaces/rust/innerkits/src/sys_event_manager.rs:213 (rust, ffi)
- 模式: CString/CStr
- 证据: `std::ffi::CString::from_raw(self.level as *mut std::ffi::c_char)`
- 前置条件: 传入的C指针不是有效的、以null结尾的C字符串，或者指针为null
- 触发路径: 调用路径推导：C代码 -> 创建HiSysEventRecord -> Rust调用get_level/get_tag/get_json_str -> from_raw转换。数据流：C代码传入原始指针到HiSysEventRecord结构体，Rust方法直接使用from_raw转换这些指针。关键调用点：所有方法都未对指针进行有效性检查。
- 后果: 可能导致未定义行为、程序崩溃或内存安全问题
- 建议: 1) 在转换前检查指针是否为null；2) 确保C端保证传入的字符串是有效的、以null结尾的；3) 考虑使用CStr而不是CString来避免所有权问题
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [117] interfaces/rust/innerkits/src/sys_event_manager.rs:222 (rust, ffi)
- 模式: CString/CStr
- 证据: `std::ffi::CString::from_raw(self.tag as *mut std::ffi::c_char)`
- 前置条件: 传入的C指针不是有效的、以null结尾的C字符串，或者指针为null
- 触发路径: 调用路径推导：C代码 -> 创建HiSysEventRecord -> Rust调用get_level/get_tag/get_json_str -> from_raw转换。数据流：C代码传入原始指针到HiSysEventRecord结构体，Rust方法直接使用from_raw转换这些指针。关键调用点：所有方法都未对指针进行有效性检查。
- 后果: 可能导致未定义行为、程序崩溃或内存安全问题
- 建议: 1) 在转换前检查指针是否为null；2) 确保C端保证传入的字符串是有效的、以null结尾的；3) 考虑使用CStr而不是CString来避免所有权问题
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [118] interfaces/rust/innerkits/src/sys_event_manager.rs:232 (rust, ffi)
- 模式: CString/CStr
- 证据: `std::ffi::CString::from_raw(self.json_str as *mut std::ffi::c_char)`
- 前置条件: 传入的C指针不是有效的、以null结尾的C字符串，或者指针为null
- 触发路径: 调用路径推导：C代码 -> 创建HiSysEventRecord -> Rust调用get_level/get_tag/get_json_str -> from_raw转换。数据流：C代码传入原始指针到HiSysEventRecord结构体，Rust方法直接使用from_raw转换这些指针。关键调用点：所有方法都未对指针进行有效性检查。
- 后果: 可能导致未定义行为、程序崩溃或内存安全问题
- 建议: 1) 在转换前检查指针是否为null；2) 确保C端保证传入的字符串是有效的、以null结尾的；3) 考虑使用CStr而不是CString来避免所有权问题
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [119] interfaces/rust/innerkits/src/sys_event_manager.rs:213 (rust, unsafe_usage)
- 模式: from_raw_parts/from_raw
- 证据: `std::ffi::CString::from_raw(self.level as *mut std::ffi::c_char)`
- 前置条件: C/C++端传入的level/tag/json_str指针无效或未正确分配
- 触发路径: 调用路径推导：C/C++代码 -> GetHiSysEventRecordByIndexWrapper() -> Rust代码 -> get_level()/get_tag()/get_json_str() -> CString::from_raw()。数据流：C/C++端创建HiSysEventRecord并设置指针字段，通过FFI传递给Rust端，Rust直接使用from_raw转换这些指针。关键调用点：Rust端未对指针进行有效性验证，也未明确指针所有权。
- 后果: 可能导致空指针解引用、访问无效内存、双重释放或内存泄漏
- 建议: 1. 在Rust端添加指针有效性检查；2. 明确指针所有权协议；3. 考虑使用更安全的FFI包装器或自动生成绑定
- 置信度: 0.85, 严重性: high, 评分: 2.55

### [120] interfaces/rust/innerkits/src/sys_event_manager.rs:222 (rust, unsafe_usage)
- 模式: from_raw_parts/from_raw
- 证据: `std::ffi::CString::from_raw(self.tag as *mut std::ffi::c_char)`
- 前置条件: C/C++端传入的level/tag/json_str指针无效或未正确分配
- 触发路径: 调用路径推导：C/C++代码 -> GetHiSysEventRecordByIndexWrapper() -> Rust代码 -> get_level()/get_tag()/get_json_str() -> CString::from_raw()。数据流：C/C++端创建HiSysEventRecord并设置指针字段，通过FFI传递给Rust端，Rust直接使用from_raw转换这些指针。关键调用点：Rust端未对指针进行有效性验证，也未明确指针所有权。
- 后果: 可能导致空指针解引用、访问无效内存、双重释放或内存泄漏
- 建议: 1. 在Rust端添加指针有效性检查；2. 明确指针所有权协议；3. 考虑使用更安全的FFI包装器或自动生成绑定
- 置信度: 0.85, 严重性: high, 评分: 2.55

### [121] interfaces/rust/innerkits/src/sys_event_manager.rs:232 (rust, unsafe_usage)
- 模式: from_raw_parts/from_raw
- 证据: `std::ffi::CString::from_raw(self.json_str as *mut std::ffi::c_char)`
- 前置条件: C/C++端传入的level/tag/json_str指针无效或未正确分配
- 触发路径: 调用路径推导：C/C++代码 -> GetHiSysEventRecordByIndexWrapper() -> Rust代码 -> get_level()/get_tag()/get_json_str() -> CString::from_raw()。数据流：C/C++端创建HiSysEventRecord并设置指针字段，通过FFI传递给Rust端，Rust直接使用from_raw转换这些指针。关键调用点：Rust端未对指针进行有效性验证，也未明确指针所有权。
- 后果: 可能导致空指针解引用、访问无效内存、双重释放或内存泄漏
- 建议: 1. 在Rust端添加指针有效性检查；2. 明确指针所有权协议；3. 考虑使用更安全的FFI包装器或自动生成绑定
- 置信度: 0.85, 严重性: high, 评分: 2.55

### [122] interfaces/rust/innerkits/src/utils.rs:20 (rust, ffi)
- 模式: CString/CStr
- 证据: `let name = CString::new(src).unwrap();`
- 前置条件: 输入字符串长度超过目标缓冲区大小
- 触发路径: 调用路径推导：sys_event_manager.rs中的HiSysEvent查询/写入函数 -> trans_slice_to_array()。数据流：查询/写入参数通过FFI接口传入，在sys_event_manager.rs中部分调用点进行了长度校验(line 382-387)，但sys_event.rs中的调用点未直接校验输入长度。关键调用点：sys_event.rs中的write函数未对event_params[i].param_name长度进行校验。
- 后果: 可能导致缓冲区溢出或数据截断
- 建议: 1. 在trans_slice_to_array函数中添加输入长度校验 2. 使用expect替代unwrap提供更有意义的错误信息 3. 确保所有调用点都进行输入长度校验
- 置信度: 0.65, 严重性: medium, 评分: 1.3

### [123] interfaces/rust/innerkits/src/utils.rs:20 (rust, error_handling)
- 模式: unwrap/expect
- 证据: `let name = CString::new(src).unwrap();`
- 前置条件: 输入字符串 src 包含空字节(null byte)
- 触发路径: 调用路径推导：外部调用者 -> trans_slice_to_array() -> CString::new().unwrap()。数据流：外部传入的字符串src直接传递给CString::new()，未进行空字节检查。关键调用点：trans_slice_to_array()函数未对输入进行空字节校验。
- 后果: 程序panic，可能导致服务中断
- 建议: 使用expect提供更有意义的错误信息，或使用match/Result进行显式错误处理
- 置信度: 0.65, 严重性: medium, 评分: 1.3
