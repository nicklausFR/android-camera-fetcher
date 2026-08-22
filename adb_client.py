from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from io import BytesIO
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def find_adb() -> str:
    """Return ADB from PATH or from the usual local Android SDK folders."""
    executable = "adb.exe" if os.name == "nt" else "adb"
    from_path = shutil.which(executable)
    if from_path:
        return from_path

    sdk_roots = [
        os.environ.get("ANDROID_SDK_ROOT"),
        os.environ.get("ANDROID_HOME"),
    ]
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        user_profile = os.environ.get("USERPROFILE")
        if local_app_data:
            sdk_roots.append(str(Path(local_app_data) / "Android" / "Sdk"))
        if user_profile:
            sdk_roots.append(
                str(Path(user_profile) / "AppData" / "Local" / "Android" / "Sdk")
            )

    for sdk_root in sdk_roots:
        if not sdk_root:
            continue
        candidate = Path(sdk_root).expanduser() / "platform-tools" / executable
        if candidate.is_file():
            return str(candidate)

    # Keep the conventional command so subprocess produces the expected
    # FileNotFoundError and the existing user-facing diagnostic remains useful.
    return executable


ADB = find_adb()


@dataclass(frozen=True)
class AndroidDevice:
    serial: str
    connection_type: str
    model: str


@dataclass(frozen=True)
class MediaStoreFile:
    remote_path: str
    modified_date: date
    mime_type: str
    size: int


def run_adb(*arguments: str, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [ADB, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "adb.exe est introuvable. Ajoutez Android Platform Tools au PATH Windows."
        ) from None
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Délai ADB dépassé.") from error


def is_wifi_serial(serial: str) -> bool:
    return (
        (serial.startswith("[") and "]:" in serial)
        or bool(re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}:\d+", serial))
    )


def adb_health() -> str:
    """Return a concise diagnostic confirming that Platform Tools is usable."""
    result = run_adb("version", timeout=10)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ADB ne répond pas.")
    version = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "ADB installé")
    server = run_adb("start-server", timeout=10)
    if server.returncode != 0:
        raise RuntimeError(server.stderr.strip() or "Le serveur ADB ne démarre pas.")
    return version


def list_adb_devices() -> list[tuple[str, str]]:
    result = run_adb("devices")

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Impossible d'exécuter ADB.")

    devices: list[tuple[str, str]] = []

    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue

        serial, state = parts[0], parts[1]

        if not serial.startswith("emulator-"):
            devices.append((serial, state))

    return devices


def discover_wifi_services() -> list[str]:
    result = run_adb("mdns", "services", timeout=10)

    if result.returncode != 0:
        return []

    addresses: list[str] = []

    for line in result.stdout.splitlines():
        if "_adb-tls-connect._tcp" not in line:
            continue

        match = re.search(
            r"((?:\d{1,3}\.){3}\d{1,3}:\d+|\[[0-9a-fA-F:]+\]:\d+)",
            line,
        )

        if match and match.group(1) not in addresses:
            addresses.append(match.group(1))

    return addresses


def connect_wifi_devices() -> None:
    for address in discover_wifi_services():
        run_adb("connect", address, timeout=10)


def get_device_model(serial: str) -> str:
    result = run_adb(
        "-s",
        serial,
        "shell",
        "getprop",
        "ro.product.model",
        timeout=10,
    )

    model = result.stdout.strip()
    return model if result.returncode == 0 and model else "Android"


def select_device(connection_mode: str = "auto", preferred_serial: str = "") -> AndroidDevice:
    if connection_mode not in {"auto", "wifi", "usb"}:
        raise ValueError("Mode de connexion invalide.")

    if connection_mode in {"auto", "wifi"}:
        connect_wifi_devices()

    wifi_devices: list[str] = []
    usb_devices: list[str] = []
    unauthorized_usb: list[str] = []

    for serial, state in list_adb_devices():
        if preferred_serial and serial != preferred_serial:
            continue
        if state == "device":
            if is_wifi_serial(serial):
                wifi_devices.append(serial)
            else:
                usb_devices.append(serial)
        elif state == "unauthorized" and not is_wifi_serial(serial):
            unauthorized_usb.append(serial)

    if connection_mode == "wifi":
        if not wifi_devices:
            raise RuntimeError("Aucun téléphone connecté en Wi-Fi.")
        serial = wifi_devices[0]
        connection_type = "Wi-Fi"

    elif connection_mode == "usb":
        if usb_devices:
            serial = usb_devices[0]
            connection_type = "USB"
        elif unauthorized_usb:
            raise RuntimeError(
                "Téléphone USB détecté mais non autorisé. Déverrouillez-le et acceptez le débogage USB."
            )
        else:
            raise RuntimeError("Aucun téléphone connecté en USB.")

    else:
        # A physical link is both faster and more reliable for a media sync.
        if usb_devices:
            serial = usb_devices[0]
            connection_type = "USB"
        elif wifi_devices:
            serial = wifi_devices[0]
            connection_type = "Wi-Fi"
        elif unauthorized_usb:
            raise RuntimeError(
                "Téléphone USB détecté mais non autorisé. Déverrouillez-le et acceptez le débogage USB."
            )
        else:
            raise RuntimeError("Aucun téléphone Android disponible.")

    return AndroidDevice(
        serial=serial,
        connection_type=connection_type,
        model=get_device_model(serial),
    )


