# Rust 性能优化规则（基于 Perf 分析）

> **注意**：本规则专为 LLM Agent 设计，所有性能分析结果应输出为文本格式（而非可视化图表），便于程序化分析和处理。

## 你必须遵守的性能分析流程

### 1. 性能数据采集原则（必须遵守）

**执行要求：**

- **必须**：在优化前先使用 perf 采集性能数据
- **必须**：使用 release 模式编译（带调试符号）
- **必须**：采集足够长的时间样本（避免数据偏差）
- **禁止**：在没有性能数据的情况下进行盲目优化

**编译配置：**

在 `Cargo.toml` 中配置带调试信息的 release 构建：

```toml
[profile.release]
debug = true          # 保留调试符号用于 perf 分析
opt-level = 3         # 最高优化级别
lto = true           # 启用链接时优化
codegen-units = 1    # 单一代码生成单元以获得更好的优化
```

### 2. Perf 数据采集步骤（必须执行）

**步骤 1：编译程序**

```bash
# 编译带调试符号的 release 版本
cargo build --release

# 确认调试符号存在
file target/release/your_binary
# 输出应包含 "not stripped"
```

**步骤 2：运行 Perf 采集**

```bash
# 基本性能采集（CPU 热点）
perf record -F 99 -g --call-graph=dwarf ./target/release/your_binary

# 采集更详细的信息
perf record -F 999 -g --call-graph=dwarf -e cycles:u,instructions:u ./target/release/your_binary

# 采集特定进程
perf record -F 99 -g --call-graph=dwarf -p <PID>

# 采集缓存未命中
perf record -e cache-misses,cache-references -g ./target/release/your_binary

# 采集分支预测失败
perf record -e branch-misses,branches -g ./target/release/your_binary
```

**步骤 3：分析性能数据**

```bash
# 生成文本格式性能报告（必须执行）
perf report --stdio --sort=overhead,symbol > perf_report.txt

# 生成详细的调用链报告
perf report --stdio -g graph,0.5,caller > perf_callgraph.txt

# 查看热点函数的源代码注解
perf annotate --stdio function_name > perf_annotate.txt

# 生成统计摘要
perf report --stdio --percent-limit 5 > perf_hotspots.txt
```

**必须关注的指标：**

在 `perf report --stdio` 输出的文本报告中，你需要重点分析：

- **Overhead**：函数占用 CPU 时间的百分比（>5% 为热点，>10% 为高优先级优化目标）
- **Self**：函数自身的时间消耗（不包括调用的子函数）
- **Children**：函数及其调用的子函数的总时间
- **Symbol**：函数符号名称（Rust 函数名经过 mangling，需要 demangle）
- **Shared Object**：函数所属的库或二进制文件

**解读文本报告示例：**

```
# Overhead  Command  Shared Object      Symbol
# ........  .......  .................  ......................
    45.23%  binary   binary             [.] hot_function
    15.67%  binary   binary             [.] alloc::vec::Vec::push
     8.91%  binary   libc.so.6          [.] memcpy
     5.34%  binary   binary             [.] compute_heavy
```

在上例中：`hot_function` 占用 45.23% CPU 时间，是首要优化目标。

### 3. 热点识别与优化优先级（必须遵守）

**识别热点函数：**

- **必须**：优先优化 overhead > 10% 的函数
- **必须**：关注调用次数多但单次耗时短的函数（累积耗时高）
- **必须**：分析热点函数的调用链（parent-child 关系）
- **禁止**：优化 overhead < 1% 的函数（收益低）

**优化优先级排序：**

1. **高优先级**：overhead > 10% 的函数
2. **中优先级**：5% < overhead < 10% 的函数
3. **低优先级**：1% < overhead < 5% 的函数
4. **忽略**：overhead < 1% 的函数

**分析文本报告的步骤：**

```bash
# 1. 查看整体热点分布（只显示 >5% 的函数）
perf report --stdio --percent-limit 5 --sort=overhead,symbol

# 2. 分析特定热点函数的调用关系
perf report --stdio -g graph,0.5,caller --symbol=hot_function_name

# 3. 查看函数的详细代码注解（哪些代码行最耗时）
perf annotate --stdio hot_function_name

# 4. 统计缓存和分支预测问题
perf stat -e cache-misses,cache-references,branch-misses,branches ./binary
```

## 如何解读 Perf 文本报告（必须掌握）

### 报告格式说明

**基础报告格式** (`perf report --stdio`)：

