# 任意代码热补丁（hotpatch）方案

**状态**：待审阅（方案讨论中，未最终定稿）
**日期**：2026-10-06
**作者**：Jarvis
**监督者**：skyfire

---

## 1. 背景与目标

Jarvis 目前**没有**任意代码热补丁能力：

- `importlib.import_module` 对已加载模块返回缓存对象，不重新执行代码；
- `register_tool_by_file`（`registry.py:822`）只能加载**新模块**，对**已加载模块的代码更新**不生效；
- `execute_script` 跑在**子进程**，无法修改 Agent 主进程内存。

**目标**：让运行中的 Jarvis Agent 进程能对**自身**做任意代码热补丁——热更新/注入任意 Python 代码，**立即生效**，不重启进程。

**已确认的需求边界**（与 Administrator 对齐）：

1. 支持**两种使用方式**（见第 3 节）；
2. 作用于**正在运行的进程**；
3. **先不考虑安全**（暂不做授权/回滚等防护，但保留异常不崩 Agent 的底线）。

---

## 2. 技术原理

Python 的热补丁依赖三个机制：

### 2.1 `importlib.reload(module)`

重新执行模块代码，使已加载模块的改动立即生效。适用于**热更新已有模块**。

### 2.2 `types.ModuleType` + `exec`

从内存代码动态创建模块对象，注册进 `sys.modules` 后立即可 `import`。适用于**注入全新模块**（无需落盘）。

### 2.3 `sys.modules` 清理 + `importlib.invalidate_caches()`

清除模块缓存强制重新导入（处理依赖方引用），让新增文件可见。

---

## 3. 设计：`hotpatch` Jarvis 工具

新增 `src/jarvis/jarvis_tools/hotpatch.py`，定义 `HotpatchTool` 类（`name = "hotpatch"`）。因位于 `jarvis_tools` 包内，会被 `_load_builtin_tools`（`registry.py:594`）自动扫描注册，无需手动注册。

**运行环境**：工具经 `execute_tool_call` 分发，运行在 **Agent 进程内**，可直接操作 `sys.modules` / `importlib` / `types`，这是热补丁生效的前提。

### 3.1 两种使用方式（核心接口）

| 方式                 | 使用场景                                     | 参数                                      | 实现          |
| -------------------- | -------------------------------------------- | ----------------------------------------- | ------------- |
| **① 生效已修改代码** | 已用 edit/write 改好某个模块，让修改立即生效 | `module_name`（或 `file_path`）           | reload 该模块 |
| **② 临时注入代码**   | 调试自身/临时探针，不落盘，立即生效          | `code`（可选 `module_name` 指定注入位置） | exec 内存注入 |

### 3.2 方式①：让已修改的代码立即生效

- 前置：代码已通过 `edit_file` / `write_file` 写入磁盘文件。
- 调用：`hotpatch(module_name="jarvis.jarvis_tools.load_rule")` 或 `hotpatch(file_path="/path/to/x.py")`。
- 实现：`importlib.reload` 重新执行模块代码；`clear_cache=True` 时先清 `sys.modules` 再 import（强制刷新依赖方）。
- 结果：该模块所有改动立即生效，下次调用即用新代码。

### 3.3 方式②：临时注入代码（调试自身）

- 前置：无，直接给一段内存代码。
- **支持任意语句/代码块**（如 `print(agent.data)`、多行代码块），不限于函数/模块定义。
- 调用（注入为模块）：`hotpatch(new_module_name="my_probe", code="def f(): ...")` → 注册进 `sys.modules`，立即可 `import my_probe`。
- 调用（注入为函数）：`hotpatch(code="def debug_hook(): ...")` → 注入当前模块命名空间，立即可引用。
- 调用（执行语句/代码块）：`hotpatch(code="print(agent.data)")` → 在 agent 上下文命名空间中执行，可访问 `agent` 等运行时对象。
- 实现：`types.ModuleType` + `exec`（模块）/ `exec` 编译（函数）/ `exec` 于 agent 命名空间（语句代码块）。
- 结果：注入代码立即生效，用完可丢弃（本次运行有效，不持久化）。

**agent 上下文注入**：工具经 v1.0 协议调用时，`execute_tool`（`registry.py:1943-1947`）会把当前 Agent 实例注入到 `args["agent"]`。因此方式②执行语句/代码块时，把 `args["agent"]` 放入执行命名空间，即可让注入代码访问 `agent.data`、`agent.output_handler` 等运行时对象，实现"调试自身"。

### 3.4 参数定义

- `module_name`：方式①要生效的已有模块名（也可用于方式②指定注入位置）
- `file_path`：模块文件路径（方式①据此推导模块名）
- `new_module_name`：方式②注入的全新模块名
- `code`：方式②注入的临时代码
- `clear_cache`：方式①是否清缓存后重新导入（默认 false）

### 3.5 返回结构

统一返回 `{"success": bool, "mode": "reload|new_module|function|statement", ...}`，异常全部捕获并返回 `stderr`，**绝不向 Agent 主流程抛出异常**。

### 3.6 访问/修改 agent 之外的对象

