// Negative case: Safe FFI with NULL pointer validation
// Always check pointers from FFI before using them.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::ptr::NonNull;

extern "C" {
    fn get_string() -> *const c_char;
    fn allocate_buffer(size: usize) -> *mut u8;
    fn find_user(id: u32) -> *const User;
}

struct User {
    id: u32,
    name: [c_char; 64],
}

// SAFE: Check NULL before using
unsafe fn safe_ffi_string() -> Option<&'static str> {
    let ptr = get_string();
    if ptr.is_null() {
        return None;
    }
    // SAFETY: ptr is verified non-NULL
    let c_str = CStr::from_ptr(ptr);
    Some(c_str.to_str().unwrap())
}

// SAFE: Using NonNull type
unsafe fn safe_buffer() -> Option<&mut [u8]> {
    let buf = allocate_buffer(1024);
    NonNull::new(buf).map(|p| {
        // SAFETY: p is non-NULL, size matches allocation
        std::slice::from_raw_parts_mut(p.as_ptr(), 1024)
    })
}

// SAFE: Early return on NULL
unsafe fn safe_get_user(id: u32) -> Option<&'static str> {
    let user = find_user(id);
    if user.is_null() {
        return None;
    }
    // SAFETY: user is verified non-NULL
    CStr::from_ptr((*user).name.as_ptr()).to_str().ok()
}

// SAFE: Validate before copy
unsafe fn safe_write_to_buffer(data: &[u8]) -> Result<(), &'static str> {
    let buf = allocate_buffer(data.len());
    if buf.is_null() {
        return Err("allocation failed");
    }
    // SAFETY: buf is non-NULL, size matches data.len()
    std::ptr::copy_nonoverlapping(data.as_ptr(), buf, data.len());
    Ok(())
}

fn main() {
    unsafe {
        if let Some(s) = safe_ffi_string() {
            println!("String: {}", s);
        } else {
            println!("No string returned");
        }
    }
}
