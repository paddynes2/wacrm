"""Make the extracted core importable in a clean checkout test invocation."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
