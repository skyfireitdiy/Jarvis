// Positive case: static mut global mutable state
// static mut is inherently unsafe for concurrent access.
// Even with unsafe blocks, data races can occur if multiple threads
// access the same static mut without synchronization.
// The checker should specifically flag static mut as a data race risk,
// not just the unsafe block around it.

static mut COUNTER: u64 = 0;
static mut GLOBAL_BUFFER: [u8; 256] = [0; 256];

fn increment() {
    unsafe {
        COUNTER += 1;
    }
}

fn write_buffer(index: usize, value: u8) {
    unsafe {
        GLOBAL_BUFFER[index] = value;
    }
}

fn main() {
    increment();
    write_buffer(0, 42);
}
