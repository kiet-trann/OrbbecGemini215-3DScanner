"""Light card-dashboard presentation primitives."""

from dataclasses import dataclass

NAVY = "#163B5C"
SURFACE = "#F5F7FA"
CARD = "#FFFFFF"
BORDER = "#DEE5ED"
PRIMARY = "#2563EB"


@dataclass(frozen=True)
class DashboardStatus:
    label: str
    tone: str


def dashboard_status(message: str) -> DashboardStatus:
    if "No Orbbec camera" in message or "failed" in message.lower() or "error" in message.lower():
        return DashboardStatus(message, "error")
    if message == "RTAB-Map is running":
        return DashboardStatus("Đang quét", "ready")
    if message == "RTAB-Map is not running":
        return DashboardStatus("Sẵn sàng chuẩn bị", "neutral")
    return DashboardStatus(message, "neutral")


def configure_dashboard_theme(root) -> None:
    import customtkinter as ctk

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    root.configure(fg_color=SURFACE)


def card(parent):
    import customtkinter as ctk

    return ctk.CTkFrame(parent, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=12)
