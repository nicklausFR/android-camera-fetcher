from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
    QVBoxLayout,
)

import adb_client
from i18n import _


DEFAULT_DESTINATION = Path(r"D:\Pictures\Photos\Smartphone")


class AppSettings:
    def __init__(self):
        self.store = QSettings("NicklausFR", "AndroidCameraFetcher")

    @property
    def destination(self):
        return Path(self.store.value("destination", str(DEFAULT_DESTINATION), type=str))

    @property
    def check_seconds(self):
        return max(5, self.store.value("checkSeconds", 15, type=int))

    @property
    def preferred_serial(self):
        return self.store.value("preferredSerial", "", type=str)

    @property
    def connection_mode(self):
        return self.store.value("connectionMode", "auto", type=str)

    @property
    def language(self):
        return self.store.value("language", "en", type=str)

    def save(self, destination, seconds, serial, mode, language):
        self.store.setValue("destination", str(destination))
        self.store.setValue("checkSeconds", seconds)
        self.store.setValue("preferredSerial", serial)
        self.store.setValue("connectionMode", mode)
        self.store.setValue("language", language)


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Options"))
        self.settings = settings
        root = QVBoxLayout(self)

        phone_box = QGroupBox(_("Phone"))
        phone_layout = QFormLayout(phone_box)
        root.addWidget(phone_box)
        self.adb_status = QLabel(_("Checking ADB…"))
        self.adb_status.setWordWrap(True)
        phone_layout.addRow("ADB:", self.adb_status)
        self.seconds = QSpinBox()
        self.seconds.setRange(5, 3600)
        self.seconds.setSuffix(" " + _("seconds"))
        self.seconds.setValue(settings.check_seconds)
        phone_layout.addRow(_("Check phone presence every:"), self.seconds)
        self.mode = QComboBox()
        self.mode.addItem(_("Automatic (USB preferred)"), "auto")
        self.mode.addItem(_("USB only"), "usb")
        self.mode.addItem(_("Wi-Fi only"), "wifi")
        self.mode.setCurrentIndex(max(0, self.mode.findData(settings.connection_mode)))
        phone_layout.addRow(_("ADB transport:"), self.mode)
        self.device = QComboBox()
        self.device.activated.connect(self.device_choice)
        phone_layout.addRow(_("ADB device:"), self.device)

        debug_box = QGroupBox(_("ADB diagnostics"))
        debug_layout = QVBoxLayout(debug_box)
        self.debug = QPlainTextEdit()
        self.debug.setReadOnly(True)
        self.debug.setMaximumBlockCount(200)
        self.debug.setMinimumHeight(110)
        debug_layout.addWidget(self.debug)
        root.addWidget(debug_box)

        sync_box = QGroupBox(_("Synchronization"))
        sync_layout = QFormLayout(sync_box)
        root.addWidget(sync_box)
        self.path = QLineEdit(str(settings.destination))
        browse = QPushButton(_("Browse…"))
        browse.clicked.connect(self.choose)
        row = QHBoxLayout()
        row.addWidget(self.path)
        row.addWidget(browse)
        sync_layout.addRow(_("Synchronization folder:"), row)

        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Français", "fr")
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(settings.language)))
        sync_layout.addRow(_("Language:"), self.language_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.refresh()

    def choose(self):
        value = QFileDialog.getExistingDirectory(self, _("Synchronization folder"), self.path.text())
        if value:
            self.path.setText(value)

    def refresh(self):
        self.device.clear()
        self.device.addItem(_("Automatically choose"), "")
        try:
            self.adb_status.setText("✓ " + adb_client.adb_health())
            result = adb_client.run_adb("devices", "-l", timeout=10)
            self.debug.setPlainText(result.stdout + ("\n" + result.stderr if result.stderr else ""))
            for serial, state in adb_client.list_adb_devices():
                self.device.addItem(f"{serial} — {state}", serial)
        except Exception as error:
            self.adb_status.setText("✗ " + str(error))
            self.debug.setPlainText(str(error))
        self.device.insertSeparator(self.device.count())
        self.device.addItem("↻ " + _("Refresh ADB device list"), "__refresh__")
        self.device.setCurrentIndex(max(0, self.device.findData(self.settings.preferred_serial)))

    def device_choice(self, index):
        if self.device.itemData(index) == "__refresh__":
            self.refresh()

    def values(self):
        return (
            Path(self.path.text()), self.seconds.value(), self.device.currentData(),
            self.mode.currentData(), self.language_combo.currentData(),
        )