方式②执行代码的命名空间**不只注入 `agent`**，还应暴露对进程内任意对象的访问路径：

- `agent`：当前 Agent 实例（`args["agent"]`，由 v1.0 协议注入）。
- `sys`：`sys.modules` 可访问任意已加载模块（`jarvis.config`、`jarvis.jarvis_tools.registry` 等），从而读取/修改其全局状态。
- `GLOBAL_CONFIG_DATA` 等：通过 `sys.modules["jarvis.config"]` 访问全局配置。
- `globals()`：hotpatch 工具所在模块的全局命名空间（已导入 config 等）。

这样注入代码既能"调试自身"（agent），也能**修改/检查 agent 之外的任意对象**（全局配置、registry、其他模块单例等），覆盖 Administrator 提出的场景。

### 3.7 方式①对"已在模块中运行"的生效边界

方式①（reload）的"立即生效"**有明确边界**，需如实文档化：

| 场景                                              | reload 后是否生效                                              |
| ------------------------------------------------- | -------------------------------------------------------------- |
| **后续**通过模块属性访问的调用（`module.func()`） | ✅ 生效                                                        |
| 当前**正在执行**的调用（已入栈）                  | ❌ 本次不生效，等返回后下次调用才用新代码                      |
| 别处 `from module import func` 的**既有绑定**     | ⚠️ `clear_cache=True` 时刷新引用方                             |
| 已有**类实例**                                    | ✅ **默认自动切换**（`instance.__class__` 重绑到新类，见 4.8） |

方式①在 `clear_cache=True` 时清 `sys.modules` 后重新 import，可尽量刷新**引用方模块**（其 `from module import func` 会重新求值）。**已有类实例**通过 `gc.get_objects()` 遍历重绑 `__class__` 到新类，实现"自动切换新方法"（见 4.8）。唯一无法影响的边界是**正在执行的调用**（已入栈，等本次返回后下次调用才用新代码）。这些边界写进工具 description 与返回信息，避免用户误以为"所有场景都立即生效"。

---

## 4. 关键实现细节

### 4.1 方式①：reload 已修改模块

```python
if module_name in sys.modules:
    importlib.reload(sys.modules[module_name])   # 重新执行磁盘上的最新代码
else:
    importlib.import_module(module_name)
```

- `clear_cache=True` 时先 `sys.modules.pop(module_name)` 再 import，强制刷新所有引用方。

### 4.2 方式②：注入全新模块

```python
module = types.ModuleType(module_name)
exec(compile(code, f"<hotpatch:{module_name}>", "exec"), module.__dict__)
sys.modules[module_name] = module   # 之后 import module_name 立即可用
```

### 4.3 方式②：注入全新函数

```python
namespace = {}
exec(compile(code, "<hotpatch:function>", "exec"), namespace)
# 找到新定义的 callable，注入当前模块 globals()
globals()[func_name] = namespace[func_name]
```

### 4.4 方式②：执行任意语句/代码块（含 agent 上下文）

```python
# args["agent"] 由 v1.0 协议自动注入（registry.py:1943-1947）
agent = args.get("agent")
namespace = {
    "agent": agent,
    "sys": sys,
    "globals": globals,
    "__builtins__": __builtins__,
}
exec(compile(code, "<hotpatch:statement>", "exec"), namespace)  # 如 print(agent.data)
```

- 命名空间注入 `agent`、`sys`、`globals`，使注入代码可访问运行时对象（`agent.data`、`sys.modules["jarvis.config"]` 等），既能"调试自身"也能**修改/访问 agent 之外的任意对象**（见 3.6）。
- 通过 `compile(..., "exec")` 可执行任意多行语句/代码块，不限于函数/模块定义。

### 4.6 方式①：批量多模块 reload

`module_name` 支持逗号分隔或列表，逐个 reload；单个失败不影响其他（各自捕获异常并汇总结果），保证"一次 reload 多个模块"。

### 4.7 方式①：reload 边界处理

- `clear_cache=True` 时先 `sys.modules.pop(module_name)` 再 import，强制刷新引用方模块的 `from module import func` 绑定。
- reload 后自动重绑**已有类实例**到新类（见 4.8），实现"自动切换新方法"。
- 返回信息中说明唯一无法影响的边界：正在执行的调用本次不生效（见 3.7），避免误导。

### 4.8 方式①：已有类实例自动切换（重绑 **class**）

`importlib.reload` 会创建**新类对象**，但已存在实例的 `__class__` 仍指向旧类。要自动切换，需把旧类实例重绑到新类：

```python
import gc

def _rebind_instances(module, module_name):
    """reload 后把模块内旧类实例的 __class__ 重绑到新类。"""
    new_classes = {
        name: cls for name, cls in module.__dict__.items()
        if isinstance(cls, type) and getattr(cls, "__module__", None) == module_name
    }
    if not new_classes:
        return 0
    old_classes = {}   # 调用方在 reload 前记录：name -> 旧类对象
    rebound = 0
    for obj in gc.get_objects():
        cls = type(obj)
        if cls.__module__ != module_name:
            continue
        # 精确匹配旧类（不含子类，避免误绑子类实例）
        for name, new_cls in new_classes.items():
            if cls is old_classes.get(name) and cls is not new_cls:
                try:
                    obj.__class__ = new_cls
                    rebound += 1
                except TypeError:
                    pass   # __slots__ / C 类型无法重绑，跳过
    return rebound
```