```
# Overhead  Command  Shared Object      Symbol
# ........  .......  .................  ............................
    15.50%  binary   binary             [.] _ZN4core3ops8function6FnOnce9call_once
    10.23%  binary   binary             [.] alloc::vec::Vec<T>::push
     8.45%  binary   libc.so.6          [.] malloc
```

- **Overhead**：该函数占总采样数的百分比
- **Command**：执行的程序名
- **Shared Object**：函数所在的共享库或二进制文件
- **Symbol**：函数符号（可能需要 demangle）

**调用图报告格式** (`perf report --stdio -g graph`)：

```
    15.50%     0.00%  binary  [.] main
            |
            ---main
               |
               |--10.23% process_data
               |          |
               |          --8.50% Vec::push
               |
               --5.27% compute_result
```

- 显示函数调用关系和各层级的时间占比
- `|--` 表示调用子函数及其时间占比

### 常见热点模式识别

**模式 1：内存分配热点**

```
15.67%  binary  [.] alloc::vec::Vec::push
10.23%  binary  [.] __rust_alloc
 8.91%  binary  [.] malloc
```

**识别要点**：出现 `alloc`、`malloc`、`Vec::push` 等符号
**优化方向**：预分配容量、使用对象池、减少动态分配

**模式 2：循环/迭代热点**

```
25.34%  binary  [.] hot_loop_function
    |
    ---hot_loop_function
       |--15.20% bounds_check
       --10.14% data_access
```

**识别要点**：单个函数 overhead 高，内部有边界检查
**优化方向**：使用迭代器、避免边界检查、循环展开

**模式 3：克隆/复制热点**

```
18.45%  binary  [.] <T as Clone>::clone
12.30%  binary  [.] memcpy
```

**识别要点**：出现 `Clone::clone`、`memcpy` 符号
**优化方向**：使用引用、避免不必要的克隆、使用 Cow

**模式 4：缓存未命中**

```
cache-references:      10,000,000
cache-misses:           3,000,000  # 30% cache miss rate
```

**识别要点**：cache miss rate > 10%
**优化方向**：改善数据局部性、使用 SoA、减少随机访问

## 你必须掌握的 Rust 性能优化技巧

### 1. 内存分配优化（必须检查）

**热点特征：**

- perf 报告显示大量 `alloc::*` 或 `__rust_alloc` 调用
- allocation 相关函数在性能报告中占比高（overhead > 5%）

**优化方法：**

- **必须**：使用 `Vec::with_capacity` 预分配容量
- **必须**：使用 `String::with_capacity` 避免重复分配
- **必须**：使用 `Box::new_uninit` 延迟初始化
- **必须**：使用对象池或 arena 分配器减少小对象分配
- **考虑**：使用 `SmallVec` 或 `ArrayVec` 避免堆分配

```rust
// 错误示例：频繁扩容
let mut vec = Vec::new();
for i in 0..1000 {
    vec.push(i); // 多次重新分配
}

// 正确示例：预分配
let mut vec = Vec::with_capacity(1000);
for i in 0..1000 {
    vec.push(i); // 无需重新分配
}
```

### 2. 迭代器优化（必须检查）

**热点特征：**

- 循环代码占用高 overhead
- perf annotate 显示循环边界检查频繁

**优化方法：**

- **必须**：使用迭代器链替代手动循环
- **必须**：使用 `iter()` 避免不必要的克隆
- **必须**：使用 `chunks()` 或 `par_iter()` 并行处理
- **考虑**：使用 `unsafe` 避免边界检查（需充分测试）

```rust
// 低效示例：手动索引
let mut sum = 0;
for i in 0..data.len() {
    sum += data[i]; // 每次访问都检查边界
}

// 优化示例：使用迭代器
let sum: i32 = data.iter().sum(); // 编译器可更好优化
```

### 3. 克隆与移动优化（必须检查）

**热点特征：**

- perf 显示 `Clone::clone` 或 memcpy 调用频繁
- 大结构体的拷贝操作

**优化方法：**

- **必须**：使用引用 `&T` 或智能指针 `Rc<T>`/`Arc<T>` 避免克隆
- **必须**：使用 `Cow<'_, T>` 延迟克隆
- **必须**：使用 `take()` 或 `replace()` 移动而非克隆
- **考虑**：使用 `#[derive(Copy)]` 对小结构体

```rust
// 低效示例：不必要的克隆
fn process(data: Vec<i32>) -> Vec<i32> {
    data.clone() // 不必要的克隆
}

// 高效示例：直接移动
fn process(data: Vec<i32>) -> Vec<i32> {
    data // 移动所有权
}
```

