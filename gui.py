from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import adb_client
import camera_files
from date_picker import choose_date


class AndroidCameraFetcherGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Android Camera Fetcher")
        self.geometry("720x620")
        self.minsize(680, 580)

        self.device: adb_client.AndroidDevice | None = None
        self.files: list[camera_files.CameraFile] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()

        self.connection_mode = tk.StringVar(value="auto")
        self.selection_mode = tk.StringVar(value="")
        self.media_mode = tk.StringVar(value="all")

        today = date.today()

        self.single_date = tk.StringVar(value="")
        self.start_date = tk.StringVar(value="")
        self.end_date = tk.StringVar(value="")
        self.last_days = tk.StringVar(value="")
        self.output_directory = tk.StringVar(
            value=str(Path.home() / "Pictures")
        )

        self.device_text = tk.StringVar(value="Aucun téléphone détecté")
        self.connection_text = tk.StringVar(value="-")
        self.file_count_text = tk.StringVar(value="0")
        self.total_size_text = tk.StringVar(value="0 B")
        self.progress_text = tk.StringVar(value="Prêt")
        self.progress_value = tk.DoubleVar(value=0)
        self.analysis_job: str | None = None
        self.loading_step = 0
        self.loading_active = False
        self.cancel_download_event = threading.Event()
        self.download_running = False

        self._build_ui()
        self._update_selection_state()
        self._bind_auto_analysis()
        self.after(100, self._process_events)
        self.after(250, self.refresh_device)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=14)
        container.pack(fill="both", expand=True)

        device_frame = ttk.LabelFrame(container, text="Téléphone", padding=12)
        device_frame.pack(fill="x")

        ttk.Label(
            device_frame,
            textvariable=self.device_text,
            font=("", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            device_frame,
            textvariable=self.connection_text,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        mode_frame = ttk.Frame(device_frame)
        mode_frame.grid(row=0, column=1, rowspan=2, padx=(20, 10))

        for index, (label, value) in enumerate(
            (("Auto", "auto"), ("Wi-Fi", "wifi"), ("USB", "usb"))
        ):
            ttk.Radiobutton(
                mode_frame,
                text=label,
                value=value,
                variable=self.connection_mode,
            ).grid(row=0, column=index, padx=4)

        self.refresh_button = ttk.Button(
            device_frame,
            text="Actualiser",
            command=self.refresh_device,
        )
        self.refresh_button.grid(row=0, column=2, rowspan=2)

        device_frame.columnconfigure(0, weight=1)

        selection_frame = ttk.LabelFrame(container, text="Sélection", padding=12)
        selection_frame.pack(fill="x", pady=(12, 0))

        ttk.Radiobutton(
            selection_frame,
            text="Date",
            value="date",
            variable=self.selection_mode,
            command=self._update_selection_state,
        ).grid(row=0, column=0, sticky="w")

        self.single_date_entry = ttk.Entry(
            selection_frame,
            textvariable=self.single_date,
            width=14,
        )
        self.single_date_entry.grid(row=0, column=1, sticky="w", padx=(8, 4))

        self.single_date_button = ttk.Button(
            selection_frame,
            text="📅",
            width=3,
            command=lambda: self.open_date_picker(self.single_date),
        )
        self.single_date_button.grid(row=0, column=2, sticky="w", padx=(0, 20))

        ttk.Radiobutton(
            selection_frame,
            text="Période",
            value="period",
            variable=self.selection_mode,
            command=self._update_selection_state,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.start_date_entry = ttk.Entry(
            selection_frame,
            textvariable=self.start_date,
            width=14,
        )
        self.start_date_entry.grid(row=1, column=1, sticky="w", padx=(8, 4), pady=(8, 0))

        self.start_date_button = ttk.Button(
            selection_frame,
            text="📅",
            width=3,
            command=lambda: self.open_date_picker(self.start_date),
        )
        self.start_date_button.grid(row=1, column=2, sticky="w", pady=(8, 0))

        ttk.Label(selection_frame, text="à").grid(
            row=1,
            column=3,
            padx=(8, 4),
            pady=(8, 0),
        )

        self.end_date_entry = ttk.Entry(
            selection_frame,
            textvariable=self.end_date,
            width=14,
        )
        self.end_date_entry.grid(row=1, column=4, sticky="w", padx=(0, 4), pady=(8, 0))

        self.end_date_button = ttk.Button(
            selection_frame,
            text="📅",
            width=3,
            command=lambda: self.open_date_picker(self.end_date),
        )
        self.end_date_button.grid(row=1, column=5, sticky="w", pady=(8, 0))

        ttk.Radiobutton(
            selection_frame,
            text="Derniers jours",
            value="last",
            variable=self.selection_mode,
            command=self._update_selection_state,
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))

        self.last_days_entry = ttk.Entry(
            selection_frame,
            textvariable=self.last_days,
            width=8,
        )
        self.last_days_entry.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

        media_frame = ttk.Frame(selection_frame)
        media_frame.grid(row=3, column=0, columnspan=6, sticky="w", pady=(14, 0))

        for index, (label, value) in enumerate(
            (
                ("Photos + vidéos", "all"),
                ("Photos uniquement", "photos"),
                ("Vidéos uniquement", "videos"),
            )
        ):
            ttk.Radiobutton(
                media_frame,
                text=label,
                value=value,
                variable=self.media_mode,
            ).grid(row=0, column=index, padx=(0, 18))

        files_frame = ttk.LabelFrame(
            container,
            text="Fichiers",
            padding=12,
        )
        files_frame.pack(fill="x", pady=(12, 0))

        ttk.Label(
            files_frame,
            text="Fichiers correspondants :",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            files_frame,
            textvariable=self.file_count_text,
            font=("", 11, "bold"),
        ).grid(row=0, column=1, sticky="w", padx=(8, 30))

        ttk.Label(
            files_frame,
            text="Taille totale :",
        ).grid(row=0, column=2, sticky="w")

        ttk.Label(
            files_frame,
            textvariable=self.total_size_text,
            font=("", 11, "bold"),
        ).grid(row=0, column=3, sticky="w", padx=(8, 0))

        self.loading_label = ttk.Label(
            files_frame,
            text="",
        )
        self.loading_label.grid(
            row=0,
            column=4,
            sticky="w",
            padx=(12, 0),
        )

        self.analyze_button = ttk.Button(
            files_frame,
            text="Actualiser les fichiers",
            command=self.analyze,
        )
        self.analyze_button.grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="e",
            pady=(12, 0),
        )

        destination_frame = ttk.LabelFrame(
            container,
            text="Destination",
            padding=12,
        )
        destination_frame.pack(fill="x", pady=(12, 0))

        ttk.Entry(
            destination_frame,
            textvariable=self.output_directory,
        ).grid(row=0, column=0, sticky="ew")

        ttk.Button(
            destination_frame,
            text="Parcourir…",
            command=self.choose_output_directory,
        ).grid(row=0, column=1, padx=(8, 0))

        destination_frame.columnconfigure(0, weight=1)

        transfer_frame = ttk.LabelFrame(
            container,
            text="Téléchargement",
            padding=12,
        )
        transfer_frame.pack(fill="both", expand=True, pady=(12, 0))

        action_row = ttk.Frame(transfer_frame)
        action_row.pack(fill="x")

        self.download_button = ttk.Button(
            action_row,
            text="Télécharger",
            command=self.download,
            state="disabled",
        )
        self.download_button.pack(side="right")

        self.cancel_button = ttk.Button(
            action_row,
            text="Annuler",
            command=self.cancel_download,
            state="disabled",
        )
        self.cancel_button.pack(side="right", padx=(0, 8))

        ttk.Progressbar(
            transfer_frame,
            variable=self.progress_value,
            maximum=100,
        ).pack(fill="x", pady=(14, 6))

        ttk.Label(
            transfer_frame,
            textvariable=self.progress_text,
        ).pack(anchor="w")

        self.log = tk.Text(
            transfer_frame,
            height=8,
            state="disabled",
            wrap="word",
        )
        self.log.pack(fill="both", expand=True, pady=(10, 0))

    def _update_selection_state(self) -> None:
        mode = self.selection_mode.get()

        date_state = "normal" if mode == "date" else "disabled"
        period_state = "normal" if mode == "period" else "disabled"

        self.single_date_entry.configure(state=date_state)
        self.single_date_button.configure(state=date_state)
        self.start_date_entry.configure(state=period_state)
        self.start_date_button.configure(state=period_state)
        self.end_date_entry.configure(state=period_state)
        self.end_date_button.configure(state=period_state)
        self.last_days_entry.configure(
            state="normal" if mode == "last" else "disabled"
        )
        self._schedule_auto_analysis()

    def _start_loading_indicator(self) -> None:
        self.loading_active = True
        self.loading_step = 0
        self._animate_loading_indicator()

    def _animate_loading_indicator(self) -> None:
        if not self.loading_active:
            self.loading_label.configure(text="")
            return

        symbols = ("◐", "◓", "◑", "◒")
        symbol = symbols[self.loading_step % len(symbols)]
        self.loading_label.configure(text=f"{symbol} Calcul…")
        self.loading_step += 1
        self.after(150, self._animate_loading_indicator)

    def _stop_loading_indicator(self) -> None:
        self.loading_active = False
        self.cancel_download_event = threading.Event()
        self.download_running = False
        self.loading_label.configure(text="")

    def _bind_auto_analysis(self) -> None:
        variables = (
            self.selection_mode,
            self.media_mode,
            self.single_date,
            self.start_date,
            self.end_date,
            self.last_days,
        )

        for variable in variables:
            variable.trace_add(
                "write",
                lambda *_: self._schedule_auto_analysis(),
            )

    def _schedule_auto_analysis(self) -> None:
        if self.analysis_job is not None:
            self.after_cancel(self.analysis_job)

        self.analysis_job = self.after(
            500,
            self._run_scheduled_analysis,
        )

    def _run_scheduled_analysis(self) -> None:
        self.analysis_job = None

        if self.device is None:
            return

        self.analyze(show_errors=False)

    @staticmethod
    def parse_date(value: str) -> date:
        for format_ in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m"):
            try:
                parsed = datetime.strptime(value.strip(), format_)

                if format_ == "%d/%m":
                    return date(
                        date.today().year,
                        parsed.month,
                        parsed.day,
                    )

                return parsed.date()
            except ValueError:
                continue

        raise ValueError(f"Date invalide : {value}")

    def get_date_range(self) -> tuple[date, date]:
        mode = self.selection_mode.get()

        if not mode:
            raise ValueError("Sélectionnez Date, Période ou Derniers jours.")

        if mode == "date":
            selected = self.parse_date(self.single_date.get())
            return selected, selected

        if mode == "period":
            start = self.parse_date(self.start_date.get())
            end = self.parse_date(self.end_date.get())

            if start > end:
                raise ValueError(
                    "La date de début est postérieure à la date de fin."
                )

            return start, end

        try:
            days = int(self.last_days.get())
        except ValueError as error:
            raise ValueError(
                "Le nombre de jours doit être un entier."
            ) from error

        if days < 1:
            raise ValueError(
                "Le nombre de jours doit être supérieur à zéro."
            )

        end = date.today()
        return end - timedelta(days=days - 1), end

    def open_date_picker(self, target: tk.StringVar) -> None:
        initial_date = None
        current_value = target.get().strip()

        if current_value:
            try:
                initial_date = self.parse_date(current_value)
            except ValueError:
                initial_date = None

        selected = choose_date(self, initial_date)

        if selected is not None:
            target.set(selected.strftime("%d/%m/%Y"))

    def choose_output_directory(self) -> None:
        selected = filedialog.askdirectory(
            initialdir=self.output_directory.get()
        )

        if selected:
            self.output_directory.set(selected)

    def refresh_device(self) -> None:
        self._set_busy(True)
        self.progress_text.set("Recherche du téléphone…")
        self._log("Recherche du téléphone…")

        threading.Thread(
            target=self._refresh_worker,
            daemon=True,
        ).start()

    def _refresh_worker(self) -> None:
        try:
            device = adb_client.select_device(
                self.connection_mode.get()
            )
            self.events.put(("device", device))
        except Exception as error:
            self.events.put(("error", str(error)))
        finally:
            self.events.put(("busy", False))

    def analyze(self, show_errors: bool = True) -> None:
        if self.device is None:
            if show_errors:
                messagebox.showwarning(
                    "Téléphone",
                    "Actualisez d'abord la détection du téléphone.",
                )
            return

        try:
            start, end = self.get_date_range()
        except ValueError as error:
            if show_errors:
                messagebox.showerror("Sélection", str(error))
            return

        self.files = []
        self.download_button.configure(state="disabled")
        self.file_count_text.set("—")
        self.total_size_text.set("—")
        self._set_busy(True)
        self.progress_text.set("Analyse en cours…")
        self._start_loading_indicator()
        self._log(f"Analyse du {start} au {end}…")

        threading.Thread(
            target=self._analyze_worker,
            args=(start, end),
            daemon=True,
        ).start()

    def _analyze_worker(self, start: date, end: date) -> None:
        assert self.device is not None

        try:
            source_files = adb_client.query_camera_files(
                self.device.serial,
                camera_files.PHONE_ROOT,
                start,
                end,
                self.media_mode.get(),
            )

            files = camera_files.build_camera_files(source_files)
            self.events.put(("analysis", files))
        except Exception as error:
            self.events.put(("error", str(error)))
        finally:
            self.events.put(("busy", False))

    def download(self) -> None:
        if self.device is None or not self.files:
            return

        output = Path(self.output_directory.get()).expanduser()

        self.cancel_download_event.clear()
        self.download_running = True
        self._set_busy(True)
        self.cancel_button.configure(state="normal")
        self.progress_value.set(0)
        self.progress_text.set("Téléchargement en cours…")
        self._log(f"Téléchargement vers {output}")

        threading.Thread(
            target=self._download_worker,
            args=(output,),
            daemon=True,
        ).start()

    def cancel_download(self) -> None:
        if not self.download_running:
            return

        self.cancel_download_event.set()
        self.cancel_button.configure(state="disabled")
        self.progress_text.set("Annulation en cours…")
        self._log("Annulation demandée…")

    def _download_worker(self, output: Path) -> None:
        assert self.device is not None

        total_files = len(self.files)
        total_bytes = camera_files.total_size(self.files)
        copied_bytes = 0
        errors = 0

        for index, item in enumerate(self.files, start=1):
            local_path = camera_files.build_local_path(output, item)

            try:
                adb_client.pull_file(
                    self.device.serial,
                    item.remote_path,
                    local_path,
                    self.cancel_download_event,
                )

                copied_bytes += item.size
                self.events.put(
                    ("log", f"[{index}/{total_files}] {item.filename}")
                )
            except InterruptedError:
                self.events.put(("cancelled", index - 1))
                self.events.put(("busy", False))
                return
            except Exception as error:
                errors += 1
                self.events.put(
                    ("log", f"Échec : {item.filename} — {error}")
                )

            percent = (index / total_files) * 100

            self.events.put(
                (
                    "progress",
                    (
                        percent,
                        index,
                        total_files,
                        copied_bytes,
                        total_bytes,
                    ),
                )
            )

        self.events.put(("done", (total_files - errors, errors)))
        self.events.put(("busy", False))

    def _process_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()

                if event == "device":
                    self.device = payload
                    self.device_text.set(
                        f"{self.device.model} — {self.device.serial}"
                    )
                    self.connection_text.set(
                        f"Connexion : {self.device.connection_type}"
                    )
                    self.progress_text.set("Téléphone détecté")
                    self._log(
                        f"Téléphone détecté : "
                        f"{self.device.model} "
                        f"({self.device.connection_type})"
                    )
                    self._schedule_auto_analysis()

                elif event == "analysis":
                    self._stop_loading_indicator()
                    self.files = payload
                    count = len(self.files)
                    size = camera_files.total_size(self.files)

                    self.file_count_text.set(str(count))
                    self.total_size_text.set(self.format_size(size))
                    self.progress_text.set(f"{count} fichier(s) prêt(s)")
                    self.download_button.configure(
                        state="normal" if count else "disabled"
                    )
                    self._log(
                        f"Analyse terminée : {count} fichier(s), "
                        f"{self.format_size(size)}"
                    )

                elif event == "progress":
                    (
                        percent,
                        index,
                        total_files,
                        copied_bytes,
                        total_bytes,
                    ) = payload

                    self.progress_value.set(percent)
                    self.progress_text.set(
                        f"{index}/{total_files} — "
                        f"{self.format_size(copied_bytes)} / "
                        f"{self.format_size(total_bytes)}"
                    )

                elif event == "done":
                    self.download_running = False
                    self.cancel_button.configure(state="disabled")
                    success, errors = payload
                    self.progress_text.set(
                        f"Terminé : {success} téléchargé(s), "
                        f"{errors} erreur(s)"
                    )
                    self._log(self.progress_text.get())

                elif event == "cancelled":
                    self.download_running = False
                    self.cancel_button.configure(state="disabled")
                    completed = int(payload)
                    self.progress_text.set(
                        f"Téléchargement annulé après {completed} fichier(s)."
                    )
                    self._log(self.progress_text.get())

                elif event == "error":
                    self.download_running = False
                    self.cancel_button.configure(state="disabled")
                    self._stop_loading_indicator()
                    self.progress_text.set("Erreur")
                    self._log(str(payload))
                    messagebox.showerror(
                        "Android Camera Fetcher",
                        str(payload),
                    )

                elif event == "log":
                    self._log(str(payload))

                elif event == "busy":
                    self._set_busy(bool(payload))

        except queue.Empty:
            pass

        self.after(100, self._process_events)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"

        self.refresh_button.configure(state=state)
        self.analyze_button.configure(state=state)

        if busy:
            self.download_button.configure(state="disabled")
        elif self.files:
            self.download_button.configure(state="normal")

        if not self.download_running:
            self.cancel_button.configure(state="disabled")

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    @staticmethod
    def format_size(value: int) -> str:
        size = float(value)

        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.2f} {unit}"
            size /= 1024

        return f"{value} B"


if __name__ == "__main__":
    app = AndroidCameraFetcherGUI()
    app.mainloop()
