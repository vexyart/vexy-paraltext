# this_file: tests/test_portable_config.py
"""Default model locations must work outside the maintainer workstation."""
from pathlib import Path

from vexy_paraltext.config import EmbedConfig


def test_default_gguf_paths_use_the_current_home():
    for model in EmbedConfig().models.values():
        if model.path:
            assert str(Path.home() / ".lmstudio" / "models") in model.path
