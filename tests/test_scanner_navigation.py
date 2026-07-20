# ruff: noqa: E402

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.navigation import (
    DashboardPage,
    default_page,
    is_navigable,
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
        DashboardPage.SETTINGS,
    ]
    assert [item.enabled for item in items] == [True, True, True, True, True, False]


def test_dashboard_is_the_default_and_settings_is_reserved() -> None:
    assert default_page() is DashboardPage.OVERVIEW
    assert is_navigable(DashboardPage.OVERVIEW)
    assert not is_navigable(DashboardPage.SETTINGS)
