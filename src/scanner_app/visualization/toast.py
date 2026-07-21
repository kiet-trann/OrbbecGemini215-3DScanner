"""UI-agnostic timing and presentation for transient in-window toasts."""

from typing import Any


TOAST_STYLES = {
    "info": ("#DBEAFE", "#1E3A8A", 4000),
    "success": ("#DCFCE7", "#166534", 4000),
    "error": ("#FEE2E2", "#991B1B", 6000),
}


class ToastNotifier:
    def __init__(self, root: Any, widget: Any) -> None:
        self._root = root
        self._widget = widget
        self._hide_handle: Any | None = None
        self._generation = 0

    def show(self, message: str, tone: str = "info") -> None:
        if self._hide_handle is not None:
            self._root.after_cancel(self._hide_handle)

        self._generation += 1
        generation = self._generation
        background, foreground, delay_ms = TOAST_STYLES[tone]
        self._widget.configure(text=message, fg_color=background, text_color=foreground)
        self._widget.place(relx=0.975, rely=0.965, anchor="se")
        self._hide_handle = self._root.after(delay_ms, lambda: self._hide_if_current(generation))

    def hide(self) -> None:
        if self._hide_handle is not None:
            self._root.after_cancel(self._hide_handle)
            self._hide_handle = None
        self._generation += 1
        self._widget.place_forget()

    def _hide_if_current(self, generation: int) -> None:
        if generation != self._generation:
            return
        self._hide_handle = None
        self._widget.place_forget()
