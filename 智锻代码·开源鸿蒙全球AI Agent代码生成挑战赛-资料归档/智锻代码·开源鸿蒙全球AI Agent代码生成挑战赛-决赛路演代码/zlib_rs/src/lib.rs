//! zlib-rs: A Rust implementation of zlib compression library
//!
//! This crate provides Rust implementations of zlib compression algorithms
//! and data structures, with FFI bindings for C interoperability.
//!
//! ## Modules
//!
//! - [`adler32`]: Adler-32 checksum algorithm implementation
//! - [`ffi`]: Foreign Function Interface for C compatibility

pub mod adler32;
pub mod ffi;
