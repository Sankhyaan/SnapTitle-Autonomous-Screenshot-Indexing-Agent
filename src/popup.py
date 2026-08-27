"""SnapTitle modern floating Desktop HUD Notification with thumbnail preview, live editing, and animated countdown."""

import os
import sys
import time
import queue
import logging
import threading
from pathlib import Path
from typing import Optional, Callable
try:
    import tkinter as tk
    from tkinter import ttk
    HAS_TKINTER = True
    BasePopupClass = tk.Toplevel
except (ImportError, ModuleNotFoundError):
    tk = None
    ttk = None
    HAS_TKINTER = False
    BasePopupClass = object

from PIL import Image, ImageOps, ImageDraw
try:
    from PIL import ImageTk
except (ImportError, ModuleNotFoundError):
    ImageTk = None

logger = logging.getLogger("snaptitle.popup")


class ScreenshotPopup(BasePopupClass):
    """Floating modern desktop HUD notification for newly detected screenshots."""

    # Curated color palette matching web design system
    BG_DARK = "#07090E"
    CARD_BG = "#0D121F"
    CARD_INNER = "#131B2E"
    INPUT_BG = "#030712"
    BORDER_GLOW = "#06B6D4"
    BORDER_SUBTLE = "#1E293B"
    TEXT_PRIMARY = "#F8FAFC"
    TEXT_SECONDARY = "#94A3B8"
    TEXT_MUTED = "#64748B"
    ACCENT_CYAN = "#06B6D4"
    ACCENT_VIOLET = "#8B5CF6"
    ACCENT_EMERALD = "#10B981"
    ACCENT_AMBER = "#F59E0B"
    ACCENT_ROSE = "#F43F5E"

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
        self._is_hovered = False
        self._thumbnail_photo: Optional[ImageTk.PhotoImage] = None

        # Configure window appearance
        self.title("SnapTitle Notification")
        self.overrideredirect(True)  # Frameless floating card
        self.attributes("-topmost", True)  # Always on top
        self.config(bg=self.BG_DARK)

        self._build_ui()
        self._position_window()

        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._on_confirm_click())
        self.bind("<Escape>", lambda e: self._on_confirm_click())

        # Hover pause/resume interaction
        self.bind("<Enter>", self._on_mouse_enter)
        self.bind("<Leave>", self._on_mouse_leave)

    def _build_ui(self):
        """Construct the ultra-sleek dark-themed popup layout."""
        # Outer luminous gradient border simulation frame
        self.outer_border = tk.Frame(self, bg=self.BORDER_GLOW, padx=1, pady=1)
        self.outer_border.pack(fill="both", expand=True)

        # Main Card Frame
        main_card = tk.Frame(self.outer_border, bg=self.CARD_BG, padx=16, pady=14)
        main_card.pack(fill="both", expand=True)

        # Header: Brand Pill, AI Model Badge, and Close Button
        header_frame = tk.Frame(main_card, bg=self.CARD_BG)
        header_frame.pack(fill="x", pady=(0, 10))

        # Brand icon and title
        brand_group = tk.Frame(header_frame, bg=self.CARD_BG)
        brand_group.pack(side="left")

        brand_pill = tk.Label(
            brand_group,
            text="📸 SnapTitle",
            font=("Segoe UI", 10, "bold"),
            fg=self.TEXT_PRIMARY,
            bg=self.CARD_BG
        )
        brand_pill.pack(side="left")

        # Loading / Status badge
        self.status_badge = tk.Label(
            brand_group,
            text="⚡ Naming...",
            font=("Segoe UI", 8, "bold"),
            fg=self.ACCENT_AMBER,
            bg=self.CARD_INNER,
            padx=8,
            pady=2,
            relief="flat"
        )
        self.status_badge.pack(side="left", padx=(10, 0))

        # Close button (✕) with hover state
        self.close_btn = tk.Label(
            header_frame,
            text="✕",
            font=("Segoe UI", 10, "bold"),
            fg=self.TEXT_MUTED,
            bg=self.CARD_BG,
            cursor="hand2"
        )
        self.close_btn.pack(side="right")
        self.close_btn.bind("<Button-1>", lambda e: self._on_confirm_click())
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.config(fg=self.ACCENT_ROSE))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.config(fg=self.TEXT_MUTED))

        # Middle section: Thumbnail preview + Title input
        content_frame = tk.Frame(main_card, bg=self.CARD_BG)
        content_frame.pack(fill="both", expand=True, pady=(0, 10))

        # Thumbnail Container with crisp glowing border
        thumb_border = tk.Frame(content_frame, bg=self.CARD_INNER, padx=1, pady=1)
        thumb_border.pack(side="left", padx=(0, 14))

        self.thumb_label = tk.Label(thumb_border, bg=self.BG_DARK, relief="flat")
        self.thumb_label.pack()
        self._load_thumbnail()

        # Input & details column
        input_col = tk.Frame(content_frame, bg=self.CARD_BG)
        input_col.pack(side="left", fill="both", expand=True)

        self.input_label = tk.Label(
            input_col,
            text="Target Filename:",
            font=("Segoe UI", 8, "bold"),
            fg=self.TEXT_SECONDARY,
            bg=self.CARD_BG,
            anchor="w"
        )
        self.input_label.pack(fill="x", pady=(0, 3))

        # Input container with dark inset
        entry_border = tk.Frame(input_col, bg=self.BORDER_SUBTLE, padx=1, pady=1)
        entry_border.pack(fill="x", pady=(0, 4))
        self.entry_border = entry_border

        # Editable Title Entry
        self.title_var = tk.StringVar(value="Naming in progress...")
        self.entry = tk.Entry(
            entry_border,
            textvariable=self.title_var,
            font=("Consolas", 9, "bold"),
            bg=self.INPUT_BG,
            fg=self.ACCENT_CYAN,
            insertbackground=self.ACCENT_CYAN,
            relief="flat",
            bd=6
        )
        self.entry.pack(fill="x")
        self.entry.config(state="disabled")

        # Bind user interaction events to stop countdown timer immediately
        self.entry.bind("<Button-1>", self._on_user_started_editing)
        self.entry.bind("<Key>", self._on_user_started_editing)
        self.entry.bind("<FocusIn>", self._on_user_focus)

        # Animated Progress Bar Canvas
        self.progress_canvas = tk.Canvas(
            main_card,
            height=4,
            bg=self.CARD_INNER,
            highlightthickness=0,
            relief="flat"
        )
        self.progress_canvas.pack(fill="x", pady=(0, 10))
        self._progress_bar_rect = self.progress_canvas.create_rectangle(
            0, 0, 380, 4,
            fill=self.ACCENT_CYAN,
            outline=""
        )

        # Bottom row: Countdown timer & Save/Undo buttons
        bottom_frame = tk.Frame(main_card, bg=self.CARD_BG)
        bottom_frame.pack(fill="x")

        self.timer_label = tk.Label(
            bottom_frame,
            text="Waiting for title...",
            font=("Segoe UI", 8),
            fg=self.TEXT_SECONDARY,
            bg=self.CARD_BG
        )
        self.timer_label.pack(side="left")

        actions_group = tk.Frame(bottom_frame, bg=self.CARD_BG)
        actions_group.pack(side="right")

        self.save_btn = tk.Button(
            actions_group,
            text="Save (Enter)",
            font=("Segoe UI", 8, "bold"),
            bg=self.ACCENT_CYAN,
            fg=self.BG_DARK,
            activebackground="#22D3EE",
            activeforeground=self.BG_DARK,
            relief="flat",
            padx=12,
            pady=3,
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
                    img.thumbnail((110, 75), Image.Resampling.LANCZOS)
                    self._thumbnail_photo = ImageTk.PhotoImage(img, master=self)
                    self.thumb_label.config(image=self._thumbnail_photo)
        except Exception as e:
            logger.warning(f"Could not load thumbnail for '{self.image_path}': {e}")
            self.thumb_label.config(text="No Preview", width=12, height=4, fg=self.TEXT_MUTED)

    def _position_window(self):
        """Position the popup in the bottom-right corner above the taskbar."""
        self.update_idletasks()
        popup_width = 400
        popup_height = 175
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

        # Update status badge with bright emerald color
        self.status_badge.config(text="✓ AI Ready", fg=self.ACCENT_EMERALD, bg=self.CARD_INNER)

        # Start 5-second countdown timer (if user hasn't already started typing)
        if not self._is_editing:
            self._remaining_time = float(self.duration_seconds)
            self._start_countdown()

    def _on_mouse_enter(self, event=None):
        """Pause countdown when user hovers mouse over popup to give them time to inspect."""
        if self._timer_running and not self._is_editing and not self._is_closed:
            self._is_hovered = True
            self.timer_label.config(text="⏸ Paused on hover", fg=self.ACCENT_CYAN)

    def _on_mouse_leave(self, event=None):
        """Resume countdown when mouse leaves popup."""
        if self._timer_running and not self._is_editing and not self._is_closed:
            self._is_hovered = False

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

        # Update UI to custom editing mode
        self.input_label.config(text="Custom Title (Editing):", fg=self.ACCENT_AMBER)
        self.entry_border.config(bg=self.ACCENT_AMBER)
        self.timer_label.config(text="✏️ Custom Mode (Timer stopped)", fg=self.ACCENT_AMBER)
        self.status_badge.config(text="✎ Custom Edit", fg=self.ACCENT_AMBER, bg=self.CARD_INNER)
        self.save_btn.config(bg=self.ACCENT_EMERALD, fg=self.BG_DARK, text="Save (Enter)")
        self.progress_canvas.coords(self._progress_bar_rect, 0, 0, 400, 4)
        self.progress_canvas.itemconfig(self._progress_bar_rect, fill=self.ACCENT_AMBER)

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

        # Only decrement time if not hovered
        if not self._is_hovered:
            self.timer_label.config(text=f"Auto-saving in {self._remaining_time:.1f}s...")
            self._remaining_time -= 0.1
            
            # Animate progress bar fill
            ratio = max(0.0, self._remaining_time / float(self.duration_seconds))
            width = int(400 * ratio)
            self.progress_canvas.coords(self._progress_bar_rect, 0, 0, width, 4)

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
        self._task_queue: queue.Queue = queue.Queue()
        self._is_running = False

        self._start_thread()

    def _start_thread(self):
        """Start the background Tkinter GUI event loop thread."""
        self._is_running = True
        self._thread = threading.Thread(target=self._run_tk_loop, daemon=True, name="SnapTitlePopupThread")
        self._thread.start()
        self._ready_event.wait(timeout=5.0)

    def _run_tk_loop(self):
        """Background thread target function hosting the Tk root instance."""
        try:
            self._root = tk.Tk()
            self._root.withdraw()
            self._ready_event.set()

            def process_queue():
                try:
                    while not self._task_queue.empty():
                        fn = self._task_queue.get_nowait()
                        fn()
                except Exception as e:
                    logger.error(f"Error processing task in Tkinter queue: {e}", exc_info=True)
                finally:
                    if self._is_running and self._root:
                        self._root.after(50, process_queue)

            self._root.after(50, process_queue)
            self._root.mainloop()
        except Exception as e:
            logger.error(f"Tkinter mainloop failed: {e}", exc_info=True)
        finally:
            self._is_running = False
            self._ready_event.set()

    def show_popup_and_wait(
        self,
        image_path: Path,
        title_resolver: Callable[[], str],
        duration_seconds: int = 5,
        fallback_title: str = "screenshot"
    ) -> str:
        """Display the floating popup, resolve title in background, and block caller until dismissal.

        Args:
            image_path: Path to screenshot.
            title_resolver: Callable returning the AI generated title.
            duration_seconds: Countdown seconds before auto-dismissal.
            fallback_title: Default title if resolution fails.

        Returns:
            str: The confirmed title string.
        """
        if not self._is_running or not self._root:
            logger.warning("PopupManager GUI thread is not running. Falling back to direct resolution.")
            return title_resolver()

        resolved_title_holder = [fallback_title]
        dismiss_event = threading.Event()
        popup_holder = [None]

        def create_popup():
            def on_confirmed(confirmed_title: str):
                resolved_title_holder[0] = confirmed_title
                dismiss_event.set()

            popup = ScreenshotPopup(
                master=self._root,
                image_path=image_path,
                duration_seconds=duration_seconds,
                on_confirmed=on_confirmed
            )
            popup_holder[0] = popup

        self._task_queue.put(create_popup)

        # Resolve title in background worker thread so UI is never frozen
        def resolve_worker():
            try:
                title = title_resolver()
                if not title:
                    title = fallback_title

                def update_ui():
                    if popup_holder[0]:
                        popup_holder[0].set_title(title)

                self._task_queue.put(update_ui)
            except Exception as e:
                logger.error(f"Error in title resolver worker: {e}")

        worker = threading.Thread(target=resolve_worker, daemon=True)
        worker.start()

        # Wait for popup confirmation/auto-save (with fallback timeout)
        wait_timeout = duration_seconds + 30
        dismiss_event.wait(timeout=wait_timeout)

        return resolved_title_holder[0]

    def shutdown(self):
        """Cleanly close the GUI thread and destroy root window."""
        self._is_running = False
        if self._root:
            try:
                self._root.quit()
            except Exception:
                pass
