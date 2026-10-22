use rmcp::schemars::{self, JsonSchema};
use serde::{Deserialize, Serialize};

fn quality() -> u8 {
    90
}
fn model() -> String {
    "birefnet-general".into()
}

#[derive(Debug, Default, Clone, Copy, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum Format {
    #[default]
    Png,
    Webp,
    #[serde(alias = "jpg")]
    Jpeg,
}
impl Format {
    pub fn extension(self) -> &'static str {
        match self {
            Self::Png => "png",
            Self::Webp => "webp",
            Self::Jpeg => "jpeg",
        }
    }
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RemoveArgs {
    pub image_path: String,
    #[serde(default = "model")]
    pub model: String,
    pub output_path: Option<String>,
    #[serde(default)]
    pub output_format: Format,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ConvertArgs {
    pub image_path: String,
    pub target_format: Format,
    #[serde(default = "quality")]
    pub quality: u8,
    #[serde(default)]
    pub lossless: bool,
    pub output_path: Option<String>,
}

#[derive(Debug, Default, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum ResizeMode {
    #[default]
    Fit,
    Fill,
    Exact,
    Percentage,
}
#[derive(Debug, Default, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum Resample {
    #[default]
    Lanczos,
    Bicubic,
    Bilinear,
    Nearest,
}
#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ResizeArgs {
    pub image_path: String,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub scale_percent: Option<f64>,
    #[serde(default)]
    pub mode: ResizeMode,
    #[serde(default)]
    pub resample: Resample,
    pub output_path: Option<String>,
}

#[derive(Debug, Default, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum Detail {
    #[default]
    Logo,
    Low,
    Medium,
    High,
}
#[derive(Debug, Default, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum ColorMode {
    #[default]
    Color,
    Binary,
}
#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct VectorArgs {
    pub image_path: String,
    /// Remove background to a retained PNG, then trace that exact PNG in one call.
    #[serde(default)]
    pub remove_background: bool,
    #[serde(default)]
    pub detail_level: Detail,
    #[serde(default)]
    pub color_mode: ColorMode,
    pub output_path: Option<String>,
}
#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelArgs {
    pub model_id: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct EmptyArgs {}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ResultInfoArgs {
    /// Existing output inside the prepared output folder; omit to list that folder (100 files, no recursion).
    pub output_path: Option<String>,
}

fn input_directory() -> String {
    "input".into()
}
fn output_directory() -> String {
    "output".into()
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PrepareArgs {
    /// Actual absolute project/task directory of the calling agent, NOT a guessed server path.
    pub expected_workspace: String,
    /// Folder inside the workspace, default "input"; "." selects the workspace root.
    #[serde(default = "input_directory")]
    pub input_directory: String,
    /// Workspace-relative output folder requested by the user, e.g. output/2.
    #[serde(default = "output_directory")]
    pub output_directory: String,
}
