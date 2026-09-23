"""Training framework (Milestone 5).

Built so that authorised data can be dropped in later without redesign, and so that
nothing can be trained before then:

    python -m src.training train      # gate first; blocked today
    python -m src.training device     # CUDA / GPU report
    python -m src.training config     # resolved configuration

The only path from research records to a model is :func:`run.run_training`, which
calls the readiness gate before doing anything else.
"""

from .config import TrainingConfig, TrainingConfigError

__all__ = ["TrainingConfig", "TrainingConfigError"]
