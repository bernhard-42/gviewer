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


# %%
def to_json(
    component: Component,
    layer_views: LayerViews | None = None,
    layer_stack: LayerStack | None = None,
    exclude_layers: LayerSpecs | None = None,
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
        "version": 1.0,
        "label": top_name,
        "id": f"/{top_name}",
        "loc": [(0, 0, 0), (0, 0, 0, 1)],
        "parts": [],
    }
    for level in layer_stack.layers.values():
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

        poly_sub_assembly = {
            "name": layer_view.name,
            "id": f"/{top_name}/{layer_view.name}",
            "loc": [(0, 0, zmin), (0, 0, 0, 1)],
            "parts": [],
        }

        assert layer_view.fill_color is not None
        if zmin is not None and layer_view.visible:
            has_polygons = True
            polygons = polygons_per_layer[layer_index]
            for i, polygon in enumerate(polygons):
                poly_sub_assembly["parts"].append(
                    {
                        "name": f"{layer_view.name}_{i}",
                        "id": f"/{top_name}/{layer_view.name}/{layer_view.name}_{i}",
                        "color": layer_view.fill_color.as_hex(),
                        "loc": [(0, 0, 0), (0, 0, 0, 1)],
                        "shape": {
                            "polygon": np.array(polygon, dtype="float32"),
                            "height": height,
                        },
                        "renderback": False,
                        "state": [1, 1],
                        "type": "polygon",
                        "subtype": "solid",
                    }
                )
            poly_assembly["parts"].append(poly_sub_assembly)

    if not has_polygons:
        raise ValueError(
            f"{component.name!r} does not have polygons defined in the "
            f"layer_stack or layer_views for the active Pdk {get_active_pdk().name!r}"
        )
    print(f"to_json took {time.time() - start:.2f} seconds")
    return orjson.dumps(numpy_to_buffer_json(poly_assembly)).decode("utf-8")


# %%
if __name__ == "__main__":
    example = 1

    if example == 1:
        c = gf.c.straight_heater_doped_rib(length=100)
        layer_stack = get_layer_stack()
        name = "straight_heater_doped"

    elif example == 2:
        from sky130 import LAYER_STACK

        c = gf.read.import_gds("example_sky130.gds")
        layer_stack = LAYER_STACK
        name = "sky130"

    with open(f"{name}.js", "w") as fd:
        j = to_json(c, layer_stack=layer_stack)
        fd.write(f"const {name} = {j};")
