// Negative case: safe type conversion
fn main() {
    let a: i32 = 1;
    let b: f32 = a as f32; // safe conversion
    println!("b: {}", b);
}
