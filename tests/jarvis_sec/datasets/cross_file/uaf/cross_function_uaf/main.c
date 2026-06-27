int main() {
    void* buffer = get_buffer();
    release_buffer(buffer);
    use_buffer(buffer);  // UAF: 释放后调用use函数
    return 0;
}
