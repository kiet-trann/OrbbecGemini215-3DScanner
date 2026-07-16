import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.processing.mesh_orientation import orient_camera_y_down_mesh_y_up


def test_orientation_converts_camera_y_down_to_y_up_without_reflection() -> None:
    class FakeMesh:
        def __init__(self) -> None:
            self.transform_matrix = None

        def transform(self, matrix) -> None:
            self.transform_matrix = np.asarray(matrix)

    mesh = FakeMesh()

    result = orient_camera_y_down_mesh_y_up(mesh)

    assert result is mesh
    np.testing.assert_allclose(mesh.transform_matrix, np.diag([1.0, -1.0, -1.0, 1.0]))
    assert np.linalg.det(mesh.transform_matrix[:3, :3]) == 1.0
