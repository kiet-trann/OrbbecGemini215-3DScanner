try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.toast import ToastNotifier  # noqa: E402


class FakeRoot:
    def __init__(self) -> None:
        self.scheduled: dict[str, tuple[int, object]] = {}
        self.cancelled: list[str] = []
        self._next_handle = 0

    def after(self, delay_ms: int, callback: object) -> str:
        self._next_handle += 1
        handle = f"after-{self._next_handle}"
        self.scheduled[handle] = (delay_ms, callback)
        return handle

    def after_cancel(self, handle: str) -> None:
        self.cancelled.append(handle)


class FakeWidget:
    def __init__(self) -> None:
        self.configurations: list[dict[str, str]] = []
        self.placements: list[dict[str, object]] = []
        self.forget_count = 0

    def configure(self, **kwargs: str) -> None:
        self.configurations.append(kwargs)

    def place(self, **kwargs: object) -> None:
        self.placements.append(kwargs)

    def place_forget(self) -> None:
        self.forget_count += 1


def test_success_toast_displays_message_and_schedules_four_seconds() -> None:
    root = FakeRoot()
    widget = FakeWidget()

    ToastNotifier(root, widget).show("Saved", tone="success")

    assert widget.configurations == [
        {"text": "Saved", "fg_color": "#DCFCE7", "text_color": "#166534"}
    ]
    assert widget.placements == [{"relx": 0.975, "rely": 0.965, "anchor": "se"}]
    assert root.scheduled["after-1"][0] == 4000


def test_error_toast_schedules_six_seconds() -> None:
    root = FakeRoot()
    widget = FakeWidget()

    ToastNotifier(root, widget).show("Failed", tone="error")

    assert widget.configurations[-1]["fg_color"] == "#FEE2E2"
    assert root.scheduled["after-1"][0] == 6000


def test_replacement_cancels_prior_callback_and_stale_callback_cannot_hide_it() -> None:
    root = FakeRoot()
    widget = FakeWidget()
    notifier = ToastNotifier(root, widget)
    notifier.show("First")
    stale_callback = root.scheduled["after-1"][1]

    notifier.show("Second")
    stale_callback()

    assert root.cancelled == ["after-1"]
    assert widget.configurations[-1]["text"] == "Second"
    assert widget.forget_count == 0
