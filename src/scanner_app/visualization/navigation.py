"""Sidebar navigation definitions for the scanner dashboard."""

from dataclasses import dataclass
from enum import Enum


class DashboardPage(str, Enum):
    NEW_SCAN = "new_scan"
    CAMERA = "camera"
    RESULTS = "results"


@dataclass(frozen=True)
class NavigationItem:
    page: DashboardPage
    title: str
    group: str
    enabled: bool = True


def navigation_items() -> tuple[NavigationItem, ...]:
    return (
        NavigationItem(DashboardPage.NEW_SCAN, "Quét mới", "Làm việc"),
        NavigationItem(DashboardPage.CAMERA, "Camera", "Làm việc"),
        NavigationItem(DashboardPage.RESULTS, "Phiên & kết quả", "Làm việc"),
    )


def default_page() -> DashboardPage:
    return DashboardPage.NEW_SCAN


def is_navigable(page: DashboardPage) -> bool:
    return next(item.enabled for item in navigation_items() if item.page is page)