### 4. 分支预测优化（必须检查）

**热点特征：**

- perf 显示高 branch-miss 率（>10%）
- 热点代码包含大量条件判断

**优化方法：**

- **必须**：使用 `#[cold]` 标记罕见分支
- **必须**：使用 `likely!`/`unlikely!` 提示编译器（需 nightly）
- **必须**：使用 match 替代多层 if-else（更利于优化）
- **考虑**：重组代码减少分支数量

```rust
#[cold]
fn handle_error(err: Error) {
    eprintln!("Error: {:?}", err);
}

fn process(data: Option<i32>) -> i32 {
    if let Some(val) = data {
        val * 2 // 热路径
    } else {
        handle_error(Error::None); // 冷路径
        0
    }
}
```

### 5. 缓存友好性优化（必须检查）

**热点特征：**

- perf 显示高 cache-miss 率（>10%）
- 大数组或随机访问模式

**优化方法：**

- **必须**：使用 `struct of arrays` 替代 `array of structs`（提高缓存局部性）
- **必须**：按顺序访问数据，避免随机跳转
- **必须**：使用 `#[repr(C)]` 或 `#[repr(align(N))]` 控制内存布局
- **考虑**：使用分块处理（blocking）提高缓存命中率

```rust
// 缓存不友好：Array of Structs (AoS)
struct Particle { x: f32, y: f32, z: f32 }
let particles: Vec<Particle> = vec![...];
for p in &particles {
    p.x += 1.0; // 跳过 y, z 字段，缓存浪费
}

// 缓存友好：Struct of Arrays (SoA)
struct Particles {
    x: Vec<f32>,
    y: Vec<f32>,
    z: Vec<f32>,
}
let particles = Particles { ... };
for x in &mut particles.x {
    *x += 1.0; // 连续访问，缓存友好
}
```

### 6. 内联优化（必须检查）

**热点特征：**

- perf 显示大量小函数调用开销
- 函数调用层级深

**优化方法：**

- **必须**：对热路径小函数使用 `#[inline]`
- **必须**：对频繁调用的 trait 方法使用 `#[inline]`
- **考虑**：对关键函数使用 `#[inline(always)]`
- **禁止**：过度内联导致代码膨胀

```rust
// 热路径小函数应内联
#[inline]
fn add(a: i32, b: i32) -> i32 {
    a + b
}

// Trait 方法应内联
trait MyTrait {
    #[inline]
    fn method(&self) -> i32;
}
```

### 7. 并行化优化（必须考虑）

**热点特征：**

- 单个函数占用 CPU 时间 > 30%
- 数据处理可独立并行

**优化方法：**

- **必须**：使用 `rayon` crate 并行化迭代器
- **必须**：使用 `par_iter()` 替代 `iter()` 处理大数据
- **必须**：合理设置线程池大小
- **禁止**：过度并行化（任务粒度太小导致开销高）

```rust
use rayon::prelude::*;

// 串行处理
let results: Vec<_> = data.iter().map(|x| expensive_fn(x)).collect();

// 并行处理
let results: Vec<_> = data.par_iter().map(|x| expensive_fn(x)).collect();
```

## 性能优化工作流程

### 标准流程（必须遵守）

1. **建立性能基准**

   ```bash
   # 使用 criterion 建立基准测试
   cargo bench
   ```

2. **采集性能数据**

   ```bash
   perf record -F 99 -g --call-graph=dwarf ./target/release/binary
   ```

3. **分析热点**

   ```bash
   # 生成按 overhead 排序的性能报告
   perf report --stdio --sort=overhead,symbol > perf_report.txt

   # 生成热点函数列表（仅显示 overhead > 5%）
   perf report --stdio --percent-limit 5 --sort=overhead > perf_hotspots.txt

   # 生成调用链分析报告
   perf report --stdio -g graph,0.5,caller > perf_callgraph.txt
   ```

4. **识别优化目标**
   - 列出 overhead > 5% 的函数
   - 分析调用关系
   - 确定根本原因（内存分配、缓存、分支等）

5. **实施优化**
   - 根据热点类型选择对应优化方法
   - 一次只优化一个热点
   - 保持代码可读性

