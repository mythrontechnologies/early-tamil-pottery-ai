"""Image preprocessing for Early Tamil Pottery AI (Milestone 3).

Turns a source photograph into a deterministic, model-ready image without ever
modifying the original. Quality metrics describe the photograph only; they are never
archaeological judgements.

    from src.preprocessing import PreprocessConfig, preprocess_image

    cfg = PreprocessConfig.from_config()
    result = preprocess_image("some/sherd.jpg", config=cfg)
    if result.ok:
        array = result.to_array()      # normalised CHW float32
"""

from .loader import Issue, LoadedImage, load_image, sha256_file
from .pipeline import (
    DEFAULT_OUTPUT_ROOT,
    PreprocessConfig,
    PreprocessResult,
    RawImmutabilityError,
    preprocess_image,
    preprocess_to_disk,
    save_result,
)
from .quality import DISCLAIMER, QualityMetrics, assess
from .transforms import (
    TransformLog,
    apply_exif_orientation,
    map_box_to_original,
    resize_preserving_aspect,
    to_model_array,
    to_rgb,
)

__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "DISCLAIMER",
    "Issue",
    "LoadedImage",
    "PreprocessConfig",
    "PreprocessResult",
    "QualityMetrics",
    "RawImmutabilityError",
    "TransformLog",
    "apply_exif_orientation",
    "assess",
    "load_image",
    "map_box_to_original",
    "preprocess_image",
    "preprocess_to_disk",
    "resize_preserving_aspect",
    "save_result",
    "sha256_file",
    "to_model_array",
    "to_rgb",
]
