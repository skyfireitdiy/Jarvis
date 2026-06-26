/*
 * 正例：基类缺少虚析构函数
 * 预期：应该检测到 missing_virtual_dtor
 */
class Base {
public:
  ~Base() {}
};
class Derived : public Base {
public:
  ~Derived() {}
};
void foo() {
  Base *b = new Derived();
  delete b; // 真实风险：缺少虚析构函数
}
