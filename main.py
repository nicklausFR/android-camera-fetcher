import ctypes
import signal
import sys
from ctypes import wintypes

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from i18n import _, configure
from settings import AppSettings
from tray import TrayController
from windows_notifications import PROTOCOL, register_notification_identity


def another_instance_running() -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, "Local\\AndroidCameraFetcherSingleInstance")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    globals()["_instance_mutex"] = mutex
    return ctypes.get_last_error() == 183


def install_console_ctrl_handler(app: QApplication) -> None:
    """Make Ctrl+C quit the Qt event loop when launched from PowerShell."""
    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    @handler_type
    def handler(control_type: int) -> bool:
        if control_type in (0, 1):
            app.quit()
            return True
        return False

    set_handler = ctypes.WinDLL("kernel32", use_last_error=True).SetConsoleCtrlHandler
    set_handler.argtypes = (handler_type, wintypes.BOOL)
    set_handler.restype = wintypes.BOOL
    if set_handler(handler, True):
        globals()["_console_ctrl_handler"] = handler


CONTROL_SERVER = "AndroidCameraFetcherControl"


def send_command_to_running_instance(command: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(CONTROL_SERVER)
    if not socket.waitForConnected(1500):
        return False
    socket.write(command.encode("utf-8"))
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


def install_command_server(app: QApplication, controller: TrayController) -> QLocalServer:
    QLocalServer.removeServer(CONTROL_SERVER)
    server = QLocalServer(app)
    server.listen(CONTROL_SERVER)

    def receive() -> None:
        socket = server.nextPendingConnection()
        socket.waitForReadyRead(1000)
        if bytes(socket.readAll()).decode("utf-8", "replace").strip() == "sync":
            QTimer.singleShot(0, controller.start_sync)
        socket.disconnectFromServer()

    server.newConnection.connect(receive)
    return server


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Android Camera Fetcher")
    app.setQuitOnLastWindowClosed(False)
    configure(AppSettings().language)
    if another_instance_running():
        if any(value == f"{PROTOCOL}:sync" for value in sys.argv):
            send_command_to_running_instance("sync")
            sys.exit(0)
        QMessageBox.information(None, "Android Camera Fetcher", _("The application is already running."))
        sys.exit(0)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    install_console_ctrl_handler(app)
    register_notification_identity()
    controller = TrayController(app)
    command_server = install_command_server(app, controller)
    sys.exit(app.exec())
