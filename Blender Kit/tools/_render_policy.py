"""Blender Kit render policy (import it in every Blender script, then call apply(scene)).

Renders use 1 sample, and 2 motion-blur steps when motion blur is on. This keeps every render fast on an ordinary PC or laptop; the
look comes from lighting, depth, motion and grading, not from samples. A template setting, quality preset or Claude's own judgment
is NOT a reason to raise these. Only the user can, for one job: put their request word for word in
config["render_samples_user_request"] (with config["samples"]) or config["render_blur_steps_user_request"] (with
config["blur_steps"]). This module only applies settings; it never renders.
"""

POLICY = "blender-kit-1-sample"


def samples(config=None):
    config = config or {}
    if not str(config.get("render_samples_user_request", "")).strip():
        return 1
    v = config.get("samples", 1)
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise ValueError("a user-requested sample count must be a positive whole number")
    return v


def blur_steps(config=None):
    config = config or {}
    if not str(config.get("render_blur_steps_user_request", "")).strip():
        return 2
    v = config.get("blur_steps", 2)
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise ValueError("user-requested blur steps must be a positive whole number")
    return v


def apply(scene, config=None):
    """Set samples and blur steps on a bpy scene (EEVEE and Cycles). Returns the sample count used."""
    n = samples(config)
    ee = getattr(scene, "eevee", None)
    if ee is not None:
        if hasattr(ee, "taa_render_samples"):
            ee.taa_render_samples = n
        if hasattr(ee, "motion_blur_steps"):
            ee.motion_blur_steps = blur_steps(config)
    if hasattr(scene.render, "motion_blur_steps"):      # Blender 4.2+ keeps it on the render settings
        scene.render.motion_blur_steps = blur_steps(config)
    cy = getattr(scene, "cycles", None)
    if cy is not None:
        cy.samples = n
        if hasattr(cy, "use_adaptive_sampling"):
            cy.use_adaptive_sampling = False
    for layer in getattr(scene, "view_layers", ()):
        if hasattr(layer, "samples"):
            layer.samples = 0                          # use the scene count, no hidden per-layer override
    return n
