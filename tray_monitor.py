from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

import adb_client


class DeviceMonitor(QObject):
    """Poll ADB without ever blocking the Qt user interface."""

    available = Signal(object)
    unavailable = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="adb")
        self._checking = False
        self._device: adb_client.AndroidDevice | None = None
        self.connection_mode = "auto"
        self.preferred_serial = ""

    @property
    def device(self) -> adb_client.AndroidDevice | None:
        return self._device

    def check_now(self) -> None:
        if self._checking:
            return

        self._checking = True
        future = self._executor.submit(adb_client.select_device, self.connection_mode, self.preferred_serial)
        future.add_done_callback(self._check_finished)

    def _check_finished(self, future: Future[adb_client.AndroidDevice]) -> None:
        self._checking = False
        try:
            device = future.result()
        except Exception as error:
            if self._device is not None:
                self._device = None
                self.unavailable.emit(str(error))
            return

        previous = self._device
        self._device = device
        if previous is None or previous.serial != device.serial:
            self.available.emit(device)

    def stop(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def set_preferences(self, connection_mode: str, preferred_serial: str) -> None:
        self.connection_mode = connection_mode
        self.preferred_serial = preferred_serial
        self.check_now()
