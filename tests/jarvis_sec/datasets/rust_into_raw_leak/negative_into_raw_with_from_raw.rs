// Negative case: into_raw with matching from_raw - properly managed
// When into_raw() is called, from_raw() is also called to reclaim ownership.

use std::boxed::Box;
use std::ffi::CString;

fn managed_cstring() {
    let c_string = CString::new("hello").unwrap();
    let ptr = c_string.into_raw();
    // ... use ptr for FFI ...
    // SAFE: from_raw reclaims ownership, CString will be dropped
    unsafe {
        let _ = CString::from_raw(ptr as *mut i8);
    }
}

fn managed_box() {
    let boxed = Box::new(42);
    let ptr = Box::into_raw(boxed);
    // ... use ptr ...
    // SAFE: from_raw reclaims ownership, Box will be dropped
    unsafe {
        let _ = Box::from_raw(ptr);
    }
}

fn main() {
    managed_cstring();
    managed_box();
}
