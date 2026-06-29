// Negative case: safe function (no unsafe fn)
// Regular safe functions are verified by the borrow checker.

fn safe_read(slice: &[u8], index: usize) -> Option<u8> {
    slice.get(index).copied()
}

fn safe_write(slice: &mut [u8], index: usize, val: u8) -> bool {
    if index < slice.len() {
        slice[index] = val;
        true
    } else {
        false
    }
}

fn main() {
    let mut data = [0u8; 10];
    safe_write(&mut data, 0, 42);
    if let Some(val) = safe_read(&data, 0) {
        println!("val: {}", val);
    }
}
