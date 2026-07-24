"""Tkinter GUI tying the EDGAR scraper, Excel dashboard, and prompt builder
together.

Network work runs on a worker thread; all widget updates are marshalled back to
the Tk main thread via ``root.after`` so the UI stays responsive.
"""

from __future__ import annotations

import os
import queue
import threading
import traceback
from datetime import date, datetime
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .dashboard import build_workbook
from .edgar_client import CompanyMatch, EdgarClient, EdgarError
from .filings import Filing, select_filings
from .financials import extract_figures
from .prompt_builder import build_prompt
from .sections import Section, extract_sections

DEFAULT_EMAIL = "rzeminski16@gmail.com"
SECTION_FORMS = ("10-K", "10-Q")  # forms we extract selectable sections from


class FinanceScrapeApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("FinanceScrape — SEC EDGAR Dashboard")
        root.geometry("900x680")

        self._ui_queue: "queue.Queue" = queue.Queue()
        self.sections_by_form: dict[str, list[Section]] = {}
        self._section_vars: list[tuple[str, Section, tk.BooleanVar]] = []
        self.company_name: str = ""
        self.workbook_path: Optional[str] = None

        self._build_ui()
        self.root.after(100, self._pump_ui_queue)

    # -- UI construction --------------------------------------------------

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_fetch = ttk.Frame(notebook)
        self.tab_prompt = ttk.Frame(notebook)
        notebook.add(self.tab_fetch, text="1. Fetch & Dashboard")
        notebook.add(self.tab_prompt, text="2. Analysis Prompt")

        self._build_fetch_tab(self.tab_fetch)
        self._build_prompt_tab(self.tab_prompt)

    def _build_fetch_tab(self, parent: ttk.Frame) -> None:
        form = ttk.Frame(parent)
        form.pack(fill="x", padx=10, pady=10)

        ttk.Label(form, text="Ticker or company name:").grid(row=0, column=0, sticky="w", pady=4)
        self.query_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.query_var, width=32).grid(row=0, column=1, sticky="w")

        ttk.Label(form, text="Cutoff date (YYYY-MM-DD):").grid(row=1, column=0, sticky="w", pady=4)
        self.date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(form, textvariable=self.date_var, width=32).grid(row=1, column=1, sticky="w")

        ttk.Label(form, text="Contact email (SEC User-Agent):").grid(row=2, column=0, sticky="w", pady=4)
        self.email_var = tk.StringVar(value=DEFAULT_EMAIL)
        ttk.Entry(form, textvariable=self.email_var, width=32).grid(row=2, column=1, sticky="w")

        ttk.Label(form, text="Save dashboard to:").grid(row=3, column=0, sticky="w", pady=4)
        self.outpath_var = tk.StringVar(value=os.path.join(os.getcwd(), "dashboard.xlsx"))
        ttk.Entry(form, textvariable=self.outpath_var, width=32).grid(row=3, column=1, sticky="w")
        ttk.Button(form, text="Browse…", command=self._choose_output).grid(row=3, column=2, padx=4)

        self.fetch_btn = ttk.Button(form, text="Fetch filings & build dashboard",
                                    command=self._on_fetch)
        self.fetch_btn.grid(row=4, column=0, columnspan=2, sticky="w", pady=10)

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(parent, textvariable=self.status_var, foreground="#1F4E78").pack(anchor="w", padx=10)

        log_frame = ttk.LabelFrame(parent, text="Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=8)
        self.log = tk.Text(log_frame, height=16, wrap="word", state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        log_scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=log_scroll.set)

    def _build_prompt_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(
            top,
            text="Select sections from the 10-K / 10-Q to include in the ChatGPT prompt:",
        ).pack(anchor="w")

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True, padx=10)

        canvas = tk.Canvas(list_frame, height=180)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.sections_inner = ttk.Frame(canvas)
        self.sections_inner.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.sections_inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._sections_placeholder()

        btns = ttk.Frame(parent)
        btns.pack(fill="x", padx=10, pady=6)
        ttk.Button(btns, text="Build prompt", command=self._on_build_prompt).pack(side="left")
        ttk.Button(btns, text="Copy", command=self._copy_prompt).pack(side="left", padx=4)
        ttk.Button(btns, text="Save .txt…", command=self._save_prompt).pack(side="left")

        out_frame = ttk.LabelFrame(parent, text="Prompt")
        out_frame.pack(fill="both", expand=True, padx=10, pady=8)
        self.prompt_text = tk.Text(out_frame, wrap="word")
        self.prompt_text.pack(side="left", fill="both", expand=True)
        p_scroll = ttk.Scrollbar(out_frame, command=self.prompt_text.yview)
        p_scroll.pack(side="right", fill="y")
        self.prompt_text.configure(yscrollcommand=p_scroll.set)

    def _sections_placeholder(self) -> None:
        for child in self.sections_inner.winfo_children():
            child.destroy()
        ttk.Label(
            self.sections_inner,
            text="(Fetch a company first — sections will appear here.)",
            foreground="#808080",
        ).pack(anchor="w")

    # -- helpers ----------------------------------------------------------

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile="dashboard.xlsx",
        )
        if path:
            self.outpath_var.set(path)

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _pump_ui_queue(self) -> None:
        """Run callables posted by the worker thread on the Tk main thread."""
        try:
            while True:
                func = self._ui_queue.get_nowait()
                func()
        except queue.Empty:
            pass
        self.root.after(100, self._pump_ui_queue)

    def _post(self, func) -> None:
        self._ui_queue.put(func)

    # -- fetch workflow ---------------------------------------------------

    def _on_fetch(self) -> None:
        query = self.query_var.get().strip()
        email = self.email_var.get().strip()
        out_path = self.outpath_var.get().strip()
        if not query:
            messagebox.showwarning("Missing input", "Enter a ticker or company name.")
            return
        try:
            cutoff = datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d").date()
        except ValueError:
            messagebox.showwarning("Invalid date", "Use the format YYYY-MM-DD.")
            return
        if not out_path:
            messagebox.showwarning("Missing output", "Choose where to save the dashboard.")
            return

        self.fetch_btn.configure(state="disabled")
        self._set_status("Working…")
        threading.Thread(
            target=self._fetch_worker, args=(query, cutoff, email, out_path), daemon=True
        ).start()

    def _fetch_worker(self, query: str, cutoff: date, email: str, out_path: str) -> None:
        try:
            client = EdgarClient(email)

            self._post(lambda: self._log(f"Resolving '{query}'…"))
            matches = client.resolve_company(query)
            company = self._select_company(matches)
            if company is None:
                self._post(lambda: self._log("Cancelled."))
                return
            self.company_name = company.name
            self._post(lambda: self._log(
                f"→ {company.name} (ticker {company.ticker}, CIK {company.cik})"))

            self._post(lambda: self._log("Downloading filing history…"))
            submissions = client.get_submissions(company.cik)
            filings = select_filings(submissions, cutoff)
            for form, filing in filings.items():
                msg = (f"  {form}: {filing.filing_date} ({filing.accession_number})"
                       if filing else f"  {form}: none on or before {cutoff}")
                self._post(lambda m=msg: self._log(m))

            self._post(lambda: self._log("Downloading XBRL company facts…"))
            facts = client.get_company_facts(company.cik)
            figures = extract_figures(facts, cutoff)
            self._post(lambda: self._log(f"Extracted {len(figures)} figures."))

            build_workbook(
                out_path, company.name, company.ticker, company.cik, cutoff, figures, filings
            )
            self.workbook_path = out_path
            self._post(lambda: self._log(f"Saved dashboard → {out_path}"))

            self._post(lambda: self._log("Extracting sections from 10-K / 10-Q…"))
            sections_by_form: dict[str, list[Section]] = {}
            for form in SECTION_FORMS:
                filing = filings.get(form)
                if not filing:
                    continue
                try:
                    html = client.get_document_text(filing.document_url)
                    secs = extract_sections(html)
                    if secs:
                        sections_by_form[form] = secs
                        self._post(lambda f=form, n=len(secs):
                                   self._log(f"  {f}: {n} sections"))
                except EdgarError as exc:
                    self._post(lambda f=form, e=exc:
                               self._log(f"  {f}: could not fetch document ({e})"))

            self.sections_by_form = sections_by_form
            self._post(self._populate_sections)
            self._post(lambda: self._finish(f"Done. Dashboard saved to {out_path}"))
        except (EdgarError, ValueError) as exc:
            self._post(lambda e=exc: self._fail(str(e)))
        except Exception as exc:  # unexpected
            tb = traceback.format_exc()
            self._post(lambda e=exc, t=tb: self._fail(f"{e}\n\n{t}"))

    def _finish(self, message: str) -> None:
        self._set_status(message)
        self.fetch_btn.configure(state="normal")

    def _fail(self, message: str) -> None:
        self._set_status("Error.")
        self._log("ERROR: " + message)
        self.fetch_btn.configure(state="normal")
        messagebox.showerror("FinanceScrape", message)

    def _select_company(self, matches: list[CompanyMatch]) -> Optional[CompanyMatch]:
        """Choose a company, prompting on the main thread if ambiguous."""
        if len(matches) == 1:
            return matches[0]

        result: "queue.Queue" = queue.Queue(maxsize=1)

        def ask() -> None:
            result.put(self._disambiguation_dialog(matches[:50]))

        self._post(ask)
        return result.get()

    def _disambiguation_dialog(self, matches: list[CompanyMatch]) -> Optional[CompanyMatch]:
        dialog = tk.Toplevel(self.root)
        dialog.title("Select company")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="Multiple matches — pick one:").pack(padx=10, pady=6)

        listbox = tk.Listbox(dialog, width=60, height=min(15, len(matches)))
        for m in matches:
            label = f"{m.ticker or '—':<8} {m.name}"
            listbox.insert("end", label)
        listbox.pack(padx=10, pady=6)
        listbox.selection_set(0)

        chosen: dict[str, Optional[CompanyMatch]] = {"value": None}

        def confirm() -> None:
            sel = listbox.curselection()
            if sel:
                chosen["value"] = matches[sel[0]]
            dialog.destroy()

        ttk.Button(dialog, text="OK", command=confirm).pack(pady=6)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.root.wait_window(dialog)
        return chosen["value"]

    # -- sections & prompt ------------------------------------------------

    def _populate_sections(self) -> None:
        for child in self.sections_inner.winfo_children():
            child.destroy()
        self._section_vars = []

        if not self.sections_by_form:
            ttk.Label(
                self.sections_inner,
                text="(No 10-K/10-Q sections available for this company/date.)",
                foreground="#808080",
            ).pack(anchor="w")
            return

        for form in SECTION_FORMS:
            secs = self.sections_by_form.get(form)
            if not secs:
                continue
            ttk.Label(self.sections_inner, text=form, font=("TkDefaultFont", 10, "bold")).pack(
                anchor="w", pady=(6, 0)
            )
            for section in secs:
                var = tk.BooleanVar(value=False)
                text = section.title
                if section.preview:
                    text = f"{section.title}  —  {section.preview}"
                ttk.Checkbutton(self.sections_inner, text=text, variable=var).pack(
                    anchor="w", padx=12
                )
                self._section_vars.append((form, section, var))

    def _on_build_prompt(self) -> None:
        selected: list[Section] = []
        for form, section, var in self._section_vars:
            if var.get():
                selected.append(Section(f"[{form}] {section.title}", section.text))
        if not selected:
            messagebox.showinfo("No selection", "Tick at least one section.")
            return
        prompt = build_prompt(self.company_name, selected)
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", prompt)

    def _copy_prompt(self) -> None:
        text = self.prompt_text.get("1.0", "end").strip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status("Prompt copied to clipboard.")

    def _save_prompt(self) -> None:
        text = self.prompt_text.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Nothing to save", "Build a prompt first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt")],
            initialfile="chatgpt_prompt.txt",
        )
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            self._set_status(f"Prompt saved to {path}")


def run() -> None:
    root = tk.Tk()
    FinanceScrapeApp(root)
    root.mainloop()
