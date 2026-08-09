import subprocess

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMenu, QMessageBox, QProgressBar, QPushButton, QSystemTrayIcon, QVBoxLayout

from download_dialog import DownloadDialog
from i18n import _
from settings import AppSettings, SettingsDialog
from sync_service import SyncService
from tray_monitor import DeviceMonitor
from windows_notifications import show_notification


def create_camera_icon(state="idle"):
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    outline = QColor("#07557e" if state != "idle" else "#64748b")
    painter.setBrush(outline)
    painter.drawRoundedRect(5, 2, 47, 60, 11, 11)
    painter.setBrush(QColor("#0ca1c8" if state != "idle" else "#94a3b8"))
    painter.drawRoundedRect(11, 8, 35, 48, 7, 7)
    painter.setBrush(QColor("#063b61"))
    painter.drawRoundedRect(14, 12, 29, 17, 4, 4)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(16, 33, 24, 6, 3, 3)
    painter.drawEllipse(25, 48, 6, 6)
    if state == "syncing":
        painter.setBrush(QColor("#1479d1"))
        painter.drawEllipse(34, 34, 29, 29)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI Symbol", 22))
        painter.drawText(38, 57, "↻")
    elif state == "synced":
        painter.setBrush(QColor("#12a150"))
        painter.drawEllipse(34, 34, 29, 29)
        painter.setPen(QPen(QColor("#ffffff"), 5))
        painter.drawLine(41, 48, 47, 54)
        painter.drawLine(47, 54, 57, 42)
    painter.end()
    return QIcon(pixmap)


class SyncStatusDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Android Camera Fetcher — synchronization"))
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        self.text = QLabel(_("Preparing…"))
        self.text.setWordWrap(True)
        layout.addWidget(self.text)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        close = QPushButton(_("Hide"))
        close.clicked.connect(self.hide)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)

    def started(self, device):
        self.text.setText(_("Reading media from {device}…").format(device=device))
        self.progress.hide()

    def update(self, index, total, name):
        self.progress.show()
        self.progress.setRange(0, total)
        self.progress.setValue(index)
        self.text.setText(_("Copying {index}/{total} — {name}").format(index=index, total=total, name=name))

    def completed(self, text):
        self.progress.show()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.text.setText(text)


