int main() {
    void* ptr = malloc(100);
    my_free(ptr);
    my_free(ptr);  // Double Free: 重复释放
    return 0;
}
