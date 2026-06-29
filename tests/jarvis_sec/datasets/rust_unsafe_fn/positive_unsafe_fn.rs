// Positive case: unsafe fn declaration without SAFETY comment
// unsafe fn declares a function that callers must uphold safety invariants.
// The checker should detect unsafe fn as a security boundary that needs documentation.

unsafe fn raw_read(ptr: *const u8) -> u8 {
    *ptr
}

unsafe fn raw_write(ptr: *mut u8, val: u8) {
    *ptr = val;
}

fn main() {
    let mut x: u8 = 42;
    unsafe {
        raw_write(&mut x, 10);
        let val = raw_read(&x);
        println!("val: {}", val);
    }
}
