"""Coordinate-system normalization for exported and preview meshes."""

import numpy as np


CAMERA_Y_DOWN_TO_Y_UP = np.diag([1.0, -1.0, -1.0, 1.0])


def orient_camera_y_down_mesh_y_up(mesh):
    """Rotate a camera-coordinate mesh into a conventional Y-up orientation."""
    mesh.transform(CAMERA_Y_DOWN_TO_Y_UP.copy())
    return mesh
