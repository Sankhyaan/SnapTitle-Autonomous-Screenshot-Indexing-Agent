"""SnapTitle non-blocking floating Popup UI with thumbnail preview, live editing, and countdown timer."""

import os
import sys
import time
import queue
import logging
import threading
from pathlib import Path
from typing import Optional, Callable
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageOps

logger = logging.getLogger("snaptitle.popup")


class ScreenshotPopup(tk.Toplevel):
    """Floating desktop notification popup window for newly detected screenshots."""

    def __init__(
        self,
        master: tk.Tk,
        image_path: Path,
        duration_seconds: int = 5,
        on_confirmed: Optional[Callable[[str], None]] = None
    ):
        super().__init__(master)
        self.image_path = Path(image_path)
        self.duration_seconds = duration_seconds
        self.on_confirmed = on_confirmed
        
        self.final_title: Optional[str] = None
        self._remaining_time = float(duration_seconds)
        self._timer_running = False
        self._timer_job = None
        self._is_closed = False
        self._is_editing = False
        self._thumbnail_photo: Optional[ImageTk.PhotoImage] = None

        # Configure window appearance
        self.title("SnapTitle Notification")
        self.overrideredirect(True)  # Frameless floating card
        self.attributes("-topmost", True)  # Always on top
        self.config(bg="#181825")  # Modern dark background

        self._build_ui()
        self._position_window()

        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._on_confirm_click())
        self.bind("<Escape>", lambda e: self._on_confirm_click())

    def _build_ui(self):
        """Construct the modern dark-themed popup layout."""
        # Outer border frame
        outer_frame = tk.Frame(self, bg="#313244", padx=1, pady=1)
        outer_frame.pack(fill="both", expand=True)

        main_card = tk.Frame(outer_frame, bg="#1e1e2e", padx=14, pady=12)
        main_card.pack(fill="both", expand=True)

        # Header: App brand and close button
        header_frame = tk.Frame(main_card, bg="#1e1e2e")
        header_frame.pack(fill="x", pady=(0, 8))

        app_title = tk.Label(
            header_frame,
            text="✨ SnapTitle",
            font=("Segoe UI", 10, "bold"),
            fg="#cdd6f4",
            bg="#1e1e2e"
        )
        app_title.pack(side="left")

        # Loading / Status badge
        self.status_badge = tk.Label(
            header_frame,
            text="⚡ Naming...",
            font=("Segoe UI", 8, "bold"),
            fg="#f9e2af",
            bg="#313244",
            padx=6,
            pady=1
        )
        self.status_badge.pack(side="left", padx=(10, 0))

        # Close button (✕)
        close_btn = tk.Label(
            header_frame,
            text="✕",
            font=("Segoe UI", 10, "bold"),
            fg="#a6adc8",
            bg="#1e1e2e",
            cursor="hand2"
        )
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self._on_confirm_click())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg="#f38ba8"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg="#a6adc8"))

        # Middle section: Thumbnail preview + Title input
        content_frame = tk.Frame(main_card, bg="#1e1e2e")
        content_frame.pack(fill="both", expand=True, pady=(0, 10))

        # Thumbnail
        self.thumb_label = tk.Label(content_frame, bg="#181825", relief="solid", bd=1)
        self.thumb_label.pack(side="left", padx=(0, 12))
        self._load_thumbnail()

        # Input & details column
        input_col = tk.Frame(content_frame, bg="#1e1e2e")
        input_col.pack(side="left", fill="both", expand=True)

        input_label = tk.Label(
            input_col,
            text="Screenshot Title:",
            font=("Segoe UI", 8),
            fg="#a6adc8",
            bg="#1e1e2e",
            anchor="w"
        )
        input_label.pack(fill="x", pady=(0, 2))

        # Editable Title Entry
        self.title_var = tk.StringVar(value="Naming in progress...")
        self.entry = tk.Entry(
            input_col,
            textvariable=self.title_var,
            font=("Segoe UI", 10),
            bg="#313244",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat",
            bd=5
        )
        self.entry.pack(fill="x", pady=(0, 4))
        self.entry.config(state="disabled")

        # Bind user interaction events to stop countdown timer immediately
        self.entry.bind("<Button-1>", self._on_user_started_editing)
        self.entry.bind("<Key>", self._on_user_started_editing)
        self.entry.bind("<FocusIn>", self._on_user_focus)

        # Bottom row: Countdown timer & Save button
        bottom_frame = tk.Frame(main_card, bg="#1e1e2e")
        bottom_frame.pack(fill="x")

        self.timer_label = tk.Label(
            bottom_frame,
            text="Waiting for title...",
            font=("Segoe UI", 8),
            fg="#89b4fa",
            bg="#1e1e2e"
        )
        self.timer_label.pack(side="left")

        self.save_btn = tk.Button(
            bottom_frame,
            text="Save (Enter)",
            font=("Segoe UI", 8, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            activeforeground="#11111b",
            relief="flat",
            padx=10,
            pady=2,
            cursor="hand2",
            command=self._on_confirm_click
        )
        self.save_btn.pack(side="right")

    def _load_thumbnail(self):
        """Create and display an aspect-ratio preserving thumbnail of the screenshot."""
        try:
            if self.image_path.exists():
                with Image.open(self.image_path) as img:
                    img = img.convert("RGB")
                    img.thumbnail((120, 80), Image.Resampling.LANCZOS)
                    self._thumbnail_photo = ImageTk.PhotoImage(img, master=self)
                    self.thumb_label.config(image=self._thumbnail_photo)
        except Exception as e:
            logger.warning(f"Could not load thumbnail for '{self.image_path}': {e}")
            self.thumb_label.config(text="No Preview", width=12, height=4, fg="#a6adc8")

    def _position_window(self):
        """Position the popup in the bottom-right corner above the taskbar."""
        self.update_idletasks()
        popup_width = 380
        popup_height = 160
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        # Position bottom-right with 24px right padding and 60px bottom padding
        x = screen_width - popup_width - 24
        y = screen_height - popup_height - 60

        self.geometry(f"{popup_width}x{popup_height}+{x}+{y}")

    def set_title(self, generated_title: str):
        """Update the popup from loading state to ready with the generated AI title, and start countdown."""
        if self._is_closed:
            return

        self.title_var.set(generated_title)
        self.entry.config(state="normal")

        # Update status badge
        self.status_badge.config(text="✓ AI Ready", fg="#a6e3a1", bg="#313244")

        # Start 5-second countdown timer (if user hasn't already started typing)
        if not self._is_editing:
            self._remaining_time = float(self.duration_seconds)
            self._start_countdown()

    def _on_user_focus(self, event=None):
        """Handle focus on the text box."""
        if str(self.entry.cget("state")) == "normal" and not self._is_closed:
            self._on_user_started_editing(event)

    def _on_user_started_editing(self, event=None):
        """Pause/stop the countdown timer permanently when the user clicks or types in the title box."""
        if self._is_closed or str(self.entry.cget("state")) != "normal":
            return

        self._is_editing = True
        self._timer_running = False

        if self._timer_job:
            try:
                self.after_cancel(self._timer_job)
                self._timer_job = None
            except Exception:
                pass

        # Update labels to clearly indicate editing mode without auto-dismiss
        self.timer_label.config(text="✏️ Editing mode (timer stopped)", fg="#f9e2af")
        self.status_badge.config(text="✎ Custom Edit", fg="#f9e2af", bg="#313244")
        self.save_btn.config(bg="#a6e3a1", text="Save (Enter)")

    def _start_countdown(self):
        """Begin counting down to auto-dismiss."""
        self._timer_running = True
        self._tick_timer()

    def _tick_timer(self):
        """Timer tick every 100ms for a smooth countdown experience."""
        if not self._timer_running or self._is_closed or self._is_editing:
            return

        if self._remaining_time <= 0:
            self._on_confirm_click()
            return

        self.timer_label.config(text=f"Auto-saving in {int(self._remaining_time + 0.9)}s...")
        self._remaining_time -= 0.1
        self._timer_job = self.after(100, self._tick_timer)

    def _on_confirm_click(self):
        """Handle user confirmation, early close, or timer expiration."""
        if self._is_closed:
            return
        self._is_closed = True
        self._timer_running = False

        if self._timer_job:
            try:
                self.after_cancel(self._timer_job)
                self._timer_job = None
            except Exception:
                pass

        # Retrieve edited or current title text
        raw_text = self.title_var.get().strip()
        if not raw_text or raw_text == "Naming in progress...":
            raw_text = "screenshot"

        self.final_title = raw_text
        logger.info(f"Popup confirmed with title: '{self.final_title}'")

        if self.on_confirmed:
            try:
                self.on_confirmed(self.final_title)
            except Exception as e:
                logger.error(f"Error in on_confirmed callback: {e}", exc_info=True)

        try:
            self.destroy()
        except Exception:
            pass


class PopupManager:
    """Thread-safe manager running the Tkinter mainloop on a dedicated UI background thread."""

    def __init__(self):
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._ready_event = threading.Event()
        self._active_popup: Optional[ScreenshotPopup] = None
        self._lock = threading.Lock()
        self._start_ui_thread()

    def _start_ui_thread(self):
        """Initialize Tkinter instance in background thread."""
        def ui_loop():
            try:
                self._root = tk.Tk()
                self._root.withdraw()  # Hide root master window
                self._ready_event.set()
                self._root.mainloop()
            except Exception as e:
                logger.error(f"Tkinter mainloop encountered error: {e}", exc_info=True)

        self._thread = threading.Thread(target=ui_loop, daemon=True, name="SnapTitle-UI")
        self._thread.start()
        self._ready_event.wait(timeout=3.0)

    def show_popup_and_wait(
        self,
        image_path: Path,
        title_resolver: Callable[[], str],
        duration_seconds: int = 5,
        fallback_title: str = "screenshot"
    ) -> str:
        """Display popup in loading state, resolve title in background, and wait for user confirm/timeout.

        Args:
            image_path: Path to the screenshot file.
            title_resolver: Function that executes OCR/VLM/LLM to generate title.
            duration_seconds: Duration before auto-save countdown dismisses (default: 5).
            fallback_title: Fallback title if resolution fails.

        Returns:
            str: Final title (either AI generated or edited by user).
        """
        if not self._root:
            logger.warning("Tkinter root not ready. Running direct resolution without popup.")
            try:
                return title_resolver()
            except Exception:
                return fallback_title

        result_queue: queue.Queue[str] = queue.Queue(maxsize=1)
        popup_ref: list[Optional[ScreenshotPopup]] = [None]

        def create_popup():
            try:
                popup = ScreenshotPopup(
                    master=self._root,
                    image_path=image_path,
                    duration_seconds=duration_seconds,
                    on_confirmed=lambda title: result_queue.put(title)
                )
                popup_ref[0] = popup
                self._active_popup = popup
            except Exception as e:
                logger.error(f"Failed to create popup: {e}", exc_info=True)
                result_queue.put(fallback_title)

        # 1. Schedule popup creation on Tkinter thread
        self._root.after(0, create_popup)

        # 2. Resolve title in current worker thread (OCR / LLM / VLM)
        generated_title = fallback_title
        try:
            generated_title = title_resolver() or fallback_title
        except Exception as e:
            logger.error(f"Title resolution failed: {e}", exc_info=True)
            generated_title = fallback_title

        # 3. Update popup with resolved title and start timer
        def update_popup_title():
            if popup_ref[0] and not popup_ref[0]._is_closed:
                popup_ref[0].set_title(generated_title)

        self._root.after(0, update_popup_title)

        # 4. Wait for user edit, early close, or countdown timer expiration
        # If user edits, window stays open until they click Save, so we allow generous wait time
        try:
            final_title = result_queue.get(timeout=600.0)  # Up to 10 minutes for manual editing
            return final_title
        except queue.Empty:
            logger.warning("Popup timed out without response. Using generated title.")
            if popup_ref[0]:
                self._root.after(0, popup_ref[0]._on_confirm_click)
            return generated_title
