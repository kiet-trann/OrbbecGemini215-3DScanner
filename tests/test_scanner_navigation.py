# ruff: noqa: E402

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.navigation import (
    DashboardPage,
    default_page,
    navigation_items,
)


def test_navigation_lists_the_four_guided_workspace_routes() -> None:
    items = navigation_items()

    assert [(item.page, item.title, item.group, item.enabled) for item in items] == [
        (DashboardPage.NEW_SCAN, "Quét mới", "Làm việc", True),
        (DashboardPage.CAMERA, "Camera", "Làm việc", True),
        (DashboardPage.RESULTS, "Phiên & kết quả", "Làm việc", True),
        (DashboardPage.ADVANCED, "Công cụ nâng cao", "Làm việc", True),
    ]


def test_new_scan_is_the_default_page() -> None:
    assert default_page() is DashboardPage.NEW_SCAN
