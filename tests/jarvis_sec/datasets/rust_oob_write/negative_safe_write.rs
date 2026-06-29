// Negative case: Safe buffer writing patterns
// Use bounds checking, safe APIs, and proper validation.

use std::os::raw::c_char;
use std::ptr;

extern "C" {
    fn c_get_buffer() -> *mut u8;
    fn c_get_buffer_size() -> usize;
}

// SAFE: Bounds-checked write
fn safe_write(buffer: &mut [u8], offset: usize, data: u8) -> Result<(), &'static str> {
    buffer
        .get_mut(offset)
        .map(|slot| *slot = data)
        .ok_or("index out of bounds")
}

// SAFE: Copy with size validation
fn safe_copy_to_buffer(dest: &mut [u8], src: &[u8]) -> Result<(), &'static str> {
    if src.len() > dest.len() {
        return Err("source too large for destination");
    }
    dest[..src.len()].copy_from_slice(src);
    Ok(())
}

// SAFE: FFI write with bounds check
unsafe fn safe_ffi_write(data: &[u8]) -> Result<(), &'static str> {
    let buf = c_get_buffer();
    let size = c_get_buffer_size();

    if data.len() > size {
        return Err("data exceeds buffer size");
    }

    for i in 0..data.len() {
        *buf.add(i) = data[i];
    }
    Ok(())
}

// SAFE: String copy with length limit
fn safe_str_copy(buffer: &mut [u8], input: &str) -> Result<(), &'static str> {
    let bytes = input.as_bytes();
    if bytes.len() >= buffer.len() {
        return Err("input too long");
    }
    buffer[..bytes.len()].copy_from_slice(bytes);
    buffer[bytes.len()] = 0; // Null terminator
    Ok(())
}

// SAFE: Write with correct slice length
unsafe fn safe_write_with_length(
    buffer: *mut u8,
    size: usize,
    data: &[u8],
) -> Result<(), &'static str> {
    if data.len() > size {
        return Err("data too large");
    }
    let slice = std::slice::from_raw_parts_mut(buffer, size);
    slice[..data.len()].copy_from_slice(data);
    Ok(())
}

// SAFE: Checked array access
fn safe_index(arr: &[u8], idx: usize) -> Option<u8> {
    arr.get(idx).copied() // Returns None if out of bounds
}

// SAFE: Write with destination size check
unsafe fn safe_ffi_memcpy(dest: *mut u8, dest_size: usize, src: &[u8]) -> Result<(), &'static str> {
    if src.len() > dest_size {
        return Err("source exceeds destination size");
    }
    ptr::copy_nonoverlapping(src.as_ptr(), dest, src.len());
    Ok(())
}

// SAFE: Format with bounds check
fn safe_format(buffer: &mut [u8], user_input: &str) -> Result<usize, &'static str> {
    let msg = format!("User: {}", user_input);
    let bytes = msg.as_bytes();

    if bytes.len() >= buffer.len() {
        return Err("formatted message too long");
    }

    buffer[..bytes.len()].copy_from_slice(bytes);
    Ok(bytes.len())
}

fn main() {
    let mut buf = [0u8; 10];
    match safe_write(&mut buf, 5, 0xFF) {
        Ok(()) => println!("Write successful"),
        Err(e) => eprintln!("Error: {}", e),
    }
}
