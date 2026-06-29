// Negative case: safe reference usage
fn main() {
    let mut num = 5;
    let ref_num = &mut num;
    *ref_num = 10;
}
