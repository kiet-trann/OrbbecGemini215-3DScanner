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


def test_navigation_lists_each_existing_scanner_area_once() -> None:
    items = navigation_items()

    assert [item.page for item in items] == [
        DashboardPage.OVERVIEW,
        DashboardPage.CAMERA,
        DashboardPage.SCAN,
        DashboardPage.SESSIONS,
        DashboardPage.OUTPUTS,
    ]
    assert all(item.enabled for item in items)


def test_dashboard_is_the_default_page() -> None:
    assert default_page() is DashboardPage.OVERVIEW
