use crate::error::{AppError, Result};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
};

pub struct Workspace {
    root: PathBuf,
}

impl Workspace {
    pub fn native(path: &Path) -> String {
        let value = path.to_string_lossy();
        if let Some(unc) = value.strip_prefix(r"\\?\UNC\") {
            return format!(r"\\{unc}");
        }
        value.strip_prefix(r"\\?\").unwrap_or(&value).to_string()
    }
    pub fn client_path(raw: &str) -> PathBuf {
        // The Windows engine accepts the WSL representation of a mounted drive;
        // this translates syntax, never authorizes another directory.
        if cfg!(windows) && raw.starts_with("/mnt/") && raw.len() >= 6 {
            let bytes = raw.as_bytes();
            if bytes[5].is_ascii_alphabetic() && (raw.len() == 6 || bytes[6] == b'/') {
                return PathBuf::from(format!(
                    "{}:/{}",
                    (bytes[5] as char).to_ascii_uppercase(),
                    raw.get(7..).unwrap_or("")
                ));
            }
        }
        PathBuf::from(raw)
    }
    pub fn path_aliases(path: &Path) -> Vec<String> {
        let native = Self::native(path);
        let mut aliases = vec![native.clone()];
        let bytes = native.as_bytes();
        if cfg!(windows) && bytes.len() >= 3 && bytes[1] == b':' && bytes[0].is_ascii_alphabetic() {
            aliases.push(format!(
                "/mnt/{}/{}",
                (bytes[0] as char).to_ascii_lowercase(),
                native[3..].replace('\\', "/")
            ));
        }
        aliases
    }
    pub fn info(&self) -> Value {
        json!({"root": Self::native(&self.root), "path_aliases": Self::path_aliases(&self.root),
            "relative_paths_base": "workspace root, never agent CWD",
            "image_scope": "all image inputs and outputs must remain inside this root"})
    }
    pub fn matches(&self, raw: &str) -> bool {
        let path = Self::client_path(raw);
        path.is_absolute() && fs::canonicalize(path).is_ok_and(|p| p == self.root)
    }
    pub fn directory(&self, raw: &str) -> Result<PathBuf> {
        let path = Self::client_path(raw);
        if path
            .components()
            .any(|c| matches!(c, std::path::Component::ParentDir))
        {
            return Err(AppError::new(
                "SECURITY_ERROR",
                "Parent traversal is not allowed",
            ));
        }
        let resolved = self.resolve_new(&self.absolute(&path))?;
        if resolved.exists() && !resolved.is_dir() {
            return Err(AppError::invalid("Expected a directory"));
        }
        Ok(resolved)
    }
    pub fn new(path: &Path) -> Result<Self> {
        let root = fs::canonicalize(path)?;
        if !root.is_dir() {
            return Err(AppError::invalid("Workspace must be a directory"));
        }
        Ok(Self { root })
    }
    fn confine(&self, path: PathBuf) -> Result<PathBuf> {
        if !path.starts_with(&self.root) {
            return Err(AppError::new(
                "SECURITY_ERROR",
                "Path is outside the authorized workspace",
            ));
        }
        Ok(path)
    }
    fn absolute(&self, path: &Path) -> PathBuf {
        if path.is_absolute() {
            path.into()
        } else {
            self.root.join(path)
        }
    }
    pub fn input(&self, path: &str) -> Result<PathBuf> {
        let p = self.confine(fs::canonicalize(self.absolute(&Self::client_path(path)))?)?;
        if !p.is_file() {
            return Err(AppError::invalid("Input must be a regular file"));
        }
        Ok(p)
    }
    fn resolve_new(&self, path: &Path) -> Result<PathBuf> {
        if path.exists() {
            return self.confine(fs::canonicalize(path)?);
        }
        // Resolve existing ancestors before creating directories. Reject traversal components.
        let name = path
            .file_name()
            .ok_or_else(|| AppError::invalid("Invalid output path"))?;
        if name == "." || name == ".." {
            return Err(AppError::invalid("Invalid output path"));
        }
        let parent = path
            .parent()
            .ok_or_else(|| AppError::invalid("Invalid output parent"))?;
        let resolved = self.resolve_new(parent)?.join(name);
        self.confine(resolved)
    }
    pub fn output(
        &self,
        input: &Path,
        explicit: Option<&str>,
        suffix: &str,
        ext: &str,
        auto_rename: bool,
    ) -> Result<PathBuf> {
        if let Some(raw) = explicit {
            let client_path = Self::client_path(raw);
            if client_path
                .components()
                .any(|c| matches!(c, std::path::Component::ParentDir))
            {
                return Err(AppError::new(
                    "SECURITY_ERROR",
                    "Parent traversal is not allowed in output paths",
                ));
            }
            let p = self.resolve_new(&self.absolute(&client_path))?;
            let actual_ext = p
                .extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_ascii_lowercase();
            if actual_ext != ext && !(ext == "jpeg" && actual_ext == "jpg") {
                return Err(AppError::invalid(format!(
                    "Output extension must match {ext}"
                )));
            }
            if p.exists() || p.symlink_metadata().is_ok() {
                if !auto_rename || p == input || !p.is_file() {
                    return Err(AppError::new("OUTPUT_EXISTS", "Existing files are preserved; choose a new output path. Never delete or rename existing outputs to retry."));
                }
                let stem = p.file_stem().unwrap().to_string_lossy();
                for index in 1..10000 {
                    let candidate = p.with_file_name(format!("{stem}_{index}.{actual_ext}"));
                    if !candidate.exists() && candidate.symlink_metadata().is_err() {
                        return self.confine(candidate);
                    }
                }
                return Err(AppError::new(
                    "OUTPUT_EXISTS",
                    "No unused output filename is available",
                ));
            }
            return Ok(p);
        }
        let stem = input.file_stem().unwrap().to_string_lossy();
        for index in 0..10000 {
            let extra = if index == 0 {
                String::new()
            } else {
                format!("_{index}")
            };
            let p = input.with_file_name(format!("{stem}{suffix}{extra}.{ext}"));
            if !p.exists() && p.symlink_metadata().is_err() {
                return self.confine(p);
            }
        }
        Err(AppError::new(
            "OUTPUT_EXISTS",
            "Too many output filename collisions",
        ))
    }
    pub fn relative(&self, path: &Path) -> String {
        path.strip_prefix(&self.root)
            .unwrap_or(path)
            .to_string_lossy()
            .replace('\\', "/")
    }
    pub fn write(&self, path: &Path, bytes: &[u8]) -> Result<()> {
        use std::io::Write;
        let parent = path
            .parent()
            .ok_or_else(|| AppError::invalid("Invalid output parent"))?;
        self.resolve_new(parent)?;
        fs::create_dir_all(parent)?;
        self.confine(fs::canonicalize(parent)?)?;
        let mut tmp = tempfile::NamedTempFile::new_in(parent)?;
        tmp.write_all(bytes)?;
        tmp.as_file().sync_all()?;
        tmp.persist_noclobber(path)
            .map_err(|e| AppError::from(e.error))?;
        Ok(())
    }
}
