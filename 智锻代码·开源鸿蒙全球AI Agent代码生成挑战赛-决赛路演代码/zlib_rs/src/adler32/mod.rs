//! Adler-32 checksum algorithm implementation
//!
//! This module provides Adler-32 checksum calculation and combination utilities.
//! Adler-32 is a checksum algorithm used in zlib for fast integrity checking.
//!
//! ## Submodules
//!
//! - [`combine`]: Functions for combining two Adler-32 checksums
//! - [`core`]: Core implementation details (crate-internal)

pub mod combine;
pub(crate) mod core;
