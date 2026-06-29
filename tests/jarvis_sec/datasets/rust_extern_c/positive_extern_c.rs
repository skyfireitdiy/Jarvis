// Positive case: extern C declaration
extern "C" {
    fn malloc(size: usize) -> *mut u8;
    fn free(ptr: *mut u8);
}

fn main() {
    unsafe {
        let ptr = malloc(100);
        free(ptr);
    }
}
