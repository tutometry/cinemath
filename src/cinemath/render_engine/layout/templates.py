"""Named scene layout templates — authored in animation JSON only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from cinemath.render_engine.layout.constraints import (
    LayoutConstraints,
    constraints_for_composition,
)
from cinemath.render_engine.stage import Region, StageConductor, full_frame

TemplateName = Literal["full_frame", "plot_with_labels", "split_archive", "board_only"]

TEMPLATE_NAMES: frozenset[str] = frozenset(
    {"full_frame", "plot_with_labels", "split_archive", "board_only"}
)


@dataclass(frozen=True)
class Template:
    name: TemplateName


def resolve_template(scene_data: dict[str, Any]) -> Template:
    """Resolve layout template from required ``scene.template`` (no heuristics)."""
    explicit = scene_data.get("template")
    if explicit is None:
        raise ValueError(
            f"scene {scene_data.get('id', '<unknown>')!r} missing required 'template'"
        )
    name = str(explicit)
    if name not in TEMPLATE_NAMES:
        raise ValueError(
            f"Unknown scene template {name!r}; expected one of {sorted(TEMPLATE_NAMES)}"
        )
    return Template(name)  # type: ignore[arg-type]


def region_for_template(template: Template, conductor: StageConductor) -> Region:
    """Resolve the placement region for a template under the live stage state."""
    if template.name == "board_only":
        return conductor.board_region()
    if template.name == "plot_with_labels":
        return content_band_region(conductor)
    if template.name == "split_archive":
        return conductor.content()
    # full_frame: honor half-stage when archive is pinned
    return full_frame() if not conductor.use_right_stage else conductor.content()


def constraints_for_template(
    template: Template,
    conductor: StageConductor,
) -> LayoutConstraints:
    region = region_for_template(template, conductor)
    return constraints_for_composition(region=region)


def content_band_region(conductor: StageConductor) -> Region:
    """Band between composition floor and caption ceiling inside the active content."""
    base = conductor.content()
    constraints = constraints_for_composition(region=base)
    floor = constraints.floor
    ceiling = constraints.ceiling
    return Region(
        center=(base.center[0], (floor + ceiling) / 2.0),
        max_w=base.max_w,
        max_h=max(ceiling - floor, 0.5),
        left=base.left,
        right=base.right,
        bottom=floor,
        top=ceiling,
    )
