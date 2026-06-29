// Negative case: pure Rust code
fn allocate(size: usize) -> Vec<u8> {
    vec![0; size]
}

fn main() {
    let data = allocate(100);
    println!("allocated {} bytes", data.len());
}
