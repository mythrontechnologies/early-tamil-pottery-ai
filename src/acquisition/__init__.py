"""Public-data acquisition (Milestone 6).

Turns a curated plan of candidate files into acquired, licence-checked, provenance-
recorded data, through the project's existing validation and ingestion:

    python -m src.acquisition plan configs/acquisition/milestone6_wikimedia_commons.yaml
    python -m src.acquisition plan configs/acquisition/milestone6_wikimedia_commons.yaml --commit

See docs/DATA_ACQUISITION.md.
"""

from .licenses import ALLOWED, evaluate_license, normalise
from .policy import Candidate, evaluate

__all__ = ["ALLOWED", "Candidate", "evaluate", "evaluate_license", "normalise"]
