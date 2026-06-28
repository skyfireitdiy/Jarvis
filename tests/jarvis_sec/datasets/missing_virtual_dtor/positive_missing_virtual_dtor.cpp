/*
 * 正例：基类缺少虚析构函数
 * 预期：应该检测到 missing_virtual_dtor
 */
class Base {
public:
  virtual void foo() {} // 虚函数，但析构函数非虚
  ~Base() {}
};
class Derived : public Base {
public:
  ~Derived() {}
};
void bar() {
  Base *b = new Derived();
  delete b; // 真实风险：缺少虚析构函数
}