关键点：

- **reload 前**记录模块内类名 → 旧类对象；reload 后模块内同名属性 → 新类对象，据此建立新旧对应。
- 用 `gc.get_objects()` 遍历整个堆找实例；只重绑 `type(obj) is 旧类`（**精确匹配**，不重绑子类实例，避免破坏子类）。
- 重绑失败（`__slots__`、C 扩展类型、布局不兼容）时静默跳过并计数，不中断 reload。
- 重绑前提：新旧类**结构兼容**（方法签名、属性布局一致）；若用户改了字段布局，重绑后实例可能缺属性——这是用户责任，工具在返回信息中提示。
- 性能：`gc.get_objects()` 遍历堆有成本，但热补丁是低频操作，可接受。
- **关键坑（实现时发现）**：`importlib.reload` 可能复用**过期的 `.pyc` 字节码缓存**，导致源码已改但 reload 后仍是旧代码（`co_consts` 未变）。因此 reload 前必须清理模块 `__file__` 目录下的 `__pycache__`（`shutil.rmtree`），强制重新编译源码，否则"修改后立即生效"会失效。

### 4.5 模块名推导

`_derive_module_name(file_path)`：按 jarvis 包内路径推导（`src/jarvis/jarvis_tools/x.py` → `jarvis.jarvis_tools.x`），否则用文件 stem。

---

## 5. 验证方案

1. **单元测试**（新增 `tests/` 用例）：
   - 方式①：修改模块文件后 reload 生效；
   - 方式①：**批量多模块**（一次 reload 多个模块，单个失败不影响其他）；
   - 方式①：`clear_cache=True` 时引用方 `from module import func` 绑定被刷新；
   - 方式②：注入全新模块立即可 import；
   - 方式②：注入函数立即可调用；
   - 方式②：执行任意语句/代码块（如 `print(agent.data)`）并访问 agent 上下文；
   - 方式②：**访问/修改 agent 之外的对象**（如 `sys.modules["jarvis.config"]` 的全局状态）；
   - 无效参数/异常：返回错误不抛异常；
   - 不影响其他模块。
2. **回归测试**：`tests/jarvis_agent/` 全套通过。
3. **静态检查**：ruff 0 错误。
4. **端到端验证**：通过 `get_tool_registry` 确认 `hotpatch` 工具被发现并调用。

---

## 6. 风险与边界（当前"先不考虑安全"）

- **风险**：热补丁可能破坏运行中的 Agent（如 reload 后模块引用失效）。
- **当前决策**：按 Administrator 要求"先不考虑安全"，不做授权/回滚防护。
- **保留底线**：异常捕获 + 返回错误信息，不向 Agent 主流程抛异常（避免直接崩溃）。
- **后续可增强**（不在本次范围）：补丁白名单、补丁前校验、失败自动回滚、审计记录、注入代码持久化。

---

## 7. 变更清单

| 文件                                       | 变更                    |
| ------------------------------------------ | ----------------------- |
| `src/jarvis/jarvis_tools/hotpatch.py`      | 新增，HotpatchTool 工具 |
| `tests/`（新增测试文件）                   | 验证两种方式            |
| `.jarvis/evolution/evolution_history.json` | 追加记录                |
| `.jarvis/evolution/current_phase.md`       | 更新能力说明            |

---

## 8. 已确认决策（Administrator 拍板）

| #   | 问题                                | 决策                                                                       |
| --- | ----------------------------------- | -------------------------------------------------------------------------- |
| 1   | 方式①（生效已修改代码）是否支持批量 | **支持多模块**（一次 reload 多个模块）                                     |
| 2   | 方式②（临时注入）是否持久化         | **不持久化**（仅本次运行有效，临时）                                       |
| 3   | 是否需要"撤销/回滚"能力             | **不需要**（先不考虑安全）                                                 |
| 4   | 方式②是否支持任意语句/代码块        | **支持**（如 `print(agent.data)`，在 agent 上下文命名空间执行）            |
| 5   | 可访问/修改的对象范围               | **不限于 agent**，需能访问/修改 agent 之外的任意进程内对象（见 3.6 / 4.6） |
| 6   | 方式①对"已在模块中运行"的代码       | **有边界**，如实处理并文档化（见 3.7 / 4.7）                               |

---

## 9. 边界与后续增强（记录，不在本次范围）

- 方式①对**正在执行的调用**不生效（等本次调用返回后，下次调用才用新代码）。
- 方式①对 `from module import func` 的**既有绑定**不自动更新。
- 方式①对**已有类实例**不自动切换新方法（需手动 `instance.__class__ = NewClass`）。
- 后续可增强（不在本次范围）：补丁白名单、补丁前校验、失败自动回滚、审计记录、注入代码持久化。

---

**方案已按上述决策修订完毕，可进入实现。**
