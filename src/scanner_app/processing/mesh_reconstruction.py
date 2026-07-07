"""Open3D mesh reconstruction helpers for cropped point clouds."""

from collections.abc import Sequence
import copy

import numpy as np
import open3d as o3d


def estimate_point_spacing(cloud: o3d.geometry.PointCloud) -> float:
    distances = np.asarray(cloud.compute_nearest_neighbor_distance(), dtype=np.float64)
    distances = distances[np.isfinite(distances) & (distances > 0)]
    if len(distances) == 0:
        raise ValueError("Cannot estimate point spacing from an empty or degenerate cloud.")
    return float(np.median(distances))


def ball_pivoting_radii(
    cloud: o3d.geometry.PointCloud,
    *,
    base_radius_m: float = 0.0,
    radius_scales: Sequence[float] = (1.5, 2.5, 4.0),
) -> o3d.utility.DoubleVector:
    base_radius = float(base_radius_m) if base_radius_m > 0 else estimate_point_spacing(cloud)
    return o3d.utility.DoubleVector([base_radius * float(scale) for scale in radius_scales])


def prepare_point_cloud_normals(
    cloud: o3d.geometry.PointCloud,
    *,
    normal_radius_m: float = 0.02,
    normal_max_nn: int = 30,
    orient_k: int = 20,
) -> o3d.geometry.PointCloud:
    prepared = copy.deepcopy(cloud)
    prepared.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(
            radius=float(normal_radius_m),
            max_nn=int(normal_max_nn),
        )
    )
    if orient_k > 0 and len(prepared.points) > orient_k:
        prepared.orient_normals_consistent_tangent_plane(int(orient_k))
    return prepared


def reconstruct_mesh(
    cloud: o3d.geometry.PointCloud,
    *,
    method: str = "ball-pivoting",
    normal_radius_m: float = 0.02,
    normal_max_nn: int = 30,
    orient_k: int = 20,
    ball_radius_m: float = 0.0,
    ball_radius_scales: Sequence[float] = (1.5, 2.5, 4.0),
    poisson_depth: int = 8,
    poisson_density_quantile: float = 0.02,
    alpha: float = 0.03,
) -> o3d.geometry.TriangleMesh:
    if len(cloud.points) < 4:
        raise ValueError("Mesh reconstruction requires at least 4 points.")

    prepared = prepare_point_cloud_normals(
        cloud,
        normal_radius_m=normal_radius_m,
        normal_max_nn=normal_max_nn,
        orient_k=orient_k,
    )

    if method == "ball-pivoting":
        radii = ball_pivoting_radii(
            prepared,
            base_radius_m=ball_radius_m,
            radius_scales=ball_radius_scales,
        )
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(prepared, radii)
    elif method == "poisson":
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            prepared,
            depth=int(poisson_depth),
        )
        mesh = remove_low_density_vertices(mesh, densities, quantile=poisson_density_quantile)
    elif method == "alpha":
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(prepared, float(alpha))
    else:
        raise ValueError(f"Unknown reconstruction method: {method}")

    cleanup_mesh(mesh)
    if len(mesh.triangles) == 0:
        raise ValueError(
            "Mesh reconstruction produced 0 triangles. Try another method or adjust radius/alpha."
        )
    return mesh


def remove_low_density_vertices(
    mesh: o3d.geometry.TriangleMesh,
    densities,
    *,
    quantile: float = 0.02,
) -> o3d.geometry.TriangleMesh:
    if quantile <= 0:
        return mesh
    density_values = np.asarray(densities, dtype=np.float64)
    if len(density_values) == 0:
        return mesh
    threshold = np.quantile(density_values, float(quantile))
    mesh.remove_vertices_by_mask(density_values < threshold)
    return mesh


def cleanup_mesh(mesh: o3d.geometry.TriangleMesh) -> None:
    mesh.remove_duplicated_vertices()
    mesh.remove_duplicated_triangles()
    mesh.remove_degenerate_triangles()
    mesh.remove_non_manifold_edges()
    mesh.compute_vertex_normals()


def describe_mesh(mesh: o3d.geometry.TriangleMesh) -> str:
    return f"vertices={len(mesh.vertices)} | triangles={len(mesh.triangles)}"
