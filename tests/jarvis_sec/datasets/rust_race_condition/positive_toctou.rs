// Positive case: CWE-362 Race Condition (TOCTOU)
// Time-of-Check to Time-of-Use vulnerabilities.
// Check and use operations are not atomic, creating a race window.

use std::fs;
use std::io::{self, Write};
use std::path::Path;

// VULNERABLE: TOCTOU between exists() and read()
fn read_file_if_exists(path: &Path) -> io::Result<String> {
    if path.exists() {
        // Time of Check
        // Race window: attacker can replace file with symlink
        let content = fs::read_to_string(path)?; // Time of Use
        Ok(content)
    } else {
        Err(io::Error::new(io::ErrorKind::NotFound, "file not found"))
    }
}

// VULNERABLE: TOCTOU between exists() and write()
fn write_if_not_exists(path: &Path, data: &[u8]) -> io::Result<()> {
    if !path.exists() {
        // Time of Check
        // Race window: attacker can create file
        fs::write(path, data)?; // Time of Use - may overwrite attacker's file
    }
    Ok(())
}

// VULNERABLE: TOCTOU between metadata() and open()
fn open_if_regular_file(path: &Path) -> io::Result<fs::File> {
    let meta = path.metadata()?; // Time of Check
    if meta.is_file() {
        // Race window: file could be replaced with symlink or device
        fs::File::open(path) // Time of Use
    } else {
        Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "not a regular file",
        ))
    }
}

// VULNERABLE: TOCTOU between is_dir() and create_file()
fn create_file_in_dir(dir: &Path, filename: &str) -> io::Result<fs::File> {
    if dir.is_dir() {
        // Time of Check
        let file_path = dir.join(filename);
        // Race window: dir could be replaced with symlink
        fs::File::create(&file_path) // Time of Use
    } else {
        Err(io::Error::new(
            io::ErrorKind::NotADirectory,
            "not a directory",
        ))
    }
}

// VULNERABLE: TOCTOU in symlink handling
fn follow_symlink_once(path: &Path) -> io::Result<PathBuf> {
    let meta = fs::symlink_metadata(path)?; // Time of Check
    if meta.file_type().is_symlink() {
        // Race window: symlink target could change
        fs::read_link(path) // Time of Use
    } else {
        Ok(path.to_path_buf())
    }
}

use std::path::PathBuf;

fn main() {
    let path = Path::new("/tmp/test.txt");
    if let Ok(content) = read_file_if_exists(path) {
        println!("Content: {}", content);
    }
}