class TrayController(QObject):
    def __init__(self, app: QApplication):
        super().__init__(app)
        self.app = app
        self.settings = AppSettings()
        self.offer_sync = False
        self.monitor = DeviceMonitor()
        self.sync_service = SyncService(self.settings.destination)
        self.sync_status = SyncStatusDialog()
        self.tray = QSystemTrayIcon(create_camera_icon(), app)
        self.tray.setToolTip(_("Android Camera Fetcher — looking for a phone"))
        menu = QMenu()
        open_action = QAction(_("Open"), menu)
        open_action.triggered.connect(self.show_window)
        self.sync_action = QAction(_("Synchronize all now"), menu)
        self.sync_action.triggered.connect(lambda: self.start_sync())
        download_action = QAction(_("One-off download…"), menu)
        download_action.triggered.connect(self.open_download_dialog)
        check_action = QAction(_("Check now"), menu)
        check_action.triggered.connect(self.monitor.check_now)
        options_action = QAction(_("Options…"), menu)
        options_action.triggered.connect(self.open_options)
        quit_action = QAction(_("Quit"), menu)
        quit_action.triggered.connect(app.quit)
        for action in (open_action, self.sync_action, download_action, check_action, options_action):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.activated.connect(self.activated)
        self.tray.messageClicked.connect(self.notification_clicked)
        self._menu = menu
        self.monitor.available.connect(self.device_available)
        self.monitor.unavailable.connect(self.device_unavailable)
        self.sync_service.started.connect(self.sync_started)
        self.sync_service.progress.connect(self.sync_progress)
        self.sync_service.finished.connect(self.sync_finished)
        self.sync_service.failed.connect(self.sync_failed)
        self.monitor.set_preferences(self.settings.connection_mode, self.settings.preferred_serial)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.monitor.check_now)
        self.apply_interval()
        QTimer.singleShot(1000, self.monitor.check_now)
        app.aboutToQuit.connect(self.stop)

    def apply_interval(self):
        self.timer.start(self.settings.check_seconds * 1000)

    def activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            QTimer.singleShot(0, self.show_window)

    def notification_clicked(self):
        if self.offer_sync:
            self.start_sync()

    def device_available(self, device):
        self.offer_sync = True
        self.tray.setIcon(create_camera_icon("connected"))
        self.tray.setToolTip(_("Android Camera Fetcher — {model} available via {transport}").format(model=device.model, transport=device.connection_type))
        message = _("{model} is available via {transport}. Click here to synchronize.").format(model=device.model, transport=device.connection_type)
        self.tray.showMessage("Android Camera Fetcher", message, QSystemTrayIcon.MessageIcon.Information, 8000)
        show_notification("Android Camera Fetcher", _("{model} is connected via {transport}. Synchronize now?").format(model=device.model, transport=device.connection_type), offer_sync=True)

    def device_unavailable(self, _device):
        self.offer_sync = False
        self.tray.setIcon(create_camera_icon())
        self.tray.setToolTip(_("Android Camera Fetcher — phone unavailable"))

    def start_sync(self, connection_mode="auto", start_date=None, end_date=None, media_mode="all", destination=None):
        self._active_destination = destination or self.settings.destination
        self.sync_service.destination = self._active_destination
        chosen_mode = connection_mode if connection_mode != "auto" else self.settings.connection_mode
        self.offer_sync = False
        self.sync_action.setEnabled(False)
        self.tray.setIcon(create_camera_icon("syncing"))
        self.sync_status.text.setText(_("Checking files already present…"))
        self.sync_status.progress.hide()
        self.sync_service.start(connection_mode=chosen_mode, start_date=start_date, end_date=end_date, media_mode=media_mode, preferred_serial=self.settings.preferred_serial)
        self.tray.setToolTip(_("Android Camera Fetcher — preparing synchronization…"))
        self.tray.showMessage("Android Camera Fetcher", _("Preparing synchronization…"), QSystemTrayIcon.MessageIcon.Information, 5000)

    def sync_started(self, device):
        self.tray.setToolTip(_("Android Camera Fetcher — synchronizing from {device}").format(device=device))
        self.tray.showMessage("Android Camera Fetcher", _("Synchronization started from {device}.").format(device=device), QSystemTrayIcon.MessageIcon.Information, 5000)

    def sync_progress(self, index, total, name, copied_this_file):
        if copied_this_file:
            if not self.sync_status.isVisible():
                self.sync_status.show()
                self.sync_status.raise_()
            self.sync_status.update(index, total, name)

    def sync_finished(self, _result):
        self.sync_action.setEnabled(True)
        self.tray.setIcon(create_camera_icon("synced"))
        message = _("Sync OK")
        self.sync_status.completed(message)
        self.tray.showMessage(_("Synchronization complete"), message, QSystemTrayIcon.MessageIcon.Information, 10000)
        self.sync_service.destination = self.settings.destination

    def sync_failed(self, message):
        self.sync_action.setEnabled(True)
        self.tray.setIcon(create_camera_icon("connected" if self.monitor.device else "idle"))
        self.sync_status.completed(_("Synchronization interrupted: {message}").format(message=message))
        self.tray.showMessage(_("Synchronization interrupted"), message, QSystemTrayIcon.MessageIcon.Warning, 8000)
        self.sync_service.destination = self.settings.destination

    def show_window(self):
        destination = self.sync_service.destination
        if not destination.exists():
            destination.mkdir(parents=True, exist_ok=True)
        media = [path for path in destination.iterdir() if path.is_file()]
        if media:
            newest = max(media, key=lambda path: path.stat().st_mtime)
            subprocess.Popen(["explorer.exe", f"/select,{newest}"])
        else:
            subprocess.Popen(["explorer.exe", str(destination)])

    def open_download_dialog(self):
        dialog = DownloadDialog()
        if dialog.exec() == dialog.DialogCode.Accepted:
            connection_mode, start_date, end_date, media_mode, destination = dialog.selection()
            self.start_sync(connection_mode, start_date, end_date, media_mode, destination)

    def open_options(self):
        dialog = SettingsDialog(self.settings)
        if dialog.exec() == dialog.DialogCode.Accepted:
            destination, seconds, serial, mode, language = dialog.values()
            language_changed = language != self.settings.language
            self.settings.save(destination, seconds, serial, mode, language)
            self.sync_service.destination = destination
            self.monitor.set_preferences(mode, serial)
            self.apply_interval()
            if language_changed:
                QMessageBox.information(self.sync_status, _("Language"), _("The language will change when the application is restarted."))

    def stop(self):
        self.timer.stop()
        self.monitor.stop()
        self.sync_service.stop()
        self.tray.hide()
