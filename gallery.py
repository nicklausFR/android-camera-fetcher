from __future__ import annotations

import hashlib
import os
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QComboBox,
    QDateEdit,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import adb_client
import camera_files


THUMBNAIL_SIZE = 150
PAGE_SIZE = 60


def _cache_path(device: adb_client.AndroidDevice, item: camera_files.CameraFile) -> Path:
    key = f"{device.serial}\0{item.remote_path}\0{item.size}\0{item.media_date}".encode()
    name = hashlib.sha256(key).hexdigest() + ".jpg"
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AndroidCameraFetcher" / "thumbnails"
    return root / name


def _video_placeholder() -> QPixmap:
    pixmap = QPixmap(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
    pixmap.fill(QColor("#263447"))
    painter = QPainter(pixmap)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#4d9ae8"))
    painter.drawEllipse(47, 47, 56, 56)
    painter.setBrush(QColor("#ffffff"))
    painter.drawPolygon([QPoint(68, 61), QPoint(68, 89), QPoint(91, 75)])
    painter.end()
    return pixmap


class MediaTile(QWidget):
    def __init__(self, item: camera_files.CameraFile) -> None:
        super().__init__()
        self.preview = QLabel()
        self.preview.setFixedSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background: #edf2f7; border-radius: 6px;")
        if item.mime_type.startswith("video/"):
            self.preview.setPixmap(_video_placeholder())
        else:
            self.preview.setText("Chargement…")
        name = QLabel(item.filename)
        name.setWordWrap(True)
        name.setMaximumWidth(THUMBNAIL_SIZE)
        name.setFont(QFont("", 9))
        metadata = QLabel(f"{item.media_date.isoformat()} · {self._format_size(item.size)}")
        metadata.setStyleSheet("color: #64748b;")
        metadata.setMaximumWidth(THUMBNAIL_SIZE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(5)
        layout.addWidget(self.preview)
        layout.addWidget(name)
        layout.addWidget(metadata)

    def set_thumbnail(self, data: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.preview.setPixmap(
                pixmap.scaled(
                    THUMBNAIL_SIZE,
                    THUMBNAIL_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.preview.setText("Aperçu indisponible")

    @staticmethod
    def _format_size(value: int) -> str:
        return f"{value / 1_048_576:.1f} Mo" if value >= 1_048_576 else f"{value // 1024} Ko"


class GalleryWindow(QWidget):
    files_loaded = Signal(int, object)
    loading_failed = Signal(int, str)
    thumbnail_ready = Signal(object, bytes)

    def __init__(self, monitor) -> None:
        super().__init__()
        self._monitor = monitor
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gallery")
        self._files: list[camera_files.CameraFile] = []
        self._shown = 0
        self._tiles: dict[str, MediaTile] = {}
        self._load_request = 0
        self._reload_scheduled = False
        self.setWindowTitle("Android Camera Fetcher")
        self.resize(980, 720)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title = QLabel("Photos et vidéos de l’appareil photo")
        self.title.setStyleSheet("font-size: 17px; font-weight: 600;")
        header.addWidget(self.title)
        header.addStretch()
        refresh = QPushButton("Actualiser")
        refresh.clicked.connect(self.reload)
        header.addWidget(refresh)
        layout.addLayout(header)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Afficher :"))
        self.filter_mode = QComboBox()
        self.filter_mode.addItem("Choisir un filtre…", "none")
        self.filter_mode.addItem("Toutes les photos et vidéos", "all")
        self.filter_mode.addItem("Une date", "date")
        self.filter_mode.addItem("Une période", "period")
        self.filter_mode.currentIndexChanged.connect(self._filter_mode_changed)
        filters.addWidget(self.filter_mode)
        self.single_date = QDateEdit(QDate.currentDate())
        self.single_date.setCalendarPopup(True)
        self.single_date.setDisplayFormat("dd/MM/yyyy")
        self.single_date.dateChanged.connect(self._schedule_reload)
        filters.addWidget(self.single_date)
        self.period_from_label = QLabel("Du :")
        filters.addWidget(self.period_from_label)
        self.period_start = QDateEdit(QDate.currentDate())
        self.period_start.setCalendarPopup(True)
        self.period_start.setDisplayFormat("dd/MM/yyyy")
        self.period_start.dateChanged.connect(self._schedule_reload)
        filters.addWidget(self.period_start)
        self.period_to_label = QLabel("au :")
        filters.addWidget(self.period_to_label)
        self.period_end = QDateEdit(QDate.currentDate())
        self.period_end.setCalendarPopup(True)
        self.period_end.setDisplayFormat("dd/MM/yyyy")
        self.period_end.dateChanged.connect(self._schedule_reload)
        filters.addWidget(self.period_end)
        filters.addStretch()
        layout.addLayout(filters)
        self.status = QLabel("Recherche d’un téléphone…")
        layout.addWidget(self.status)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid_host)
        layout.addWidget(scroll)
        self.more = QPushButton("Afficher les éléments suivants")
        self.more.clicked.connect(self.show_next_page)
        self.more.setVisible(False)
        layout.addWidget(self.more, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._filter_mode_changed()

        self.files_loaded.connect(self._render_files)
        self.loading_failed.connect(self._render_error)
        self.thumbnail_ready.connect(self._set_thumbnail)
        monitor.available.connect(lambda _device: self.reload())
        monitor.unavailable.connect(lambda _reason: self.status.setText("Aucun téléphone ADB disponible."))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._files and self.filter_mode.currentData() != "none":
            self.reload()

    def reload(self) -> None:
        self._reload_scheduled = False
        if self.filter_mode.currentData() == "none":
            self._load_request += 1
            self._clear_gallery()
            self.status.setText("Choisissez Toutes, une date ou une période.")
            return
        device = self._monitor.device
        if device is None:
            self.status.setText("Aucun téléphone ADB disponible. Vérification en cours…")
            self._monitor.check_now()
            return
        self.status.setText("Lecture des médias de DCIM/Camera…")
        self._load_request += 1
        request = self._load_request
        start_date, end_date = self._selected_dates()
        future = self._executor.submit(self._load_files, device, start_date, end_date)
        future.add_done_callback(
            lambda result: self._files_finished(request, result)
        )

    @staticmethod
    def _load_files(
        device: adb_client.AndroidDevice,
        start_date: date,
        end_date: date,
    ) -> list[camera_files.CameraFile]:
        files = adb_client.query_camera_files(
            device.serial,
            camera_files.PHONE_ROOT,
            start_date,
            end_date,
            newest_first=True,
        )
        return camera_files.build_camera_files(files)

    def _filter_mode_changed(self) -> None:
        mode = self.filter_mode.currentData()
        self.single_date.setVisible(mode == "date")
        show_period = mode == "period"
        self.period_from_label.setVisible(show_period)
        self.period_start.setVisible(show_period)
        self.period_to_label.setVisible(show_period)
        self.period_end.setVisible(show_period)
        if mode == "none":
            self._load_request += 1
            self._clear_gallery()
            self.status.setText("Choisissez Toutes, une date ou une période.")
        elif self.isVisible():
            self._schedule_reload()

    def _schedule_reload(self, *_args) -> None:
        """Coalesce calendar changes before querying ADB again."""
        if not self.isVisible() or self._reload_scheduled:
            return
        self._reload_scheduled = True
        QTimer.singleShot(150, self.reload)

    def _selected_dates(self) -> tuple[date, date]:
        mode = self.filter_mode.currentData()
        if mode == "date":
            selected = self.single_date.date().toPython()
            return selected, selected
        if mode == "period":
            start = self.period_start.date().toPython()
            end = self.period_end.date().toPython()
            return min(start, end), max(start, end)
        return date(2000, 1, 1), date.today()

    def _files_finished(
        self,
        request: int,
        future: Future[list[camera_files.CameraFile]],
    ) -> None:
        try:
            self.files_loaded.emit(request, future.result())
        except Exception as error:
            self.loading_failed.emit(request, str(error))

    def _render_files(self, request: int, files: list[camera_files.CameraFile]) -> None:
        if request != self._load_request:
            return
        self._clear_gallery()
        self._files = files
        self._shown = 0
        self._tiles.clear()
        self.status.setText(f"{len(files)} média(s), du plus récent au plus ancien.")
        self.show_next_page()

    def _clear_gallery(self) -> None:
        while self.grid.count():
            child = self.grid.takeAt(0)
            if child.widget() is not None:
                child.widget().deleteLater()
        self._files = []
        self._shown = 0
        self._tiles.clear()
        self.more.setVisible(False)

    def _render_error(self, request: int, message: str) -> None:
        if request != self._load_request:
            return
        self.status.setText(f"Impossible de lire les médias : {message}")

    def show_next_page(self) -> None:
        end = min(self._shown + PAGE_SIZE, len(self._files))
        for index in range(self._shown, end):
            item = self._files[index]
            tile = MediaTile(item)
            self._tiles[item.remote_path] = tile
            self.grid.addWidget(tile, index // 6, index % 6)
            if item.mime_type.startswith("image/"):
                self._load_thumbnail(item)
        self._shown = end
        self.more.setVisible(self._shown < len(self._files))

    def _load_thumbnail(self, item: camera_files.CameraFile) -> None:
        device = self._monitor.device
        if device is None:
            return
        future = self._executor.submit(self._thumbnail, device, item)
        future.add_done_callback(lambda result: self._thumbnail_finished(item.remote_path, result))

    @staticmethod
    def _thumbnail(device: adb_client.AndroidDevice, item: camera_files.CameraFile) -> bytes:
        path = _cache_path(device, item)
        if path.exists():
            return path.read_bytes()
        data = adb_client.make_image_thumbnail(device.serial, item.remote_path, THUMBNAIL_SIZE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return data

    def _thumbnail_finished(self, remote_path: str, future: Future[bytes]) -> None:
        try:
            self.thumbnail_ready.emit(remote_path, future.result())
        except Exception:
            pass

    def _set_thumbnail(self, remote_path: str, data: bytes) -> None:
        tile = self._tiles.get(remote_path)
        if tile is not None:
            tile.set_thumbnail(data)

    def closeEvent(self, event) -> None:
        self.hide()
        event.ignore()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
