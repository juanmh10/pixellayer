# Library-only VTracer 0.6.5 packaging

Upstream: https://crates.io/crates/vtracer/0.6.5
Crate SHA-256: c2307187c5c99e7387f3158a29b0be541b99b06c5c492598b77644bf5603bd0c

Source files and MIT/Apache license notices are preserved byte for byte. The
manifest disables automatic binaries and removes clap 2, which src/main.rs uses
but the in-memory library does not. PixelLayer uses its own CLI and image loading.
The tracing algorithm and visioncortex dependency are unchanged. Image 0.23
format decoders are disabled: PixelLayer decodes PNG/WebP/JPEG with its own
current image dependency and calls convert(ColorImage, config). The unused
upstream disk-loading helper therefore has no enabled codecs in this build. UPSTREAM.toml records the original manifest. Do not build this crate's
old standalone CLI from this library-only package. This local packaging patch
removes atty without switching the approved SVG algorithm to an alpha release.
