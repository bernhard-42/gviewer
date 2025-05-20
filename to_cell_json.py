# %%
from collections import defaultdict

import numpy as np
import orjson
import time

import gdstk
import sky130
import gdsfactory as gf
from gdsfactory.generic_tech import get_generic_pdk

from serialize import numpy_to_buffer_json
from polygon import group_by_length, group_congruent_polygons

# %%

PDK = None
LAYERS = {}

DEBUG = False


def init_sky130():
    global PDK
    global LAYERS
    global EXCLUDE_LAYERS

    EXCLUDE_LAYERS = [81, 236]
    PDK = sky130.PDK
    LAYERS = {
        tuple(level.layer.layer): {
            "name": level.layer.layer.name,
            "thickness": level.thickness,
            "zmin": level.zmin,
        }
        for level in PDK.layer_stack.layers.values()
    }


def init_generic():
    global PDK
    global LAYERS
    global EXCLUDE_LAYERS

    EXCLUDE_LAYERS = []
    PDK = get_generic_pdk()
    LAYERS = {}

    for level in PDK.get_layer_stack().layers.values():
        if isinstance(level.layer, gf.technology.layer_stack.DerivedLayer):
            LAYERS[tuple(level.derived_layer.layer)] = {
                "name": level.derived_layer.layer.name,
                "thickness": level.thickness,
                "zmin": level.zmin,
            }
        else:
            LAYERS[tuple(level.layer.layer)] = {
                "name": level.layer.layer.name,
                "thickness": level.thickness,
                "zmin": level.zmin,
            }


def get_layer_name(layer):
    if LAYERS.get(layer) is not None:
        return LAYERS[layer]["name"]
    else:
        raise KeyError(f"Layer {layer} is unknown")


def get_layer_thickness(layer):
    if LAYERS.get(layer) is not None:
        return LAYERS[layer]["thickness"]
    else:
        raise KeyError(f"Layer {layer} is unknown")


def get_layer_zmin(layer):
    if LAYERS.get(layer) is not None:
        return LAYERS[layer]["zmin"]
    else:
        raise KeyError(f"Layer {layer} is unknown")


def get_layer_view(layer):
    result = [
        view for view in PDK.layer_views.layer_views.values() if view.layer == layer
    ]
    if len(result) == 1:
        return result[0]
    else:
        raise KeyError(f"Layer {layer} is unknown")


def get_layer_color(layer):
    view = get_layer_view(layer)
    return view.fill_color.as_hex()


def get_polygons(cell, as_points=False):
    layers = defaultdict(list)

    for polygon in cell.polygons:
        key = (polygon.layer, polygon.datatype)
        try:
            _ = get_layer_name((polygon.layer, polygon.datatype))
        except:
            continue

        if polygon.layer not in EXCLUDE_LAYERS:
            if as_points:
                layers[key].append(polygon.points)
            else:
                layers[key].append(polygon)

    return dict(layers)


def get_layer_polygons(cell):
    return {k: [p.points for p in v] for k, v in get_polygons(cell).items()}


def get_references(cell):
    reference_data = defaultdict(set)
    cells = {}

    for ref in cell.references:
        transform = (
            tuple(ref.origin),  # (x, y) coordinates
            ref.rotation,  # Rotation in radians
            ref.x_reflection,  # Boolean reflection state
            ref.magnification,  # Magnification factor
        )

        if (
            ref.repetition.columns is not None
            or ref.repetition.offsets is not None
            or ref.repetition.x_offsets is not None
            or ref.repetition.y_offsets is not None
        ):
            print(
                f"Warning: Repetition not supported for {ref.cell.name} in {cell.name}"
            )
        cells[(ref.cell.name, hash(ref.cell))] = ref.cell
        reference_data[(ref.cell.name, hash(ref.cell))].add(transform)

    return [
        {
            "cell": cells[key],
            "transforms": sorted(transforms, key=lambda x: (x[0], x[1], x[2], x[3])),
        }
        for key, transforms in reference_data.items()
    ]


# %%


def get_trans_index(rotation, x_reflected):
    def eq(a, b):
        return abs(a - b) < 1e-6

    if eq(rotation, 0) and not x_reflected:  # Identity
        return 0
    elif eq(rotation, np.pi / 2) and not x_reflected:  # Rotate 90°
        return 1
    elif eq(rotation, np.pi) and not x_reflected:  # Rotate 180°
        return 2
    elif eq(rotation, 3 * np.pi / 2) and not x_reflected:  # Rotate 270°
        return 3
    elif eq(rotation, 0) and x_reflected:  # Reflect over y-axis
        return 4
    elif eq(rotation, np.pi / 2) and x_reflected:  # Reflect + Rotate 90°
        return 5
    elif eq(rotation, np.pi) and x_reflected:  # Reflect + Rotate 180°
        return 6
    elif eq(rotation, 3 * np.pi / 2) and x_reflected:  # Reflect + Rotate 270°
        return 7
    else:
        raise ValueError(
            f"Invalid transformation: rotation={rotation}, x_reflected={x_reflected}"
        )