6. **验证效果**

   ```bash
   # 重新采集性能数据
   perf record -F 99 -g --call-graph=dwarf ./target/release/binary

   # 生成新的性能报告
   perf report --stdio --sort=overhead,symbol > perf_report_after.txt

   # 对比优化前后的文本报告（手动对比或使用 diff 工具）
   diff -u perf_report_before.txt perf_report_after.txt

   # 使用 perf diff 生成差异报告
   perf diff perf.data.before perf.data.after > perf_diff.txt

   # 运行基准测试验证性能提升
   cargo bench
   ```

7. **重复步骤 2-6**
   - 直到达到性能目标
   - 或热点优化收益 < 5%

## 性能优化检查清单

在完成 Rust 性能优化后，你必须确认：

**性能分析：**

- [ ] 使用 perf 采集了充分的性能数据
- [ ] 生成了文本格式的性能报告（perf_report.txt、perf_hotspots.txt 等）
- [ ] 识别了所有 overhead > 5% 的热点函数
- [ ] 分析了热点函数的调用链和根本原因
- [ ] 使用 perf annotate 查看了热点函数的具体代码行

**优化实施：**

- [ ] 优化了内存分配热点（预分配、对象池等）
- [ ] 优化了迭代器和循环代码
- [ ] 减少了不必要的克隆操作
- [ ] 优化了分支预测（使用 #[cold] 等）
- [ ] 提高了缓存友好性（SoA、顺序访问等）
- [ ] 对热路径小函数使用了内联
- [ ] 考虑了并行化（如适用）

**效果验证：**

- [ ] 重新采集了 perf 数据确认优化效果
- [ ] 热点函数的 overhead 明显降低（>30%）
- [ ] 运行了基准测试确认性能提升
- [ ] 确认没有引入新的性能瓶颈

**代码质量：**

- [ ] 优化后代码仍然清晰可读
- [ ] 添加了必要的注释说明优化原因
- [ ] unsafe 代码经过充分测试
- [ ] 性能测试集成到 CI/CD 流程

## 如何对比优化前后的性能（必须掌握）

### 使用 perf diff 对比

```bash
# 1. 采集优化前的数据
perf record -F 99 -g --call-graph=dwarf -o perf.data.before ./binary

# 2. 进行代码优化

# 3. 采集优化后的数据
perf record -F 99 -g --call-graph=dwarf -o perf.data.after ./binary

# 4. 生成对比报告
perf diff perf.data.before perf.data.after > perf_comparison.txt
```

### 解读 perf diff 输出

```
# Baseline  Delta Abs  Shared Object      Symbol
# ........  .........  .................  ........................
    15.50%    -10.23%  binary             [.] hot_function_optimized
     8.20%     +3.15%  binary             [.] helper_function
    10.30%     -0.50%  libc.so.6          [.] malloc
```

- **Baseline**：优化前的 overhead 百分比
- **Delta Abs**：变化量（负数表示优化后减少，正数表示增加）
- 关注点：
  - 目标热点函数的 Delta 应为负值（overhead 降低）
  - 如果某函数 Delta 为正值且较大，需要检查是否引入新的性能问题

### 生成对比摘要报告

```bash
# 提取优化前的热点（top 10）
perf report --stdio -i perf.data.before --percent-limit 1 --sort=overhead | head -20 > before_top10.txt

# 提取优化后的热点（top 10）
perf report --stdio -i perf.data.after --percent-limit 1 --sort=overhead | head -20 > after_top10.txt

# 手动对比两个文件，验证优化效果
```

## 常用 Perf 命令参考

```bash
# 采集 CPU 热点
perf record -F 99 -g --call-graph=dwarf ./binary

# 采集特定事件
perf record -e cpu-cycles,cache-misses,branch-misses -g ./binary

# 查看实时统计
perf stat ./binary

# 查看详细事件列表
perf list

# 对比两次性能数据
perf diff perf.data.old perf.data

# 查看源代码注解（热点代码行）
perf annotate --stdio function_name > function_annotate.txt

# 生成文本格式的性能报告
perf report --stdio --sort=overhead,symbol > perf_report.txt

# 生成调用链文本报告
perf report --stdio -g graph,0.5,caller > perf_callgraph.txt

# 导出详细的调用栈信息（用于进一步分析）
perf script > perf_script.txt
```

## LLM Agent 性能分析工作流程（推荐流程）

作为 LLM Agent，你应该按照以下自动化流程进行性能分析：

### 步骤 1：自动化数据采集

