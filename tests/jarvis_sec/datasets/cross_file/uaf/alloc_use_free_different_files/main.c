int main() {
    void* ptr = allocate_memory();
    use_memory(ptr);
    free_memory(ptr);
    use_memory(ptr);  // UAF: free后use
    return 0;
}
