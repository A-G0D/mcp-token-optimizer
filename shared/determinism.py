"""Seed the RNGs we might be using so runs reproduce. numpy/torch are seeded
only if they happen to be installed."""
from __future__ import annotations

import os
import random
from typing import Optional


def set_seed(seed: int = 1337, *, deterministic_torch: bool = True) -> int:
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)

    try:
        import numpy as np  # type: ignore

        np.random.seed(seed)
    except Exception:
        pass

    try:
        import torch  # type: ignore

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        if deterministic_torch:
            torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass

    return seed


def seeded_rng(seed: Optional[int] = None) -> random.Random:
    return random.Random(seed if seed is not None else 1337)
