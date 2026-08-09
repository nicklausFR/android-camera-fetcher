from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QMessageBox, QRadioButton,
    QVBoxLayout,
)

from i18n import _


FIRST_MEDIA_DATE = QDate(2000, 1, 1)


class DownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("One-off download"))
        self.setMinimumWidth(460)
        self.destination = None
        root = QVBoxLayout(self)
        connection_box = QGroupBox(_("Connection"))
        connection_layout = QFormLayout(connection_box)
        self.connection = QComboBox()
        self.connection.addItem(_("Automatic (USB preferred)"), "auto")
        self.connection.addItem(_("USB only"), "usb")
        self.connection.addItem(_("Wi-Fi only"), "wifi")
        connection_layout.addRow(_("Use:"), self.connection)
        root.addWidget(connection_box)

        selection_box = QGroupBox(_("Selection"))
        selection_layout = QFormLayout(selection_box)
        self.all_files = QRadioButton(_("All photos and videos"))
        self.by_date = QRadioButton(_("One date"))
        self.by_period = QRadioButton(_("A period"))
        self.selection_group = QButtonGroup(self)
        for button in (self.all_files, self.by_date, self.by_period):
            self.selection_group.addButton(button)
            button.toggled.connect(self._update_fields)
        selection_layout.addRow(self.all_files)
        selection_layout.addRow(self.by_date)
        self.single_date = self._empty_date_edit()
        selection_layout.addRow(_("Date:"), self.single_date)
        selection_layout.addRow(self.by_period)
        self.start_date = self._empty_date_edit()
        self.end_date = self._empty_date_edit()
        selection_layout.addRow(_("From:"), self.start_date)
        selection_layout.addRow(_("To:"), self.end_date)
        root.addWidget(selection_box)

        type_box = QGroupBox(_("File types"))
        types = QHBoxLayout(type_box)
        self.photos = QCheckBox(_("Photos"))
        self.photos.setChecked(True)
        self.videos = QCheckBox(_("Videos"))
        self.videos.setChecked(True)
        types.addWidget(self.photos)
        types.addWidget(self.videos)
        types.addStretch()
        root.addWidget(type_box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(_("Download"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._update_fields()

    @staticmethod
    def _empty_date_edit():
        widget = QDateEdit(FIRST_MEDIA_DATE)
        widget.setMinimumDate(FIRST_MEDIA_DATE)
        widget.setSpecialValueText(_("Choose a date"))
        widget.setCalendarPopup(True)
        widget.setDisplayFormat("dd/MM/yyyy")
        return widget

    def _update_fields(self):
        self.single_date.setEnabled(self.by_date.isChecked())
        self.start_date.setEnabled(self.by_period.isChecked())
        self.end_date.setEnabled(self.by_period.isChecked())

    def accept(self):
        if not self.selection_group.checkedButton():
            QMessageBox.warning(self, _("Download"), _("Choose all files, one date, or a period."))
            return
        if not self.photos.isChecked() and not self.videos.isChecked():
            QMessageBox.warning(self, _("Download"), _("Choose photos, videos, or both."))
            return
        if self.by_date.isChecked() and self.single_date.date() == FIRST_MEDIA_DATE:
            QMessageBox.warning(self, _("Download"), _("Choose a date."))
            return
        if self.by_period.isChecked() and (self.start_date.date() == FIRST_MEDIA_DATE or self.end_date.date() == FIRST_MEDIA_DATE):
            QMessageBox.warning(self, _("Download"), _("Choose both dates for the period."))
            return
        folder = QFileDialog.getExistingDirectory(self, _("One-off download folder"))
        if not folder:
            return
        self.destination = Path(folder)
        super().accept()

    def selection(self):
        if self.all_files.isChecked():
            start, end = date(2000, 1, 1), date.today()
        elif self.by_date.isChecked():
            start = end = self.single_date.date().toPython()
        else:
            start, end = sorted((self.start_date.date().toPython(), self.end_date.date().toPython()))
        media = "all" if self.photos.isChecked() and self.videos.isChecked() else ("photos" if self.photos.isChecked() else "videos")
        return self.connection.currentData(), start, end, media, self.destination
