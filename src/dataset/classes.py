"""The classification label set, and which records may take part in training.

The class list is a **project methodology decision** recorded in
``configs/project.yaml`` (``classification``). It is not derived from data, and code
never collapses one label into another:

* trainable classes (today ``tamil_brahmi``, ``graffiti``, ``none``, ``uncertain``) get a
  class index;
* held-out labels (``other_script``, ``tamil_brahmi_and_graffiti``) are kept in the
  dataset, counted in every report, and excluded from the initial model with an
  explicit reason. They are never relabelled as a trainable class.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .schema import enum_values, load_config


class ClassSpecError(ValueError):
    """The configured class list is inconsistent with the schema."""


@dataclass(frozen=True)
class ClassSpec:
    trainable: tuple[str, ...]
    held_out: tuple[str, ...]
    schema_labels: tuple[str, ...]

    @classmethod
    def from_config(cls, config: dict[str, Any] | None = None) -> ClassSpec:
        config = config or load_config()
        section = config.get("classification", {})
        trainable = tuple(section.get("classes", []))
        held_out = tuple(section.get("held_out_labels", []))
        schema_labels = tuple(enum_values("script_type") or ())
        spec = cls(trainable, held_out, schema_labels)
        spec.check()
        return spec

    def check(self) -> None:
        if not self.trainable:
            raise ClassSpecError("classification.classes is empty")
        if len(set(self.trainable)) != len(self.trainable):
            raise ClassSpecError(f"duplicate trainable classes: {self.trainable}")
        overlap = set(self.trainable) & set(self.held_out)
        if overlap:
            raise ClassSpecError(f"labels both trainable and held out: {sorted(overlap)}")
        unknown = (set(self.trainable) | set(self.held_out)) - set(self.schema_labels)
        if unknown:
            raise ClassSpecError(f"labels not in the schema's script_type enum: {sorted(unknown)}")
        unassigned = set(self.schema_labels) - set(self.trainable) - set(self.held_out)
        if unassigned:
            raise ClassSpecError(
                f"schema labels neither trainable nor held out: {sorted(unassigned)}. "
                "Every label must be placed explicitly; none is dropped silently."
            )

    @property
    def num_classes(self) -> int:
        return len(self.trainable)

    def index_of(self, label: str) -> int | None:
        """Class index for a trainable label, ``None`` for a held-out one."""
        try:
            return self.trainable.index(label)
        except ValueError:
            if label in self.held_out:
                return None
            raise ClassSpecError(f"label {label!r} is not in the class specification") from None

    def status(self, label: str) -> str:
        if label in self.trainable:
            return "trainable"
        if label in self.held_out:
            return "held_out"
        return "not_in_schema"


def eligibility(record: Any, spec: ClassSpec) -> tuple[bool, str]:
    """Whether a record may be used for training/evaluation, and why not if not.

    Accepts a raw record dict or a :class:`~src.dataset.loader.DatasetRecord`.
    """
    get = record.get if hasattr(record, "get") else (lambda k, d=None: d)
    if get("split", "unassigned") == "excluded":
        return False, f"split=excluded ({get('split_exclusion_reason', 'no reason')})"
    label = get("script_type", None)
    if label in spec.held_out:
        return False, f"held_out_label:{label}"
    if label not in spec.trainable:
        return False, f"label {label!r} not in class specification"
    return True, "eligible"


@dataclass(frozen=True)
class ClassAvailability:
    label: str
    status: str          # trainable | held_out
    artifacts: int
    images: int

    @property
    def available(self) -> bool:
        return self.artifacts > 0


def class_availability(records: Iterable[Any], spec: ClassSpec) -> list[ClassAvailability]:
    """Artifact and image counts for every schema label, in a fixed order.

    Records excluded via ``split=excluded`` are not counted; held-out labels are counted
    and reported as such, so their absence from training is visible rather than silent.
    """
    artifacts: dict[str, set[str]] = {lbl: set() for lbl in spec.schema_labels}
    images: dict[str, int] = dict.fromkeys(spec.schema_labels, 0)
    for rec in records:
        get = rec.get
        if get("split", "unassigned") == "excluded":
            continue
        label = get("script_type", None)
        if label not in artifacts:
            continue
        artifacts[label].add(str(get("artifact_id", "")))
        images[label] += 1
    order = list(spec.trainable) + list(spec.held_out)
    return [
        ClassAvailability(lbl, spec.status(lbl), len(artifacts[lbl]), images[lbl])
        for lbl in order
    ]


__all__ = [
    "ClassAvailability",
    "ClassSpec",
    "ClassSpecError",
    "class_availability",
    "eligibility",
]
