import copy
from typing import cast

from build123d import Polygon, extrude, Pos, Compound, Box
from ocp_tessellate.utils import Color

from kfactory import LayerEnum

from gdsfactory.component import Component
from gdsfactory.technology import DerivedLayer, LayerStack, LayerViews, LogicalLayer
from gdsfactory.typings import LayerSpecs

INSTANCES = {}


def _get_extruded_polygon(polygon, height, zmin, color, decimals=4, optimize=True):
    if optimize and len(polygon) == 4:

        dx0 = round(polygon[3][0] - polygon[0][0], decimals)
        dx1 = round(polygon[2][0] - polygon[1][0], decimals)
        dy0 = round(polygon[1][1] - polygon[0][1], decimals)
        dy1 = round(polygon[2][1] - polygon[3][1], decimals)
        h = round(height, decimals)

        if dx0 == dx1 and dy0 == dy1:
            # The viewer supports instances, so render a box only once and
            # reference the instance moved to the right position

            if INSTANCES.get((dx0, dy0, h)) is None:
                INSTANCES[(dx0, dx1, h)] = Box(dx0, dy0, h)
                reference = INSTANCES[(dx0, dx1, h)]
            else:
                reference = copy.copy(INSTANCES[(dx0, dx1, h)])

            center = (polygon[0][0] + dx0 / 2, polygon[0][1] + dy0 / 2)
            obj = Pos(*center, zmin + height / 2) * reference
            obj.color = Color(color)
            return obj

    p = Polygon(*polygon, align=None)
    obj = extrude(p, amount=-height)
    obj = Pos(0, 0, zmin) * obj
    obj.color = Color(color)
    return obj


def to_b123d(
    component: Component,
    layer_views: LayerViews | None = None,
    layer_stack: LayerStack | None = None,
    exclude_layers: LayerSpecs | None = None,
) -> Compound:
    """Return build123d Compound.

    Args:
        component: to extrude in 3D.
        layer_views: layer colors from Klayout Layer Properties file.
            Defaults to active PDK.layer_views.
        layer_stack: contains thickness and zmin for each layer.
            Defaults to active PDK.layer_stack.
        exclude_layers: list of layer index to exclude.

    """
    from gdsfactory.pdk import (
        get_active_pdk,
        get_layer,
        get_layer_stack,
        get_layer_views,
    )

    try:
        from trimesh.creation import extrude_polygon
        from trimesh.scene import Scene
    except ImportError as e:
        print("you need to `pip install trimesh`")
        raise e

    layer_views = layer_views or get_layer_views()
    layer_stack = layer_stack or get_layer_stack()

    exclude_layers = exclude_layers or ()
    exclude_layers = [get_layer(layer) for layer in exclude_layers]

    component_with_booleans = layer_stack.get_component_with_derived_layers(component)
    polygons_per_layer = component_with_booleans.get_polygons_points(
        merge=True,
    )
    has_polygons = False

    sub_assemblies = []
    assembly = Compound(label="GDS")
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
        layer_view = layer_views.get_from_tuple(layer_tuple)
        assert layer_view.fill_color is not None
        if zmin is not None and layer_view.visible:
            has_polygons = True
            polygons = polygons_per_layer[layer_index]
            height = level.thickness
            objects = []
            sub_assembly = Compound(label=str(f"{layer_view.name} ({round(zmin,4)})"))
            print(layer_view.name, len(polygons))
            for polygon in polygons:
                obj = _get_extruded_polygon(
                    polygon,
                    height,
                    zmin,
                    layer_view.fill_color.as_rgb_tuple(),
                    optimize=True,
                )
                objects.append(obj)
            sub_assembly.children = objects

        sub_assemblies.append(sub_assembly)
    assembly.children = sub_assemblies

    if not has_polygons:
        raise ValueError(
            f"{component.name!r} does not have polygons defined in the "
            f"layer_stack or layer_views for the active Pdk {get_active_pdk().name!r}"
        )
    return assembly


if __name__ == "__main__":
    from ocp_vscode import show
    import gdsfactory as gf

    example = 1

    if example == 1:
        c = gf.c.straight_heater_doped_rib(length=100)
    elif example == 2:
        c = gf.components.straight_heater_doped_rib(
            length=320,
            nsections=3,
            cross_section="strip_rib_tip",
            cross_section_heater="rib_heater_doped",
            via_stack="via_stack_slab_npp_m3",
            via_stack_metal="via_stack_m1_mtop",
            via_stack_metal_size=(10, 10),
            via_stack_size=(10, 10),
            taper="taper_cross_section",
            heater_width=2,
            heater_gap=0.8,
            via_stack_gap=0,
            width=0.5,
            xoffset_tip1=0.2,
            xoffset_tip2=0.4,
        ).copy()
    elif example == 3:
        c = gf.components.straight_heater_metal(length=90)
    elif example == 4:
        c = gf.components.straight_heater_meander(
            length=300,
            spacing=2,
            cross_section="strip",
            heater_width=2.5,
            extension_length=15,
            layer_heater="HEATER",
            via_stack="via_stack_heater_mtop",
            heater_taper_length=10,
            taper_length=10,
            n=3,
        ).copy()
    elif example == 5:
        bend180 = gf.components.bend_circular180()
        wg_pin = gf.components.straight_pin(length=40)
        wg = gf.components.straight()

        # Define a map between symbols and (component, input port, output port)
        symbol_to_component = {
            "A": (bend180, "o1", "o2"),
            "B": (bend180, "o2", "o1"),
            "H": (wg_pin, "o1", "o2"),
            "-": (wg, "o1", "o2"),
        }

        # Each character in the sequence represents a component
        s = "AB-H-H-H-H-BA"
        c = gf.components.component_sequence(
            sequence=s, symbol_to_component=symbol_to_component
        )
    elif example == 6:
        c = gf.components.coupler_full(
            coupling_length=40, dx=10, dy=4.8, gap=0.5, dw=0.1, cross_section="strip"
        ).copy()
    elif example == 7:
        c = gf.components.ge_detector_straight_si_contacts(
            length=40,
            cross_section="pn_ge_detector_si_contacts",
            via_stack="via_stack_slab_m3",
            via_stack_width=10,
            via_stack_spacing=5,
            via_stack_offset=0,
            taper_length=20,
            taper_width=0.8,
            taper_cros_section="strip",
        ).copy()
    elif example == 8:
        # BROKEN
        c = gf.components.awg(
            arms=10, outputs=3, fpr_spacing=50, arm_spacing=1, cross_section="strip"
        ).copy()
    elif example == 9:
        c = gf.components.dbr(
            w1=0.45,
            w2=0.55,
            l1=0.159,
            l2=0.159,
            n=10,
            cross_section="strip",
            straight_length=0.01,
        ).copy()
    elif example == 11:
        c = gf.components.dbr_tapered(
            length=10,
            period=0.85,
            dc=0.5,
            w1=0.4,
            w2=1,
            taper_length=20,
            fins=False,
            fin_size=(0.2, 0.05),
            cross_section="strip",
        ).copy()

    compound = to_b123d(c)
    show(compound, progress="+-c")