```bash
#!/bin/bash
# 性能数据采集脚本

BINARY="./target/release/your_binary"
PERF_DATA="perf.data"
OUTPUT_DIR="./perf_analysis"

mkdir -p $OUTPUT_DIR

# 采集性能数据
echo "采集性能数据..."
perf record -F 99 -g --call-graph=dwarf -o $PERF_DATA $BINARY

# 生成文本报告
echo "生成性能报告..."
perf report --stdio -i $PERF_DATA --sort=overhead,symbol > $OUTPUT_DIR/perf_report.txt
perf report --stdio -i $PERF_DATA --percent-limit 5 --sort=overhead > $OUTPUT_DIR/perf_hotspots.txt
perf report --stdio -i $PERF_DATA -g graph,0.5,caller > $OUTPUT_DIR/perf_callgraph.txt

echo "性能分析完成，报告位于 $OUTPUT_DIR"
```

### 步骤 2：解析文本报告

你需要读取并解析 `perf_hotspots.txt`，提取关键信息：

1. **识别热点函数列表**：
   - 搜索文本中 Overhead 列 > 5% 的所有函数
   - 提取函数名、overhead 百分比、shared object

2. **分析热点类型**：
   - 如果函数名包含 `alloc`、`Vec::push`、`malloc` → 内存分配热点
   - 如果函数名包含 `clone`、`memcpy` → 克隆/复制热点
   - 如果函数是用户代码中的循环函数 → 循环/迭代热点

3. **读取调用链**：
   - 从 `perf_callgraph.txt` 中找到热点函数的调用关系
   - 确定优化应该在哪个层级进行

### 步骤 3：生成优化建议

基于热点类型，生成具体的优化建议代码示例：

```
热点函数: Vec::push (overhead: 15.67%)
调用位置: process_data() -> loop
问题类型: 内存分配热点

优化建议:
1. 在循环前预分配 Vec 容量
2. 代码示例：
   // 优化前
   let mut vec = Vec::new();
   for item in items { vec.push(item); }

   // 优化后
   let mut vec = Vec::with_capacity(items.len());
   for item in items { vec.push(item); }
```

### 步骤 4：验证优化效果

优化后，重新运行性能采集并对比：

```bash
# 采集优化后的数据
perf record -F 99 -g --call-graph=dwarf -o perf_after.data $BINARY

# 生成对比报告
perf diff perf.data perf_after.data > perf_diff.txt

# 解析 perf_diff.txt，验证目标热点的 Delta 是否为负值
```

### 输出格式示例

你应该输出结构化的分析报告：

```markdown
# 性能分析报告

## 采集信息

- 二进制文件: target/release/binary
- 采样频率: 99 Hz
- 采样时长: 30 秒
- 总样本数: 45,230

## 热点函数（Overhead > 5%）

### 1. hot_function (Overhead: 25.34%)

- **类型**: 用户代码循环热点
- **位置**: src/lib.rs:123
- **调用链**: main -> process_data -> hot_function
- **问题**: 循环中频繁进行边界检查和内存分配
- **优化建议**:
  1. 使用迭代器替代索引访问
  2. 预分配内存避免动态扩容

### 2. alloc::vec::Vec::push (Overhead: 15.67%)

- **类型**: 内存分配热点
- **位置**: 多处调用
- **优化建议**:
  1. 使用 Vec::with_capacity 预分配
  2. 考虑使用 SmallVec 优化小容量场景

## 优化优先级

1. [高优先级] hot_function - 预计可减少 15-20% 总耗时
2. [高优先级] Vec::push 热点 - 预计可减少 10-15% 总耗时
3. [中优先级] clone 操作 - 预计可减少 5-8% 总耗时
```

## 进阶优化技巧

### SIMD 优化（考虑使用）

**适用场景：**

- 大规模数值计算
- 图像/视频处理
- 向量运算

```rust
// 使用 packed_simd 或 std::arch
use std::arch::x86_64::*;

#[target_feature(enable = "avx2")]
unsafe fn simd_add(a: &[f32], b: &[f32], c: &mut [f32]) {
    // SIMD 加速的向量加法
}
```

### Profile-Guided Optimization (PGO)（考虑使用）

```bash
# 步骤 1：生成插桩二进制
RUSTFLAGS="-Cprofile-generate=/tmp/pgo-data" cargo build --release

# 步骤 2：运行代表性工作负载
./target/release/binary

# 步骤 3：使用 profile 数据重新编译
RUSTFLAGS="-Cprofile-use=/tmp/pgo-data/merged.profdata" cargo build --release
```

### 内存分配器替换（考虑使用）

```rust
// 在 Cargo.toml 中添加
[dependencies]
mimalloc = { version = "0.1", default-features = false }

// 在 main.rs 中使用
#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;
```
