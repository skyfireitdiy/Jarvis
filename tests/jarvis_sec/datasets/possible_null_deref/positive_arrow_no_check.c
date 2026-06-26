/*
 * 正例：箭头操作符解引用无检查
 * 预期：应该检测到 possible_null_deref
 */
struct Foo {
  int x;
};
void bar(struct Foo *p) {
  p->x = 10; // 真实风险：没有检查
}
