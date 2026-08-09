from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk


class DatePickerDialog(tk.Toplevel):
    MONTHS = (
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
    )
    DAYS = ("Lu", "Ma", "Me", "Je", "Ve", "Sa", "Di")

    def __init__(
        self,
        parent: tk.Misc,
        initial_date: date | None = None,
    ) -> None:
        super().__init__(parent)

        selected = initial_date or date.today()
        self.year = selected.year
        self.month = selected.month
        self.result: date | None = None

        self.title("Choisir une date")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.header_text = tk.StringVar()

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")

        ttk.Button(
            header,
            text="◀",
            width=3,
            command=self._previous_month,
        ).pack(side="left")

        ttk.Label(
            header,
            textvariable=self.header_text,
            anchor="center",
            font=("", 10, "bold"),
        ).pack(side="left", fill="x", expand=True, padx=8)

        ttk.Button(
            header,
            text="▶",
            width=3,
            command=self._next_month,
        ).pack(side="right")

        self.calendar_frame = ttk.Frame(outer)
        self.calendar_frame.pack(pady=(10, 6))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(4, 0))

        ttk.Button(
            footer,
            text="Aujourd'hui",
            command=self._select_today,
        ).pack(side="left")

        ttk.Button(
            footer,
            text="Annuler",
            command=self.destroy,
        ).pack(side="right")

        self.bind("<Escape>", lambda _event: self.destroy())
        self._render()

        self.update_idletasks()
        x = parent.winfo_rootx() + max(
            0,
            (parent.winfo_width() - self.winfo_width()) // 2,
        )
        y = parent.winfo_rooty() + max(
            0,
            (parent.winfo_height() - self.winfo_height()) // 2,
        )
        self.geometry(f"+{x}+{y}")

    def _render(self) -> None:
        for child in self.calendar_frame.winfo_children():
            child.destroy()

        self.header_text.set(
            f"{self.MONTHS[self.month - 1]} {self.year}"
        )

        for column, day_name in enumerate(self.DAYS):
            ttk.Label(
                self.calendar_frame,
                text=day_name,
                anchor="center",
                width=4,
            ).grid(row=0, column=column, padx=1, pady=1)

        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(
            self.year,
            self.month,
        )

        today = date.today()

        for row, week in enumerate(weeks, start=1):
            for column, day_number in enumerate(week):
                if day_number == 0:
                    ttk.Label(
                        self.calendar_frame,
                        text="",
                        width=4,
                    ).grid(row=row, column=column, padx=1, pady=1)
                    continue

                button = ttk.Button(
                    self.calendar_frame,
                    text=str(day_number),
                    width=4,
                    command=lambda day=day_number: self._select_day(day),
                )
                button.grid(row=row, column=column, padx=1, pady=1)

                if (
                    self.year == today.year
                    and self.month == today.month
                    and day_number == today.day
                ):
                    button.state(["focus"])

    def _previous_month(self) -> None:
        self.month -= 1

        if self.month == 0:
            self.month = 12
            self.year -= 1

        self._render()

    def _next_month(self) -> None:
        self.month += 1

        if self.month == 13:
            self.month = 1
            self.year += 1

        self._render()

    def _select_day(self, day_number: int) -> None:
        self.result = date(
            self.year,
            self.month,
            day_number,
        )
        self.destroy()

    def _select_today(self) -> None:
        self.result = date.today()
        self.destroy()


def choose_date(
    parent: tk.Misc,
    initial_date: date | None = None,
) -> date | None:
    dialog = DatePickerDialog(parent, initial_date)
    parent.wait_window(dialog)
    return dialog.result
