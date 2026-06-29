// Negative case: explicit drop
fn main() {
    let data = Box::new(42);
    drop(data); // proper cleanup
}
