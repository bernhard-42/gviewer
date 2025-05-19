import numpy as np
from numba import njit
from collections import defaultdict
import plotly.graph_objects as go

from shapely.geometry import Polygon
from shapely import set_precision, normalize, get_coordinates

import distinctipy

# ---------------------------
# 1. Core Congruence Detection
# ---------------------------

MAP_ALL = [0, 1, 2, 3, 4, 5, 6, 7]
MAP_SQUARE = [0]
MAP_RECTANGLE = [0, 1]


def is_axis_aligned_rectangle_or_square(points, tol=1e-8):
    xs = points[:, 0]
    ys = points[:, 1]
    x_unique = np.unique(xs)
    y_unique = np.unique(ys)

    if len(x_unique) != 2 or len(y_unique) != 2:
        return False, False  # Not a rectangle or square

    # Generate all 4 possible corner combinations
    corners = np.array([[x, y] for x in x_unique for y in y_unique])

    # Check if all input points are among these corners (allowing for floating point tolerance)
    matches = [
        np.any(np.all(np.isclose(pt, corners, atol=tol), axis=1)) for pt in points
    ]
    if not all(matches):
        return False, False

    # Check for square: side lengths must be equal
    side_x = abs(x_unique[1] - x_unique[0])
    side_y = abs(y_unique[1] - y_unique[0])
    is_square = np.isclose(side_x, side_y, atol=tol)

    return True, is_square


@njit
def is_rectangle_or_square(points, tol=1e-8):
    # Compute all pairwise distances
    dists = [
        np.linalg.norm(points[i] - points[j]) for i in range(4) for j in range(i + 1, 4)
    ]
    dists = np.array(sorted(dists))

    # There should be 4 equal sides and 2 equal diagonals
    side = dists[0]
    if not np.allclose(dists[0:4], side, atol=tol):
        return False, False  # Not a rectangle or square

    diag = dists[4]
    if not np.allclose(dists[4:6], diag, atol=tol):
        return False, False  # Not a rectangle or square

    # Rectangle: 4 equal sides, 2 equal diagonals
    is_rectangle = True

    # Square: additionally, diagonal == side * sqrt(2)
    is_square = np.isclose(diag, side * np.sqrt(2), atol=tol)

    return is_rectangle, is_square


@njit
def transform(points, trans_index):
    transformed = np.empty_like(points)

    for i in range(len(points)):
        x, y = points[i]
        if trans_index == 0:  # Identity
            tx, ty = x, y
        elif trans_index == 1:  # Rotate 90°
            tx, ty = y, -x
        elif trans_index == 2:  # Rotate 180°
            tx, ty = -x, -y
        elif trans_index == 3:  # Rotate 270°
            tx, ty = -y, x
        elif trans_index == 4:  # Reflect over y-axis
            tx, ty = x, -y
        elif trans_index == 5:  # Reflect + Rotate 90°
            tx, ty = y, x
        elif trans_index == 6:  # Reflect + Rotate 180°
            tx, ty = -x, y
        elif trans_index == 7:  # Reflect + Rotate 270°
            tx, ty = -y, -x
        transformed[i] = (tx, ty)
    return transformed


def center(points):
    centroid = (np.min(points, axis=0) + np.max(points, axis=0)) / 2
    return (points - centroid).astype(np.float32), centroid


def group_by_length(polygons):
    groups = defaultdict(list)
    for polygon in polygons:
        groups[len(polygon)].append(polygon)
    return groups


# def hash_polygon(polygon):
#    return hash(normalize(set_precision(Polygon(polygon), grid_size=0.00001)))


def hash_polygon(polygon):
    return hash(
        tuple(
            get_coordinates(
                (normalize(set_precision(Polygon(polygon), grid_size=0.00001)))
            )
            .flatten()
            .tolist()
        )
    )


