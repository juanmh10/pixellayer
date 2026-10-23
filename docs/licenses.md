# Licenses and model provenance

## PixelLayer and the skill

PixelLayer's own published source and skill are MIT licensed under the repository
[LICENSE](../LICENSE), copyright 2026 Juan Henrique. Preserve that notice and its
permission text when redistributing applicable portions. Third-party components
retain their own licenses; the root license does not relicense them.

A marketplace listing or its commercial conditions is separate from the project
license. This repository does not claim that marketplace onboarding, payments or
submission approval has been completed.

## Standard background-removal model

| Field | Value |
| --- | --- |
| Model | BiRefNet General, ONNX FP32 |
| Declared license | MIT; [notice](../licenses/BiRefNet-MIT.txt) |
| Upstream artifact | [onnx-community/BiRefNet-ONNX](https://huggingface.co/onnx-community/BiRefNet-ONNX/tree/534d3c82d3bb8b2f0867db6dfbc3a525b8e42f67) |
| Revision | `534d3c82d3bb8b2f0867db6dfbc3a525b8e42f67` |
| Size | `972666916` bytes, about 928 MiB |
| SHA-256 | `58f621f00f5d756097615970a88a791584600dcf7c45b18a0a6267535a1ebd3c` |
| Cache filename | `birefnet-general-fp32-534d3c82.onnx` |

The engine verifies pinned bytes and uses CPU FP32. Weights are outside Git and the
native/skill ZIPs. Image processing does not upload images to the model host.
Experimental INT8 is not part of the standard public setup or download contract.

## Runtime and dependencies

ONNX Runtime CPU 1.22.0 is bundled with the native engine, with its MIT license and
third-party notices. The source tree contains the [MIT notice](../licenses/ONNX-Runtime-MIT.txt)
and pinned native archive hashes in [packaging/onnxruntime.tsv](../packaging/onnxruntime.tsv).

The vendored VTracer library retains its [MIT](../vendor/vtracer/LICENSE-MIT) and
[Apache-2.0](../vendor/vtracer/LICENSE-APACHE) notices. Its packaging modification
and original manifest are recorded alongside the source. Native archives also
include Rust dependency notices collected during packaging.

Windows archives contain unmodified Microsoft Visual C++ runtime components,
subject to their applicable Microsoft terms. Those terms and redistribution
references accompany the package; they are not replaced by PixelLayer's MIT
license. Consult the notices inside the specific downloaded archive for its
complete bundled-component inventory.
