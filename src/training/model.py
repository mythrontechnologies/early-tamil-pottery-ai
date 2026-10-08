"""Model construction: small pretrained torchvision backbones with a new head.

Default ``resnet18``: 11.7 M parameters, about 45 MB of fp32 weights. At 224 px with
batch 16 and fp16 autocast it trains well inside a 6 GB RTX 4050. The other supported
backbones are of similar or smaller cost.

``pretrained=True`` downloads ImageNet weights from torchvision on first use. That is a
general-purpose image model, not archaeological data. Tests always use
``pretrained=False`` and never touch the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from torch import nn
from torchvision import models

from .config import SUPPORTED_MODELS, ModelConfig


class ModelError(ValueError):
    """The requested model cannot be built."""


@dataclass(frozen=True)
class _Arch:
    builder: str
    weights: str
    head_path: tuple[str, ...]     # attribute path to the final Linear layer


_ARCHS: dict[str, _Arch] = {
    "resnet18": _Arch("resnet18", "ResNet18_Weights", ("fc",)),
    "resnet34": _Arch("resnet34", "ResNet34_Weights", ("fc",)),
    "efficientnet_b0": _Arch("efficientnet_b0", "EfficientNet_B0_Weights", ("classifier", "1")),
    "mobilenet_v3_large": _Arch("mobilenet_v3_large", "MobileNet_V3_Large_Weights",
                                ("classifier", "3")),
}
assert set(_ARCHS) == set(SUPPORTED_MODELS)


def _get(module: nn.Module, path: tuple[str, ...]) -> nn.Module:
    for part in path:
        module = cast(nn.Sequential, module)[int(part)] if part.isdigit() else getattr(module, part)
    return module


def _head_path(model: nn.Module) -> tuple[str, ...]:
    """The head path build_model stored on the model (nn.Module types attributes as Tensor | Module)."""
    return tuple(model.__dict__["head_path"])


def _set(module: nn.Module, path: tuple[str, ...], value: nn.Module) -> None:
    parent = _get(module, path[:-1]) if len(path) > 1 else module
    last = path[-1]
    if last.isdigit():
        cast(nn.Sequential, parent)[int(last)] = value
    else:
        setattr(parent, last, value)


def build_model(cfg: ModelConfig) -> nn.Module:
    """Build a backbone with a fresh ``num_classes`` head (dropout -> linear)."""
    if cfg.name not in _ARCHS:
        raise ModelError(f"unsupported model {cfg.name!r}; choose from {sorted(_ARCHS)}")
    if cfg.num_classes < 2:
        raise ModelError("num_classes must be >= 2")
    arch = _ARCHS[cfg.name]
    weights = getattr(models, arch.weights).DEFAULT if cfg.pretrained else None
    model: nn.Module = getattr(models, arch.builder)(weights=weights)
    old = _get(model, arch.head_path)
    if not isinstance(old, nn.Linear):  # pragma: no cover - guards a torchvision change
        raise ModelError(f"{cfg.name}: expected a Linear head at {'.'.join(arch.head_path)}")
    head = nn.Sequential(nn.Dropout(p=cfg.dropout), nn.Linear(old.in_features, cfg.num_classes))
    _set(model, arch.head_path, head)
    model.__dict__["head_path"] = arch.head_path      # a plain attribute, not a parameter or submodule
    set_backbone_trainable(model, not cfg.freeze_backbone)
    return model


def head_parameters(model: nn.Module) -> list[nn.Parameter]:
    return list(_get(model, _head_path(model)).parameters())


def backbone_parameters(model: nn.Module) -> list[nn.Parameter]:
    head_ids = {id(p) for p in head_parameters(model)}
    return [p for p in model.parameters() if id(p) not in head_ids]


def set_backbone_trainable(model: nn.Module, trainable: bool) -> None:
    """Freeze or unfreeze everything except the classification head."""
    for p in backbone_parameters(model):
        p.requires_grad = trainable
    for p in head_parameters(model):
        p.requires_grad = True


def count_parameters(model: nn.Module) -> dict[str, int]:
    return {
        "total": sum(p.numel() for p in model.parameters()),
        "trainable": sum(p.numel() for p in model.parameters() if p.requires_grad),
    }


def num_outputs(model: nn.Module) -> int:
    head = cast(nn.Sequential, _get(model, _head_path(model)))
    return int(cast(nn.Linear, head[-1]).out_features)


__all__ = [
    "ModelError",
    "backbone_parameters",
    "build_model",
    "count_parameters",
    "head_parameters",
    "num_outputs",
    "set_backbone_trainable",
]
