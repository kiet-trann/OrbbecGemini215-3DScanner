"""Sidebar navigation definitions for the scanner dashboard."""

from dataclasses import dataclass
from enum import Enum


class DashboardPage(str, Enum):
    OVERVIEW = "overview"
    CAMERA = "camera"
    SCAN = "scan"
    SESSIONS = "sessions"
    OUTPUTS = "outputs"


@dataclass(frozen=True)
class NavigationItem:
    page: DashboardPage
    title: str
    group: str
    enabled: bool = True


def navigation_items() -> tuple[NavigationItem, ...]:
    return (
        NavigationItem(DashboardPage.OVERVIEW, "Overview", "Workspace"),
        NavigationItem(DashboardPage.CAMERA, "Camera setup", "Workspace"),
        NavigationItem(DashboardPage.SCAN, "Scan controls", "Workspace"),
        NavigationItem(DashboardPage.SESSIONS, "Saved sessions", "Models"),
        NavigationItem(DashboardPage.OUTPUTS, "Export & crop", "Models"),
    )


def default_page() -> DashboardPage:
    return DashboardPage.OVERVIEW


def is_navigable(page: DashboardPage) -> bool:
    return next(item.enabled for item in navigation_items() if item.page is page)