def get_trans_matrix(origin, rotation, x_reflected, magnification):
    s, c = np.sin(rotation), np.cos(rotation)
    x, y = origin
    r = -1 if x_reflected else 1
    return np.array([[c, -r * s, x], [s, r * c, y], [0, 0, 1]]) * magnification


def handle_references(
    parent_cell_name,
    parent_cell,
    path,
    poly_assembly,
    instance_index,
    parent_matrices=None,
):
    parts = []

    references = get_references(parent_cell)
    for reference in references:
        cell = reference["cell"]

        if parent_matrices is None:
            matrices = [
                get_trans_matrix(*transform) for transform in reference["transforms"]
            ]
        else:
            matrices = [
                matrix @ get_trans_matrix(*transform)
                for transform in reference["transforms"]
                for matrix in parent_matrices
            ]

        cell_parts = {
            "version": 3,
            "name": f"C:{cell.name}",
            "id": f"{path}/C:{cell.name}",
            "loc": [(0, 0, 0), (0, 0, 0, 1)],
            "parts": [],
        }

        instance_index, ref_parts = handle_references(
            cell.name,
            cell,
            f"{path}/C:{cell.name}",
            poly_assembly,
            instance_index,
            matrices,
        )

        cell_parts["parts"] = ref_parts

        polygons = get_polygons(cell)

        for layer, layer_polygons in polygons.items():
            try:
                layer_name = get_layer_name(layer)
            except:
                continue

            refs = []
            for polygon in layer_polygons:
                poly_assembly["instances"].append(polygon.points.astype("float32"))
                refs.append(instance_index)
                instance_index += 1

            poly_shape = {
                "version": 3,
                "name": f"L:{layer_name}",
                "id": f"{path}/C:{cell.name}/L:{layer_name}",
                "loc": [(0, 0, get_layer_zmin(layer)), (0, 0, 0, 1)],
                "color": get_layer_color(layer),
                "shape": {
                    "refs": refs,
                    "matrices": (
                        [len(matrices)]
                        if DEBUG
                        else np.asarray(
                            [matrix[:2].reshape(-1) for matrix in matrices],
                            dtype="float32",
                        )
                    ),
                    "height": get_layer_thickness(layer),
                },
                "renderback": False,
                "state": [1, 1],
                "type": "polygon",
                "subtype": "solid",
            }
            cell_parts["parts"].append(poly_shape)

        cell_parts["parts"] = sorted(
            cell_parts["parts"], key=lambda shape: shape["loc"][0][2]  # sort be zmin
        )

        parts.append(cell_parts)

    return instance_index, parts


def to_json(lib, return_json=True):
    """Return optimzed json.

    Args:
        lib: to extrude in 3D.
        exclude_layers: list of layer index to exclude.

    """
    start = time.time()
    poly_assembly = {
        "format": "GDS",
        "version": 3,
        "name": lib.name,
        "id": f"/{lib.name}",
        "loc": [(0, 0, 0), (0, 0, 0, 1)],
        "instances": [],
        "parts": [],
    }
    instance_index = 0
    top_level_cells = {c.name: c for c in lib.top_level()}

    for top_name, top_cell in top_level_cells.items():

        #
        # Handle top level references
        #

        top_parts = {
            "version": 3,
            "name": f"C:{top_name}",
            "id": f"/{lib.name}/C:{top_name}",
            "loc": [(0, 0, 0), (0, 0, 0, 1)],
            "parts": [],
        }

        instance_index, ref_parts = handle_references(
            top_name,
            top_cell,
            f"/{lib.name}/C:{top_name}",
            poly_assembly,
            instance_index,
        )

        top_parts["parts"] = ref_parts

        print("duration for references:", time.time() - start)

        #
        # Handle top level elements
        #
        start = time.time()
        polygons = get_layer_polygons(top_cell)
        for layer, layer_polygons in polygons.items():
            layer_name = get_layer_name(layer)
            layer_parts = {
                "version": 3,
                "name": f"L:{layer_name}",
                "id": f"/{lib.name}/C:{top_name}/L:{layer_name}",
                "loc": [(0, 0, 0), (0, 0, 0, 1)],
                "parts": [],
            }
            index = 0
            groups_by_length = group_by_length(layer_polygons).values()
            for groups in groups_by_length:
                congruent_polygons = group_congruent_polygons(groups)

                for group in congruent_polygons.values():
                    poly_assembly["instances"].append(group[0])
                    matrices = np.asarray(
                        [
                            get_trans_matrix(*p["transformation"])[:2].reshape(-1)
                            for p in group[1:]
                        ],
                        dtype="float32",
                    )
                    poly_shape = {
                        "version": 3,
                        "name": f"group_{index}",
                        "id": f"/{lib.name}/C:{top_name}/L:{layer_name}/group_{index}",
                        "loc": [(0, 0, get_layer_zmin(layer)), (0, 0, 0, 1)],
                        "color": get_layer_color(layer),
                        "shape": {
                            "refs": [instance_index],
                            "matrices": ([len(matrices)] if DEBUG else matrices),
                            "height": get_layer_thickness(layer),
                        },
                        "renderback": False,
                        "state": [1, 1],
                        "type": "polygon",
                        "subtype": "solid",
                    }
                    index += 1

                    layer_parts["parts"].append(poly_shape)
                    instance_index += 1

            layer_parts["parts"] = sorted(
                layer_parts["parts"], key=lambda shape: shape["loc"][0][2]
            )  # sort be zmin

            top_parts["parts"].append(layer_parts)

        if len(top_parts["parts"]) > 0:
            poly_assembly["parts"].append(top_parts)

        if DEBUG:
            poly_assembly["instances"] = []
        print("duration with geo analyzer:", time.time() - start)

    if return_json:
        return orjson.dumps(numpy_to_buffer_json(poly_assembly)).decode("utf-8")
    else:
        return poly_assembly


