from typing import cast

from gdsfactory.pdk import get_layer_stack

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


def to_poly(
    component: Component,
    layer_views: LayerViews | None = None,
    layer_stack: LayerStack | None = None,
    exclude_layers: LayerSpecs | None = None,
):
    """Return nested lists of polygons.

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

    component_with_booleans = layer_stack.get_component_with_derived_layers(component)
    polygons_per_layer = component_with_booleans.get_polygons_points(merge=True)
    has_polygons = False

    polygons = {}

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

        assert layer_view.fill_color is not None
        if zmin is not None and layer_view.visible:
            has_polygons = True
            polygons[layer_view.name] = polygons_per_layer[layer_index]

    if not has_polygons:
        raise ValueError(
            f"{component.name!r} does not have polygons defined in the "
            f"layer_stack or layer_views for the active Pdk {get_active_pdk().name!r}"
        )

    return polygons
