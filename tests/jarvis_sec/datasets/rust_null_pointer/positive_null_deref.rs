// Positive case: CWE-476 NULL Pointer Dereference
// FFI calls may return NULL pointers from C code.
// Using them without validation causes crashes.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;

extern "C" {
    fn get_string() -> *const c_char;
    fn allocate_buffer(size: usize) -> *mut u8;
    fn find_user(id: u32) -> *const User;
}

struct User {
    id: u32,
    name: [c_char; 64],
}

// VULNERABLE: No NULL check before CStr::from_ptr
unsafe fn use_ffi_string() -> &'static str {
    let ptr = get_string(); // May return NULL
    let c_str = CStr::from_ptr(ptr); // Crashes if NULL
    c_str.to_str().unwrap()
}

// VULNERABLE: Dereferencing potentially NULL pointer
unsafe fn use_buffer() -> u8 {
    let buf = allocate_buffer(1024); // May return NULL on allocation failure
    *buf // Dereference without check
}

// VULNERABLE: Accessing struct field through potentially NULL pointer
unsafe fn get_user_name(id: u32) -> &'static str {
    let user = find_user(id); // May return NULL if user not found
    CStr::from_ptr(user.name.as_ptr()).to_str().unwrap() // No NULL check
}

// VULNERABLE: Writing to potentially NULL pointer
unsafe fn write_to_buffer(data: &[u8]) {
    let buf = allocate_buffer(data.len());
    std::ptr::copy_nonoverlapping(data.as_ptr(), buf, data.len()); // No NULL check
}

fn main() {
    unsafe {
        let s = use_ffi_string(); // May crash
        println!("String: {}", s);
    }
}
