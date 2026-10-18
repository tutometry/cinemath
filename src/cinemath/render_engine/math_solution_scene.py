"""Stable Manim entrypoint — reads animation.json from CINEMATH_ANIMATION_JSON."""

from cinemath.render_engine.composition import apply_manim_config

# Apply composition (frame aspect / pixels) before the Scene class is constructed.
apply_manim_config()

from cinemath.render_engine.builder import ScriptedScene


class MathSolution(ScriptedScene):
    pass
