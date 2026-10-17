# Changelog

## 0.1.8 — 2026-10-17

- LB / RB cycle viewport shading backward / forward through Wireframe, Solid, Material Preview, and Rendered.
- Each press switches one mode; holding does not repeat, and simultaneous presses cancel each other.
- Shading controls remain available while navigation is paused.
- Added the new control to the sidebar and README.

## 0.1.7 — 2026-10-17

First public prototype, incorporating the local development iterations:

- First-person walking and collision-aware flight.
- Xbox gamepad backend for macOS Apple Silicon and keyboard/mouse mode.
- Mouse/keyboard remain available for editing in gamepad mode.
- Manual viewport changes are adopted without snapping back.
- Y toggles flight; A/B control vertical flight.
- L3 single-click sprint, RT analog throttle, LT zoom up to 2×.
- Separate walk/fly speeds, manual collision refresh, optional refresh after editing.
- Source, native helper source/binary, packaging script, and synthetic collision/input tests.
