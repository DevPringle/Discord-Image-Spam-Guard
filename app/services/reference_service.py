from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from app.config import SETTINGS
from app.db import DB
from app.image_matching import ImageMatcher


class ReferenceImageService:
    @staticmethod
    def save_uploaded_file(file_storage: BinaryIO, filename: str) -> Path:
        safe_name = Path(filename).name
        target = SETTINGS.reference_image_dir / safe_name
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while target.exists():
            target = SETTINGS.reference_image_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        with open(target, "wb") as f:
            shutil.copyfileobj(file_storage, f)
        return target

    @staticmethod
    def register_file(path: Path, label: str, notes: str = "") -> int:
        computed = ImageMatcher.compute_from_path(path)
        return DB.add_reference_image(
            {
                "label": label,
                "notes": notes,
                "file_path": str(path),
                "sha256": computed.sha256,
                "phash": computed.phash,
                "dhash": computed.dhash,
                "whash": computed.whash,
                "width": computed.width,
                "height": computed.height,
                "active": True,
            }
        )

    @staticmethod
    def save_and_register(upload_stream: BinaryIO, filename: str, label: str, notes: str = "") -> int:
        saved = ReferenceImageService.save_uploaded_file(upload_stream, filename)
        try:
            return ReferenceImageService.register_file(saved, label, notes)
        except Exception:
            saved.unlink(missing_ok=True)
            raise
