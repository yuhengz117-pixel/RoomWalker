# Black viewport after interactive zoom

Affected: RoomWalker 0.1.8. Fix: 0.1.10. Reproduced in Blender 5.1.2 on macOS Apple Silicon.

## Reproduction

1. Start navigation, then stop it. The old `Runtime.view()` leaves `RegionView3D.view_distance` at `0`.
2. With Dolly zoom selected in Blender input preferences, drag the viewport zoom magnifier vertically.
3. Inspect `view_distance`: it becomes `NaN`. This was reproduced with RoomWalker stopped, without controller input or collision calculations.
4. When navigation adopts that viewport, `eye = view_location + view_rotation @ Vector((0, 0, view_distance))` spreads the invalid distance into all position components. The viewport becomes black.

This identifies a reproducible failure path matching the reported invalid coordinates. The original incident had no event trace, so its exact user gesture cannot be established retrospectively. Collision scene size is not required to reproduce this path.

## Fix

Use a positive orbit distance of 1 Blender unit. Set the pivot to `eye - rotation @ Vector((0, 0, distance))`, preserving the first-person eye while leaving Blender a valid distance for editor navigation. Continue to validate coordinates and restore the last valid view if another source supplies non-finite data.

Startup now reads editable view properties rather than a matrix that may lag a redraw. Malformed axes become neutral, and stopping navigation removes its timer. Public metadata and Current View spawn defaults are unchanged.

## Validation

- Existing movement/collision/controller regression suite.
- Viewport regression suite: four yaw/pitch combinations; eye preservation; positive distance; editor handoff; 40 programmatic zoom operations; invalid-distance restoration.
- Pre-fix magnifier drag reproduced a NaN distance in the actual UI.
- Exact post-fix magnifier dragging has not been verified: the UI automation service returned `noWindowsAvailable`. Programmatic zoom tests do not substitute for this manual check.

Manual release check: start/stop navigation, drag the magnifier both ways, then resume controller navigation and check that the viewport remains visible and finite. Repeat with mouse orbit and pan. No project scenes or diagnostic logs are included in this repository.
