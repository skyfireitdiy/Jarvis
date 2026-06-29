// Negative case: Safe bounds-checked access patterns
// These patterns prevent out-of-bounds reads by validating indices.

use std::slice;

// SAFE: Using .get() which returns Option
fn read_safe(arr: &[u8], index: usize) -> Option<u8> {
    arr.get(index).copied() // Returns None if out of bounds
}

// SAFE: Bounds check before unsafe access
unsafe fn read_checked(ptr: *const u8, index: usize, max_len: usize) -> Option<u8> {
    if index < max_len {
        // SAFETY: index is verified to be within bounds
        Some(*ptr.add(index))
    } else {
        None
    }
}

// SAFE: Using slice with known length
fn create_safe_slice(data: &[u8], start: usize, len: usize) -> Option<&[u8]> {
    if start.checked_add(len)? <= data.len() {
        Some(&data[start..start + len])
    } else {
        None
    }
}

// SAFE: Checked arithmetic for offset calculation
fn safe_offset_access(arr: &[i32], base_index: usize, offset: isize) -> Option<i32> {
    let new_index = base_index.checked_add_signed(offset)?;
    arr.get(new_index).copied()
}

// SAFE: Using iterator instead of indexing
fn process_all(data: &[u8]) {
    for byte in data {
        println!("{}", byte);
    }
}

fn main() {
    let data = [1, 2, 3, 4, 5];

    // Safe access with Option handling
    if let Some(value) = read_safe(&data, 2) {
        println!("Read safely: {}", value);
    }

    // Safe slice creation
    if let Some(slice) = create_safe_slice(&data, 1, 3) {
        println!("Slice: {:?}", slice);
    }
}
