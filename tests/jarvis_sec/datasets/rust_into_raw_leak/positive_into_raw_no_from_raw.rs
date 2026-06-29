// Positive case: into_raw without matching from_raw causes memory leak
// When into_raw() is called, ownership is transferred to the caller.
// If from_raw() is never called to reclaim ownership, the memory is leaked.

use std::boxed::Box;
use std::ffi::CString;

fn leak_cstring() -> *const i8 {
    let c_string = CString::new("hello").unwrap();
    // VULNERABLE: ownership transferred via into_raw, never reclaimed
    let ptr = c_string.into_raw();
    ptr
    // CString memory is leaked - no from_raw to reclaim it
}

fn leak_box() -> *mut i32 {
    let boxed = Box::new(42);
    // VULNERABLE: Box ownership transferred, never reclaimed
    let ptr = Box::into_raw(boxed);
    ptr
    // Box memory is leaked - no from_raw to reclaim it
}

fn main() {
    let ptr = leak_cstring();
    let bptr = leak_box();
}
