"""Artifact annotation (Milestone 7).

Append-only, multi-annotator annotations with explicit provenance
(source_information / project_annotation / expert_annotation / ai_prediction) and review
state. Source metadata is never modified. See docs/ANNOTATION_GUIDE.md.

    python -m src.annotation validate      # N1-N13 over the whole store
    python -m src.annotation summary       # per-artifact status and disagreements
    python -m src.annotation quality       # technical quality vs archaeological usability
    streamlit run app/annotate.py          # the annotation interface
"""

from .model import blank_annotation, pixels_to_region, region_to_pixels
from .resolve import resolve_artifact
from .store import AnnotationRejected, AnnotationStore
from .validate import RULES, validate_annotation, validate_annotations

__all__ = ["RULES", "AnnotationRejected", "AnnotationStore", "blank_annotation",
           "pixels_to_region", "region_to_pixels", "resolve_artifact", "validate_annotation",
           "validate_annotations"]
