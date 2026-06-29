// Positive case: CWE-787 Out-of-bounds Write
// Buffer overflow vulnerabilities through unsafe code and FFI.
// Writing beyond buffer boundaries causes memory corruption.

use std::os::raw::c_char;
use std::ptr;

extern "C" {
    fn c_memcpy(dest: *mut u8, src: *const u8, n: usize) -> *mut u8;
    fn c_strcpy(dest: *mut c_char, src: *const c_char) -> *mut c_char;
    fn c_get_buffer() -> *mut u8;
    fn c_get_buffer_size() -> usize;
}

// VULNERABLE: Write past buffer end via pointer arithmetic
unsafe fn write_past_end(buffer: &mut [u8], offset: usize, data: u8) {
    let ptr = buffer.as_mut_ptr();
    *ptr.add(offset) = data; // No bounds check, may write past end
}

// VULNERABLE: Copy without size validation
unsafe fn copy_to_buffer(dest: *mut u8, src: &[u8], dest_size: usize) {
    // Copies src.len() bytes without checking dest_size
    ptr::copy_nonoverlapping(src.as_ptr(), dest, src.len()); // Buffer overflow!
}

// VULNERABLE: FFI write with wrong size
unsafe fn ffi_buffer_overflow(data: &[u8]) {
    let buf = c_get_buffer();
    let size = c_get_buffer_size();

    // Writing more than buffer size
    for i in 0..data.len() {
        *buf.add(i) = data[i]; // Overflow if data.len() > size
    }
}

// VULNERABLE: strcpy into fixed-size buffer
unsafe fn unsafe_strcpy(buffer: &mut [u8; 64], input: &str) {
    let c_input = std::ffi::CString::new(input).unwrap();
    c_strcpy(buffer.as_mut_ptr() as *mut c_char, c_input.as_ptr()); // No length check!
}

// VULNERABLE: Write through slice with wrong length
unsafe fn write_with_wrong_length(buffer: *mut u8, actual_size: usize, claimed_size: usize) {
    let slice = std::slice::from_raw_parts_mut(buffer, claimed_size); // Wrong size!
    for i in 0..claimed_size {
        slice[i] = 0xFF; // Writes past actual_size
    }
}

// VULNERABLE: Array index out of bounds
unsafe fn index_out_of_bounds(arr: &[u8], idx: usize) -> u8 {
    *arr.get_unchecked(idx) // No bounds check
}

// VULNERABLE: Write via FFI without validation
unsafe fn write_via_ffi(buf: *mut u8, data: &[u8]) {
    c_memcpy(buf, data.as_ptr(), data.len()); // No dest size check
}

// VULNERABLE: Format string into fixed buffer
unsafe fn format_overflow(buffer: &mut [u8; 64], user_input: &str) {
    let msg = format!("User: {}", user_input); // May exceed 64 bytes
    for (i, b) in msg.bytes().enumerate() {
        buffer[i] = b; // Overflow if msg too long
    }
}

fn main() {
    unsafe {
        let mut buf = [0u8; 10];
        write_past_end(&mut buf, 15, 0xFF); // Writes past buffer!
    }
}
