import tempfile
from pathlib import Path
from typing import Tuple


EXT_MAP = {
    "typescript": "ts",
    "ts": "ts",
    "javascript": "js",
    "js": "js",
    "python": "py",
    "py": "py",
    "java": "java",
    "cpp": "cpp",
    "c++": "cpp",
    "c": "c",
}


def make_temp_project(language: str, code: str) -> Tuple[tempfile.TemporaryDirectory, Path]:
    """
    Creates a temporary folder with a single file inside:
      main.<ext>
    Returns (temp_dir_handle, folder_path).
    Keep the temp_dir_handle alive while using the folder.
    """
    temp_dir = tempfile.TemporaryDirectory()
    folder = Path(temp_dir.name)

    ext = EXT_MAP.get(language.lower().strip(), "txt")
    file_path = folder / f"main.{ext}"
    file_path.write_text(code, encoding="utf-8", errors="ignore")

    return temp_dir, folder
