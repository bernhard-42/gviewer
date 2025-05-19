# %%
import time
from typing import cast

import numpy as np
import orjson
from kfactory import LayerEnum

from gdsfactory.component import Component
from gdsfactory.technology import DerivedLayer, LayerStack, LayerViews, LogicalLayer
from gdsfactory.typings import LayerSpecs
from gdsfactory.pdk import (
    get_active_pdk,
    get_layer,
    get_layer_stack,
    get_layer_views,
)

import gdsfactory as gf

from ocp_tessellate.utils import numpy_to_buffer_json
from polygon import group_by_length, group_congruent_polygons


# %%


def to_json(
    component: Component,
    layer_views: LayerViews | None = None,
    layer_stack: LayerStack | None = None,
    exclude_layers: LayerSpecs | None = None,
    return_json: bool = True,
):
    """Return optimzed json.

    Args:
        component: to extrude in 3D.
        layer_views: layer colors from Klayout Layer Properties file.
            Defaults to active PDK.layer_views.
        layer_stack: contains thickness and zmin for each layer.
            Defaults to active PDK.layer_stack.
        exclude_layers: list of layer index to exclude.

    """

    layer_views = layer_views or get_layer_views()
    layer_stack = layer_stack or get_layer_stack()

    exclude_layers = exclude_layers or ()
    exclude_layers = [get_layer(layer) for layer in exclude_layers]

    start = time.time()
    component_with_booleans = layer_stack.get_component_with_derived_layers(component)
    polygons_per_layer = component_with_booleans.get_polygons_points(merge=True)
    has_polygons = False
    print(f"get_polygons_points took {time.time() - start:.2f} seconds")

    start = time.time()
    top_name = "GDS"
    poly_assembly = {
        "format": "GDS",
        "version": 2,
        "name": top_name,
        "id": f"/{top_name}",
        "loc": [(0, 0, 0), (0, 0, 0, 1)],
        "instances": [],
        "parts": [],
    }
    ref = 0
    for level in layer_stack.layers.values():
        start2 = time.time()
        layer = level.layer

        if isinstance(layer, LogicalLayer):
            assert isinstance(layer.layer, tuple | LayerEnum)
            layer_tuple = cast(tuple[int, int], tuple(layer.layer))
        elif isinstance(layer, DerivedLayer):
            assert level.derived_layer is not None
            assert isinstance(level.derived_layer.layer, tuple | LayerEnum)
            layer_tuple = cast(tuple[int, int], tuple(level.derived_layer.layer))
        else:
            raise ValueError(f"Layer {layer!r} is not a DerivedLayer or LogicalLayer")

        layer_index = int(get_layer(layer_tuple))

        if layer_index in exclude_layers:
            continue

        if layer_index not in polygons_per_layer:
            continue

        zmin = level.zmin
        height = level.thickness
        layer_view = layer_views.get_from_tuple(layer_tuple)

        poly_parts = {
            "format": "GDS",
            "version": 2,
            "name": layer_view.name,
            "id": f"/{top_name}/{layer_view.name}",
            "loc": [(0, 0, zmin), (0, 0, 0, 1)],
            "parts": [],
        }

        assert layer_view.fill_color is not None
        if zmin is not None and layer_view.visible:
            has_polygons = True
            polygons = polygons_per_layer[layer_index]
            index = 0
            groups_by_length = group_by_length(polygons).values()
            for groups in groups_by_length:
                congruent_polygons = group_congruent_polygons(groups)

                for group in congruent_polygons.values():
                    poly_shape = {
                        "name": f"group_{index}",
                        "id": f"/{top_name}/{layer_view.name}/group_{index}",
                        "loc": [(0, 0, 0), (0, 0, 0, 1)],
                        "color": layer_view.fill_color.as_hex(),
                        "shape": {
                            "ref": None,
                            "offsets": None,
                            "height": height,
                        },
                        "renderback": False,
                        "state": [1, 1],
                        "type": "polygon",
                        "subtype": "solid",
                    }
                    index += 1

                    poly_assembly["instances"].append(group[0])
                    poly_shape["shape"]["ref"] = ref
                    poly_shape["shape"]["offsets"] = np.asarray(
                        [(*p["centroid"], p["transformation"]) for p in group[1:]],
                        dtype="float32",
                    )
                    poly_parts["parts"].append(poly_shape)
                    ref += 1

            poly_assembly["parts"].append(poly_parts)
            print(f"layer {layer_view.name} took {time.time() - start2:.2f} seconds")

    if not has_polygons:
        raise ValueError(
            f"{component.name!r} does not have polygons defined in the "
            f"layer_stack or layer_views for the active Pdk {get_active_pdk().name!r}"
        )
    print(f"to_json took {time.time() - start:.2f} seconds")
    if return_json:
        return orjson.dumps(numpy_to_buffer_json(poly_assembly)).decode("utf-8")
    else:
        return poly_assembly


# %%
if __name__ == "__main__":
    example = 4

    if example == 1:
        c = gf.c.straight_heater_doped_rib(length=100)
        layer_stack = get_layer_stack()
        name = "straight_heater_doped"

    elif example == 2:
        from sky130 import LAYER_STACK

        c = gf.read.import_gds("example_sky130.gds")
        layer_stack = LAYER_STACK
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
        from sky130 import LAYER_STACK

        c = gf.read.import_gds("sram_2_16_sky130A.gds")
        layer_stack = LAYER_STACK
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
        from sky130 import LAYER_STACK

        c = gf.read.import_gds("sram_32_1024_sky130A.gds")
        layer_stack = LAYER_STACK
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

    with open(f"{name}.js", "w") as fd:
        j = to_json(c, layer_stack=layer_stack)
        fd.write(f"const {name} = {j};")
