// Positive case: CWE-125 Out-of-bounds Read
// In Rust, safe code panics on OOB access, but unsafe code can bypass checks.
// This can lead to information disclosure or memory corruption.

use std::slice;

// VULNERABLE: Direct pointer arithmetic without bounds check
unsafe fn read_at_index(ptr: *const u8, index: usize) -> u8 {
    // No validation that index is within bounds
    *ptr.add(index) // Can read arbitrary memory if index is attacker-controlled
}

// VULNERABLE: Creating slice from raw parts without validation
unsafe fn create_slice(ptr: *const u8, len: usize) -> &[u8] {
    // len may exceed actual buffer size
    slice::from_raw_parts(ptr, len) // Can read past buffer boundary
}

// VULNERABLE: Using get_unchecked without prior bounds check
fn unsafe_access(arr: &[u8], index: usize) -> u8 {
    // SAFETY comment missing, no bounds validation
    unsafe {
        *arr.get_unchecked(index) // Assumes index is valid without checking
    }
}

// VULNERABLE: Pointer offset without validation
unsafe fn offset_read(base: *const i32, offset: isize) -> i32 {
    // offset could be negative or exceed bounds
    *base.offset(offset) // Arbitrary memory read
}

fn main() {
    let data = [1, 2, 3, 4, 5];
    let ptr = data.as_ptr();

    // Attacker-controlled index could read past array
    let value = unsafe { read_at_index(ptr, 100) }; // OOB read
    println!("Read: {}", value);
}
