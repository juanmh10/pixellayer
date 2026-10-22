use serde_json::{json, Value};
use std::fmt;

#[derive(Debug)]
pub struct AppError {
    pub code: &'static str,
    pub message: String,
    pub details: Option<Value>,
}

impl AppError {
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            details: None,
        }
    }
    pub fn invalid(message: impl Into<String>) -> Self {
        Self::new("INVALID_ARGUMENT", message)
    }
    pub fn json(&self) -> Value {
        let mut value = json!({"success": false, "error": self.code, "message": self.message});
        if let Some(details) = &self.details {
            value["details"] = details.clone();
        }
        value
    }
    pub fn with_details(mut self, details: Value) -> Self {
        self.details = Some(details);
        self
    }
}
impl fmt::Display for AppError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for AppError {}
impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self {
        let code = match e.kind() {
            std::io::ErrorKind::NotFound => "FILE_NOT_FOUND",
            std::io::ErrorKind::AlreadyExists => "OUTPUT_EXISTS",
            std::io::ErrorKind::PermissionDenied => "PERMISSION_DENIED",
            _ => "IO_ERROR",
        };
        Self::new(code, e.to_string())
    }
}
impl From<image::ImageError> for AppError {
    fn from(e: image::ImageError) -> Self {
        Self::new("PROCESSING_ERROR", e.to_string())
    }
}
impl From<ort::Error> for AppError {
    fn from(e: ort::Error) -> Self {
        Self::new("INFERENCE_ERROR", e.to_string())
    }
}
impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        Self::invalid(e.to_string())
    }
}
pub type Result<T> = std::result::Result<T, AppError>;
