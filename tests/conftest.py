"""Point all app data at a throwaway folder BEFORE any studio module is imported."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["BRAND_STUDIO_DATA"] = tempfile.mkdtemp(prefix="brand_studio_test_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
