"""Run in Blender UI. Preserve the scene and viewport; no collision rebuild needed."""
import bpy
import math
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('roomwalker_view_test', Path(__file__).with_name('__init__.py'))
rw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rw)
# Expected fault injection should not create diagnostic files.
rw.diagnostic = lambda message: None
from mathutils import Vector
from types import SimpleNamespace

area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
space = area.spaces.active
rv = space.region_3d
saved = (rv.view_location.copy(), rv.view_rotation.copy(), rv.view_distance, rv.view_perspective)
runtime = rw.Runtime.__new__(rw.Runtime)
runtime.space, runtime.area = space, area
runtime.scene = SimpleNamespace(roomwalker=SimpleNamespace(eye_height=1.6))
runtime.last_valid_view = tuple(saved[0])+tuple(saved[1])+(saved[2],)
checks = {}
max_error = 0.0
try:
    for i, (yaw, pitch) in enumerate([(0, 0), (1.2, .8), (-2.5, -1.48), (3.14, 1.48)]):
        runtime.player = rw.Player((2, -3, 1.5), yaw, pitch)
        runtime.view()
        eye = rv.view_location + rv.view_rotation @ Vector((0, 0, rv.view_distance))
        expected = runtime.player.feet + rw.UP * runtime.scene.roomwalker.eye_height
        error = (eye - expected).length
        max_error = max(max_error, error)
        checks[f'eye_preserved_{i}'] = error < 1e-5
        checks[f'positive_distance_{i}'] = rv.view_distance > 0
        runtime.view_signature = None
        runtime.adopt_external_view()
        checks[f'editor_handoff_{i}'] = (runtime.player.feet-Vector((2,-3,1.5))).length < 1e-5
    with bpy.context.temp_override(area=area, region=next(r for r in area.regions if r.type == 'WINDOW')):
        for delta in [1, -1] * 20:
            bpy.ops.view3d.zoom('INVOKE_DEFAULT', delta=delta)
        checks['zoom_stays_finite'] = rw.finite(runtime.signature()) and rv.view_distance > 0
    rv.view_distance = float('nan')
    try:
        runtime.adopt_external_view()
    except RuntimeError:
        checks['bad_distance_recovered'] = rw.finite(runtime.signature()) and rv.view_distance > 0
finally:
    rv.view_rotation = saved[1]
    rv.view_distance = saved[2]
    rv.view_location = saved[0]
    rv.view_perspective = saved[3]
    area.tag_redraw()
result = {'checks': checks, 'all_passed': all(checks.values()), 'max_eye_error': max_error}

if not result["all_passed"]:
    raise AssertionError(result)
print(result)
