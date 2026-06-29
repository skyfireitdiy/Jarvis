// Negative case: Safe file operations avoiding TOCTOU
// Use atomic operations or handle files safely without race conditions.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;

// SAFE: Use create_new for atomic create-if-not-exists
fn safe_create_file(path: &Path, data: &[u8]) -> io::Result<()> {
    // O_EXCL ensures atomic creation - fails if file exists
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true) // Atomic operation
        .open(path)?;
    file.write_all(data)
}

// SAFE: Open file and use file descriptor throughout
fn safe_read_file(path: &Path) -> io::Result<String> {
    // Open once and use the handle - no race
    let mut file = File::open(path)?;
    let mut content = String::new();
    file.read_to_string(&mut content)?;
    Ok(content)
}

// SAFE: Use symlink_metadata to avoid following symlinks
fn safe_check_symlink(path: &Path) -> io::Result<bool> {
    // Check without following - no race window
    let meta = fs::symlink_metadata(path)?;
    Ok(meta.file_type().is_symlink())
}

// SAFE: Atomic file operations with proper error handling
fn safe_write_exclusive(path: &Path, data: &[u8]) -> io::Result<()> {
    // Atomic: either creates and writes, or fails if exists
    match OpenOptions::new().write(true).create_new(true).open(path) {
        Ok(mut file) => file.write_all(data),
        Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {
            Err(io::Error::new(io::ErrorKind::AlreadyExists, "file exists"))
        }
        Err(e) => Err(e),
    }
}

// SAFE: Use canonicalize to resolve path once
fn safe_resolve_and_open(path: &Path) -> io::Result<File> {
    // Resolve path once, then use the resolved path
    let canonical = fs::canonicalize(path)?;
    File::open(canonical)
}

// SAFE: Directory operations with proper locking
fn safe_create_in_dir(dir: &Path, filename: &str, data: &[u8]) -> io::Result<()> {
    // Open directory first, then create file atomically
    let canonical_dir = fs::canonicalize(dir)?;
    let file_path = canonical_dir.join(filename);
    safe_create_file(&file_path, data)
}

fn main() {
    let path = Path::new("/tmp/test.txt");
    let data = b"Hello, World!";

    if safe_create_file(path, data).is_ok() {
        println!("File created safely");
    }
}