# def group_congruent_polygons(polygons):
#    groups = {}
#
#    for idx, poly in enumerate(polygons):
#        centered_poly, centroid = center(poly)
#
#        found = False
#        # Do not try all transformations for the first polygon
#        if idx > 0:
#            is_rectangle, is_square = is_rectangle_or_square(centered_poly)
#            if is_square:
#                MAP = MAP_SQUARE
#            elif is_rectangle:
#                MAP = MAP_RECTANGLE
#            else:
#                MAP = MAP_ALL
#
#            for trans_index in MAP:
#                key = hash_polygon(transform(centered_poly, trans_index))
#                if groups.get(key) is not None:
#                    groups[key].append(
#                        {
#                            "idx": idx,
#                            "centroid": centroid.tolist(),
#                            "transformation": INVERSE_MAP[trans_index],
#                        }
#                    )
#                    found = True
#                    break
#
#        if not found:
#            # first element is the reference polygon
#            key = hash_polygon(centered_poly)
#            groups[key] = [centered_poly]
#
#            # All other elements are instances
#            groups[key].append({"idx": idx, "centroid": centroid.tolist(), "transformation": 0})
#
#    return groups


def group_congruent_polygons(polygons):
    groups = {}

    for idx, poly in enumerate(polygons):
        centered_poly, centroid = center(poly)

        found = False

        # is_rectangle, is_square = is_rectangle_or_square(centered_poly)
        # if is_square:
        #     MAP = MAP_SQUARE
        # elif is_rectangle:
        #     MAP = MAP_RECTANGLE
        # else:
        MAP = MAP_ALL

        if idx > 0:
            for trans_index in MAP:
                key = hash_polygon(transform(centered_poly, trans_index))
                if groups.get(key) is not None:
                    groups[key].append(
                        {
                            "idx": idx,
                            "centroid": centroid.tolist(),
                            "transformation": trans_index,
                        }
                    )
                    found = True
                    break

        if not found:
            # first element is the reference polygon
            key = hash_polygon(centered_poly)
            groups[key] = [centered_poly]
            x = normalize(Polygon(transform(centered_poly, 0)))
            # All other elements are instances
            groups[key].append(
                {"idx": idx, "centroid": centroid.tolist(), "transformation": 0}
            )

    return groups


# ---------------------------
# 2. Reconstruction Function
# ---------------------------


def reconstruct(groups):
    result = []
    for i, (key, group) in enumerate(groups.items()):
        reference = group[0]
        for polygon in group[1:]:
            poly = transform(reference, polygon["transformation"]) + polygon["centroid"]
            result.append(poly)
    return result


def reconstruct_colored(groups):
    result = []
    colors = [
        f"rgba({r},{g},{b},1.0)"
        for r, g, b in (np.array(distinctipy.get_colors(len(groups))) * 255).round(0)
    ]
    for i, (key, group) in enumerate(groups.items()):
        reference = group[0]
        for polygon in group[1:]:
            poly = transform(reference, polygon["transformation"]) + polygon["centroid"]
            result.append((poly, colors[i], polygon["idx"], polygon["transformation"]))

    return result


# ---------------------------
# 3. Plot Polygons
# ---------------------------


def plot_polygons(polygons, title="Original Polygons", width=1300, height=1300):
    fig = go.Figure()

    for i, p in enumerate(polygons):
        if len(p) == 4:
            (poly, color, idx, trans) = p
        else:
            (poly, color) = p
            idx = i
            trans = 0
        fill_color = color.replace("1.0", "0.3")
        closed = np.vstack((poly, poly[0]))
        fig.add_trace(
            go.Scatter(
                x=closed[:, 0],
                y=closed[:, 1],
                mode="lines",
                line=dict(color=color, width=1),
                fill="toself",
                fillcolor=fill_color,
                name=f"Polygon {idx} / {trans}",
            )
        )

    fig.update_layout(
        title=title,
        width=width,
        height=height,
        showlegend=False,
        plot_bgcolor="white",
        xaxis=dict(showgrid=False, zeroline=False, scaleanchor="y"),
        yaxis=dict(showgrid=False, zeroline=False, scaleanchor="x"),
    )
    fig.show()