# %%
if __name__ == "__main__":
    import sys

    if len(sys.argv) == 2:
        example = int(sys.argv[1])
    else:
        example = 5

    if example == 1:

        init_generic()

        # c = gf.c.straight_heater_doped_rib(length=100)
        # c.write_gds("straight_heater_doped_rib.gds")

        c = gdstk.read_gds("examples/straight_heater_doped_rib.gds")

        name = "straight_heater_doped"

    elif example == 2:
        init_sky130()

        c = gdstk.read_gds("examples/example_sky130.gds")
        name = "sky130"

        # polydrawing_m:    polygons:   3626 points:   42794
        # nwelldrawing_m:   polygons:     22 points:      88
        # nsdmdrawing_m:    polygons:    202 points:    1528
        # hvtpdrawing_m:    polygons:     22 points:      88
        # licon1drawing_m:  polygons:  25348 points:  101392
        # li1drawing_m:     polygons:   2686 points:   56014
        # mcondrawing_m:    polygons:  13153 points:   52612
        # met1:             polygons:   1381 points:   17988
        # viadrawing_m:     polygons:   1695 points:    6780
        # met2drawing_m:    polygons:    647 points:    8818
        # via2drawing_m:    polygons:    458 points:    1832
        # met3drawing_m:    polygons:    126 points:     632
        # via3drawing_m:    polygons:    440 points:    1760
        # met4drawing_m:    polygons:      5 points:      20
        # via4drawing_m:    polygons:     13 points:      52
        # met5drawing_m:    polygons:      5 points:      20

    elif example == 3:
        init_sky130()

        c = gdstk.read_gds("examples/sram_2_16_sky130A.gds")
        name = "sram_2_16"

        # polydrawing_m:    polygons:   515 points:   6764
        # nwelldrawing_m:   polygons:    42 points:    272
        # nsdmdrawing_m:    polygons:   447 points:   2230
        # licon1drawing_m:  polygons:  2493 points:   9976
        # li1drawing_m:     polygons:  1115 points:  19498
        # mcondrawing_m:    polygons:  1421 points:   5688
        # met1:             polygons:   761 points:   5518
        # viadrawing_m:     polygons:   492 points:   1984
        # met2drawing_m:    polygons:   235 points:   2848
        # via2drawing_m:    polygons:   267 points:   1068
        # met3drawing_m:    polygons:   109 points:   1446
        # via3drawing_m:    polygons:   133 points:    532
        # met4drawing_m:    polygons:    70 points:    560

    elif example == 4:
        init_sky130()

        c = gdstk.read_gds("examples/sram_32_1024_sky130A.gds")
        name = "sram_32_1024"

        # polydrawing_m:   polygons:  70406 points: 1014418
        # nwelldrawing_m:  polygons:    262 points:    1812
        # nsdmdrawing_m:   polygons:  53212 points:  349106
        # licon1drawing_m: polygons: 617609 points: 2470436
        # li1drawing_m:    polygons: 243278 points: 3192044
        # mcondrawing_m:   polygons: 296952 points: 1187808
        # met1:            polygons: 140145 points:  733044
        # viadrawing_m:    polygons:  71428 points:  285968
        # met2drawing_m:   polygons:   1980 points:   47134
        # via2drawing_m:   polygons:   2587 points:   10348
        # met3drawing_m:   polygons:    675 points:   11610
        # via3drawing_m:   polygons:   1209 points:    4836
        # met4drawing_m:   polygons:    638 points:    5112

    elif example == 5:

        init_generic()

        # c = gf.c.straight_heater_doped_rib(length=100)
        # c.write_gds("straight_heater_doped_rib.gds")

        c = gdstk.read_gds("ref.gds")

        name = "ref"

    with open(f"viewer/js/{name}.js", "w") as fd:
        j = to_json(c, return_json=True)
        if not DEBUG:
            fd.write(f"const {name} = {j};")

    # %%
