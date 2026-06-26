/*
 * 正例：没有任何检查的指针解引用
 * 预期：应该检测到 possible_null_deref
 */
void foo(char *p) {
  *p = 'x'; // 真实风险：没有任何检查
}
