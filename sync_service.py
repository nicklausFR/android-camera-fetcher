from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Signal

import adb_client
import camera_files


DESTINATION = Path(r"D:\Pictures\Photos\Smartphone")


@dataclass(frozen=True)
class SyncResult:
    device: adb_client.AndroidDevice
    copied: int
    skipped: int
    errors: int


class SyncService(QObject):
    started = Signal(str)
    progress = Signal(int, int, str, bool)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, destination: Path = DESTINATION) -> None:
        super().__init__()
        self.destination = destination
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sync")
        self._running = False
        self._cancel = threading.Event()

    def start(self, connection_mode: str = "auto", start_date: date | None = None, end_date: date | None = None, media_mode: str = "all", preferred_serial: str = "") -> None:
        if self._running:
            return
        self._running = True
        self._cancel.clear()
        future = self._executor.submit(self._sync, connection_mode, start_date, end_date, media_mode, preferred_serial)
        future.add_done_callback(self._completed)

    def cancel(self) -> None:
        self._cancel.set()

    def _sync(self, connection_mode: str, start_date: date | None, end_date: date | None, media_mode: str, preferred_serial: str) -> SyncResult:
        device = adb_client.select_device(connection_mode, preferred_serial)
        self.started.emit(f"{device.model} via {device.connection_type}")
        media = adb_client.query_camera_files(
            device.serial,
            camera_files.PHONE_ROOT,
            # Windows cannot convert pre-1980 local timestamps on every setup.
            # This remains well before modern Android camera media.
            start_date or date(2000, 1, 1),
            end_date or date.today(),
            media_mode=media_mode,
            newest_first=False,
        )
        files = camera_files.build_camera_files(media)
        self.destination.mkdir(parents=True, exist_ok=True)
        copied = skipped = errors = 0

        for index, item in enumerate(files, start=1):
            if self._cancel.is_set():
                raise InterruptedError("Synchronisation annulée.")
            target = self._target_path(item)
            copied_this_file = False
            if target.exists() and target.stat().st_size == item.size:
                skipped += 1
            else:
                temporary = target.with_suffix(target.suffix + ".part")
                try:
                    if temporary.exists():
                        temporary.unlink()
                    adb_client.pull_file(device.serial, item.remote_path, temporary, self._cancel)
                    temporary.replace(target)
                    copied += 1
                    copied_this_file = True
                except InterruptedError:
                    raise
                except Exception:
                    errors += 1
                    if temporary.exists():
                        temporary.unlink()
            self.progress.emit(index, len(files), item.filename, copied_this_file)

        return SyncResult(device, copied, skipped, errors)

    def _target_path(self, item: camera_files.CameraFile) -> Path:
        target = self.destination / item.filename
        if not target.exists() or target.stat().st_size == item.size:
            return target
        # Camera apps occasionally reuse a filename. Keep both files safely.
        return self.destination / f"{item.media_date:%Y%m%d}_{item.filename}"

    def _completed(self, future: Future[SyncResult]) -> None:
        self._running = False
        try:
            self.finished.emit(future.result())
        except InterruptedError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(str(error))

    def stop(self) -> None:
        self.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