def query_camera_files(
    serial: str,
    remote_root: str,
    start_date: date,
    end_date: date,
    media_mode: str = "all",
    newest_first: bool = False,
) -> list[MediaStoreFile]:
    relative_path = remote_root.removeprefix("/sdcard/").strip("/") + "/"

    start_timestamp = int(datetime.combine(start_date, datetime_time.min).timestamp())
    end_timestamp = int(
        datetime.combine(end_date + timedelta(days=1), datetime_time.min).timestamp()
    )

    where_parts = [
        f"relative_path='{relative_path}'",
        f"date_modified>={start_timestamp}",
        f"date_modified<{end_timestamp}",
    ]

    if media_mode == "photos":
        where_parts.append("mime_type LIKE 'image/%'")
    elif media_mode == "videos":
        where_parts.append("mime_type LIKE 'video/%'")
    else:
        where_parts.append("(mime_type LIKE 'image/%' OR mime_type LIKE 'video/%')")

    where_clause = " AND ".join(where_parts)

    shell_command = (
        "content query "
        "--uri content://media/external/file "
        "--projection _data:date_modified:mime_type:_size "
        f"--where {shlex.quote(where_clause)}"
    )

    result = run_adb("-s", serial, "shell", shell_command, timeout=60)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Impossible d'interroger MediaStore.")

    row_pattern = re.compile(
        r"_data=(.*?),\s*"
        r"date_modified=(\d+),\s*"
        r"mime_type=([^,]+),\s*"
        r"_size=(\d+)"
    )

    files: list[MediaStoreFile] = []

    for raw_line in result.stdout.splitlines():
        match = row_pattern.search(raw_line.strip())
        if not match:
            continue

        try:
            modified_date = datetime.fromtimestamp(int(match.group(2))).date()
            size = int(match.group(4))
        except (ValueError, OverflowError, OSError):
            continue

        files.append(
            MediaStoreFile(
                remote_path=match.group(1),
                modified_date=modified_date,
                mime_type=match.group(3).strip(),
                size=size,
            )
        )

    files.sort(
        key=lambda item: (item.modified_date, item.remote_path),
        reverse=newest_first,
    )
    return files


def make_image_thumbnail(serial: str, remote_path: str, max_size: int = 280) -> bytes:
    """Return a compact JPEG thumbnail for a remote image.

    The source is fetched only when it is absent from the local thumbnail cache.
    """
    try:
        result = subprocess.run(
            [ADB, "-s", serial, "exec-out", "cat", remote_path],
            capture_output=True,
            timeout=90,
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError:
        raise RuntimeError("adb.exe est introuvable.") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("Délai de chargement de la miniature dépassé.") from None

    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("Impossible de charger la miniature depuis le téléphone.")

    try:
        from PIL import Image

        with Image.open(BytesIO(result.stdout)) as image:
            image.thumbnail((max_size, max_size))
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
            return output.getvalue()
    except Exception as error:
        raise RuntimeError("Format photo non pris en charge pour la miniature.") from error


def pull_file(
    serial: str,
    remote_path: str,
    local_path: Path,
    cancel_event: threading.Event | None = None,
) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        process = subprocess.Popen(
            [
                ADB,
                "-s",
                serial,
                "pull",
                remote_path,
                str(local_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "adb.exe est introuvable. "
            "Ajoutez Android Platform Tools au PATH Windows."
        ) from None

    while process.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()

            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            if local_path.exists():
                try:
                    local_path.unlink()
                except OSError:
                    pass

            raise InterruptedError("Téléchargement annulé.")

        time.sleep(0.1)

    stdout, stderr = process.communicate()

    if process.returncode != 0:
        if local_path.exists():
            try:
                local_path.unlink()
            except OSError:
                pass

        raise RuntimeError(
            stderr.strip()
            or stdout.strip()
            or f"Échec du téléchargement : {remote_path}"
        )
