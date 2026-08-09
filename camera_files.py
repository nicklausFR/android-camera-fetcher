from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from adb_client import MediaStoreFile

PHONE_ROOT = "/sdcard/DCIM/Camera"


@dataclass(frozen=True)
class CameraFile:
    remote_path: str
    media_date: date
    mime_type: str
    size: int

    @property
    def filename(self) -> str:
        return Path(self.remote_path).name


def build_camera_files(source_files: list[MediaStoreFile]) -> list[CameraFile]:
    return [
        CameraFile(
            remote_path=item.remote_path,
            media_date=item.modified_date,
            mime_type=item.mime_type,
            size=item.size,
        )
        for item in source_files
    ]


def build_local_path(output_directory: Path, camera_file: CameraFile) -> Path:
    return (
        output_directory
        / camera_file.media_date.isoformat()
        / camera_file.filename
    )


def total_size(files: list[CameraFile]) -> int:
    return sum(item.size for item in files)
