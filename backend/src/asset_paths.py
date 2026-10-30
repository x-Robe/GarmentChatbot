"""Repository layout only: the existing catalog stays in root data/images."""
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
IMAGE_ROOT = (REPOSITORY_ROOT / "data" / "images").resolve()


def resolve_catalog_path(value: str | Path) -> Path:
    """Resolve unchanged Qdrant data/images/... paths without copying assets.

    Other relative inputs keep the existing backend-relative interpretation.
    Callers such as the API enforce their existing allowed-root/traversal checks.
    """
    path = Path(value)
    if path.is_absolute():
        return path
    root = REPOSITORY_ROOT if path.parts[:2] == ("data", "images") else BACKEND_ROOT
    return root / path
