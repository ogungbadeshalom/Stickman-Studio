"""
zenn_style.py — the ZENN minimalist-stickman character + style lock (Doc 2).

Every image (Google Flow / Imagen) and the storyboard generation must carry
this exact character and visual-language spec so the protagonist stays the
SAME person across every scene. This is the single source of truth.

Character (fixed across all scenes):
  oversized round head, 2 solid black oval/dot eyes, thin curved eyebrows,
  tiny simple mouth, NO nose/ears/lips/skin texture, a few short black hair
  strokes up top, narrow cylindrical neck, slim elongated limbs, simplified
  hands/feet, exaggerated clean cartoon proportions (large head, narrow
  torso, long thin limbs), relaxed understated body language.

Clothing (default; change only when the script requires it):
  oversized plain green short-sleeve tee, loose medium-blue denim shorts
  ending above the knee with front pockets + rolled cuffs, plain white
  low-top sneakers, clean black outline around every shape.

Line art: clean black hand-drawn-style outline art, smooth slightly-organic
  contour lines, consistent medium-weight outlines, simple interior lines,
  NO photorealism/painterly/3D/cross-hatching.

Color: restrained palette; off-white/light warm-white background, black
  outline, green tee, muted medium-blue denim, white sneakers,
  very light gray contact shadow. No neon/gloss/strong saturation.

Mood: understated, observational, relatable, slightly deadpan. Emotions
  via pose/composition/context, not exaggerated facial acting.
"""

CHARACTER_LOCK = (
    "Use the same minimalist stickman character as before: an oversized round "
    "head, two solid black oval dot eyes, thin curved eyebrow lines, a tiny "
    "simple curved mouth, no nose or ears, no skin texture, a few short black "
    "hair strokes sticking up from the top, a narrow cylindrical neck, slim "
    "elongated arms and legs, simplified hands and feet. He wears an oversized "
    "plain green short-sleeve t-shirt, loose medium-blue denim shorts ending "
    "above the knee with simple front pockets and rolled cuffs, and plain "
    "white low-top sneakers, every clothing shape outlined in clean black."
)

STYLE_LOCK = (
    "Clean black hand-drawn-style line art, consistent medium-weight outlines, "
    "simple interior lines, flat color fills, very light gray contact shadow "
    "beneath the character. Minimalist 2D cartoon illustration, restrained "
    "palette of off-white background, black, green, muted medium blue, and "
    "white. No photorealism, no 3D, no anime, no painterly shading, no neon, "
    "no glossy surfaces, no dramatic lighting. Simple eye-level perspective, "
    "generous negative space, protagonist visually dominant, understated "
    "observational mood. Keep the character's design, proportions, linework, "
    "clothing, and style completely identical across every scene; change only "
    "pose, expression, actions, and props."
)

def full_image_prompt(action: str) -> str:
    """One self-contained image prompt for a scene = character lock + action + style."""
    return f"{CHARACTER_LOCK} {action} {STYLE_LOCK}"


def full_motion_prompt(scene_summary: str) -> str:
    """
    Doc 3: subtle image-to-video motion prompt. Minimal motion only; never
    change the character design, pose framing, or background content.
    """
    import random
    motions = [
        "a very slow, almost imperceptible push-in on the character.",
        "gentle parallax drift: background elements move slightly slower than the character.",
        "soft ambient idle: a slow blink and a light breath-like shoulder rise and fall, steam drifting, nothing else moving.",
        "a slow, barely noticeable pull-back to emphasize how small the character is in the frame.",
        "static hold: only gentle environmental motion (drifting clouds, soft rain, a lamp flicker), the character almost completely still.",
    ]
    return (
        f"For this scene, add {random.choice(motions)} "
        "No new objects, no new characters, no changed pose, no changes to "
        "lighting or palette. The character's pose, outfit, and background "
        "remain exactly as shown, unchanged. Motion stays subtle and slow."
    )