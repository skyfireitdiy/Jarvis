// Negative case: safe bounds-checked slice access
// Using regular indexing which panics on out-of-bounds instead of UB.

fn access_slice(data: &[u8], index: usize) -> u8 {
    // SAFE: regular indexing with bounds check
    data[index]
}

fn access_checked(data: &[u8], index: usize) -> Option<&u8> {
    // SAFE: get() returns None on out-of-bounds
    data.get(index)
}

fn main() {
    let data = [1u8, 2, 3, 4, 5];
    let val = access_slice(&data, 2);
    println!("val: {}", val);
}
