/*
 * 正例：throw无catch
 * 预期：应该检测到 uncaught_exception
 */
void foo() {
  throw 42; // 真实风险：未捕获异常
}
