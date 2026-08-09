"""Native Windows toast notifications, without relying on Qt tray balloons."""

from __future__ import annotations

import html
import os
import subprocess
import sys
from pathlib import Path
import winreg

import ctypes
from win32com.client import Dispatch
from win32com.propsys import propsys, pscon
import pythoncom


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
APP_ID = "NicklausFR.AndroidCameraFetcher"
PROTOCOL = "androidcamerafetcher"


def register_notification_identity() -> None:
    """Register a Start-menu shortcut required by desktop Windows toasts."""
    if os.name != "nt":
        return
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    start_menu.mkdir(parents=True, exist_ok=True)
    shortcut_path = start_menu / "Android Camera Fetcher.lnk"
    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = sys.executable
    shortcut.Arguments = "" if getattr(sys, "frozen", False) else f'"{Path(__file__).with_name("main.py")}"'
    shortcut.WorkingDirectory = str(Path(__file__).parent)
    shortcut.Description = "Android Camera Fetcher"
    shortcut.Save()
    store = propsys.SHGetPropertyStoreFromParsingName(str(shortcut_path), None, 2, propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
    store.Commit()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    _register_protocol_handler()


def _register_protocol_handler() -> None:
    target = Path(sys.executable)
    if getattr(sys, "frozen", False):
        command = f'"{target}" "%1"'
    else:
        pythonw = target.with_name("pythonw.exe")
        command = f'"{pythonw if pythonw.exists() else target}" "{Path(__file__).with_name("main.py")}" "%1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{PROTOCOL}") as key:
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "URL:Android Camera Fetcher")
        with winreg.CreateKey(key, r"shell\open\command") as command_key:
            winreg.SetValueEx(command_key, None, 0, winreg.REG_SZ, command)


def show_notification(title: str, message: str, offer_sync: bool = False) -> None:
    if os.name != "nt":
        return
    actions = ""
    if offer_sync:
        actions = (
            "<actions>"
            f"<action content='Synchroniser' activationType='protocol' arguments='{PROTOCOL}:sync'/>"
            "<action content='Pas maintenant' activationType='system' arguments='dismiss'/>"
            "</actions>"
        )
    xml = (
        f"<toast duration='{'long' if offer_sync else 'short'}'><visual><binding template='ToastGeneric'>"
        f"<text>{html.escape(title)}</text><text>{html.escape(message)}</text>"
        f"</binding></visual>{actions}</toast>"
    )
    script = (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null;"
        "$xml=[Windows.Data.Xml.Dom.XmlDocument]::new();"
        f"$xml.LoadXml(\"{xml}\");"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_ID}').Show($toast)"
    )
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        creationflags=CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
