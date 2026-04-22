from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import imagehash
from PIL import Image, ImageOps


@dataclass
class ComputedImage:
    sha256: str
    phash: str
    dhash: str
    whash: str
    width: int
    height: int


@dataclass
class MatchResult:
    matched: bool
    method: str
    score: int
    reference: dict[str, Any] | None


class ImageMatcher:
    @staticmethod
    def normalize_image(image: Image.Image) -> Image.Image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        return normalized

    @staticmethod
    def compute_from_bytes(data: bytes) -> ComputedImage:
        image = Image.open(io.BytesIO(data))
        normalized = ImageMatcher.normalize_image(image)
        return ComputedImage(
            sha256=hashlib.sha256(data).hexdigest(),
            phash=str(imagehash.phash(normalized)),
            dhash=str(imagehash.dhash(normalized)),
            whash=str(imagehash.whash(normalized)),
            width=normalized.width,
            height=normalized.height,
        )

    @staticmethod
    def compute_from_path(path: Path) -> ComputedImage:
        return ImageMatcher.compute_from_bytes(path.read_bytes())

    @staticmethod
    def compare(computed: ComputedImage, references: list[dict[str, Any]], threshold: int, exact_sha_enabled: bool) -> MatchResult:
        if exact_sha_enabled:
            for ref in references:
                if computed.sha256 == ref["sha256"]:
                    return MatchResult(True, "sha256", 0, ref)

        best_score: int | None = None
        best_method = ""
        best_ref: dict[str, Any] | None = None

        for ref in references:
            phash_distance = imagehash.hex_to_hash(computed.phash) - imagehash.hex_to_hash(ref["phash"])
            dhash_distance = imagehash.hex_to_hash(computed.dhash) - imagehash.hex_to_hash(ref["dhash"])
            whash_distance = imagehash.hex_to_hash(computed.whash) - imagehash.hex_to_hash(ref["whash"])

            candidate_method, candidate_score = min(
                [("phash", phash_distance), ("dhash", dhash_distance), ("whash", whash_distance)],
                key=lambda item: item[1],
            )

            if best_score is None or candidate_score < best_score:
                best_score = candidate_score
                best_method = candidate_method
                best_ref = ref

        if best_score is not None and best_score <= threshold:
            return MatchResult(True, best_method, best_score, best_ref)

        return MatchResult(False, best_method or "none", best_score if best_score is not None else 999, best_ref)
