bl_info = {
    'name': 'RoomWalker — Keyboard & Xbox', 'author': 'yuhengz117-pixel (AI-assisted)',
    'version': (0, 1, 7), 'blender': (4, 5, 0),
    'location': '3D View > Sidebar > RoomWalker',
    'description': 'First-person walking with gravity and collisions; gamepad mode leaves editing input free',
    'category': '3D View',
}

import bpy
import math
import time
import os
import json
import subprocess
import threading
from pathlib import Path
from mathutils import Vector, Quaternion
from mathutils.bvhtree import BVHTree
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, FloatProperty, EnumProperty, PointerProperty, StringProperty

UP = Vector((0, 0, 1))
_runtime = None
_status = 'Ready'


def deadzone(x, y, zone):
    length = math.hypot(x, y)
    if length <= zone:
        return 0.0, 0.0
    factor = min(1.0, (length-zone)/(1-zone))/length
    return x*factor, y*factor


def throttle_factor(value):
    t = max(0.0, min(1.0, (value-.03)/.97))
    return .08+1.92*t**1.5


class Bridge:
    def __init__(self):
        path = Path(__file__).parent / 'native' / 'gamepad_bridge'
        if not path.exists():
            raise RuntimeError('macOS Apple Silicon gamepad helper is missing')
        path.chmod(path.stat().st_mode | 0o111)
        self.state = {}
        self.received = 0
        self.process = subprocess.Popen([str(path)], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.process.stdout:
            try:
                self.state = json.loads(line)
                self.received = time.monotonic()
            except (ValueError, TypeError):
                continue

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        # Never join/wait on the UI thread.


class CollisionWorld:
    def __init__(self, tree=None):
        self.tree = tree
        self.triangles = 0

    def build(self, context, settings):
        vertices, triangles = [], []
        dg = context.evaluated_depsgraph_get()
        ignore = settings.ignore_collection
        ignored = set(ignore.all_objects) if ignore else set()
        for inst in dg.object_instances:
            obj = inst.object
            original = obj.original
            if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT'}:
                continue
            if original in ignored or original.get('roomwalker_ignore', False):
                continue
            if not original.visible_get(view_layer=context.view_layer):
                continue
            if original.display_type in {'WIRE', 'BOUNDS'}:
                continue
            if 'HumanReference' in original.name or 'ScaleFigure-' in original.name:
                continue
            mesh = None
            try:
                mesh = obj.to_mesh()
                if mesh is None:
                    continue
                mesh.calc_loop_triangles()
                base = len(vertices)
                matrix = inst.matrix_world
                vertices.extend(matrix @ v.co for v in mesh.vertices)
                triangles.extend(tuple(base+i for i in tri.vertices) for tri in mesh.loop_triangles)
            finally:
                if mesh is not None:
                    obj.to_mesh_clear()
        self.tree = BVHTree.FromPolygons(vertices, triangles, all_triangles=True) if triangles else None
        self.triangles = len(triangles)

    def floor(self, feet, rise, drop):
        if not self.tree:
            return None
        start = feet + UP*rise
        remaining = rise+drop
        # Skip non-walkable faces; steep walls should never become ground.
        for _ in range(8):
            hit, normal, _, distance = self.tree.ray_cast(start, -UP, remaining)
            if hit is None:
                return None
            if normal.z >= 0.55:
                return hit.z
            advance = distance+.002
            remaining -= advance
            if remaining <= 0:
                break
            start = hit-UP*.002
        return None

    def resolve(self, feet, height, radius):
        if not self.tree:
            return feet.copy()
        pos = feet.copy()
        # Overlapping sphere samples approximate a vertical capsule.
        count = max(3, math.ceil((height-2*radius)/(radius*.65))+1)
        for _ in range(5):
            largest = 0
            for i in range(count):
                z = radius+(height-2*radius)*i/(count-1)
                center = pos+UP*z
                hit, normal, _, distance = self.tree.find_nearest(center, radius)
                if hit is None or distance >= radius-.0001:
                    continue
                delta = center-hit
                direction = delta.normalized() if delta.length > 1e-7 else normal
                push = radius-distance+.0002
                pos += direction*push
                largest = max(largest, push)
            if largest < .0005:
                break
        return pos


class Player:
    def __init__(self, feet, yaw=0, pitch=0):
        self.feet = Vector(feet)
        self.yaw = yaw
        self.pitch = pitch
        self.vz = 0
        self.grounded = False
        self.safe = self.feet.copy()

    def step(self, world, dt, x, y, jump, sprint, s, speed_factor=1.0):
        height = s.body_height
        radius = min(s.radius, height*.49)
        direction = Vector((math.cos(self.yaw)*x-math.sin(self.yaw)*y,
                            math.sin(self.yaw)*x+math.cos(self.yaw)*y, 0))
        if not s.gravity:
            forward = Vector((-math.sin(self.yaw)*math.cos(self.pitch),
                              math.cos(self.yaw)*math.cos(self.pitch), math.sin(self.pitch)))
            right = Vector((math.cos(self.yaw), math.sin(self.yaw), 0))
            direction = right*x+forward*y
        if direction.length > 1:
            direction.normalize()
        move_speed = s.speed if s.gravity else getattr(s, 'fly_speed', 6.0)
        delta = direction*move_speed*(s.sprint_multiplier if sprint else 1)*dt*speed_factor
        # Sweep in small increments to avoid crossing thin walls between frames.
        steps = max(1, math.ceil(delta.length/max(.025, radius*.4)))
        for _ in range(steps):
            candidate = self.feet+delta/steps
            resolved = world.resolve(candidate, height, radius)
            blocked = (resolved.xy-candidate.xy).length > .002
            if blocked and self.grounded and s.gravity:
                raised = candidate+UP*s.step_height
                raised_resolved = world.resolve(raised, height, radius)
                if (raised_resolved.xy-raised.xy).length < .002:
                    ground = world.floor(raised_resolved, .02, s.step_height+.05)
                    if ground is not None and ground >= self.feet.z-.04:
                        raised_resolved.z = ground+.002
                        resolved = raised_resolved
            self.feet = resolved
        if not s.gravity:
            self.vz = 0
            self.grounded = False
            return
        if jump and self.grounded:
            self.vz = s.jump_speed
            self.grounded = False
        if self.vz <= 0:
            ground = world.floor(self.feet, .04, .16 if self.grounded else .025)
            if ground is not None and self.feet.z-ground <= (.17 if self.grounded else .03):
                self.feet.z = ground+.002
                self.vz = 0
                self.grounded = True
                self.safe = self.feet.copy()
                return
        self.grounded = False
        self.vz -= s.gravity_strength*dt
        dz = self.vz*dt
        substeps = max(1, math.ceil(abs(dz)/max(.025, radius*.4)))
        for _ in range(substeps):
            before = self.feet.copy()
            candidate = before+UP*(dz/substeps)
            # Downward sweep against ground prevents floor tunneling.
            if dz <= 0:
                ground = world.floor(before, .025, abs(dz/substeps)+.03)
                if ground is not None and candidate.z <= ground+.002:
                    self.feet.z = ground+.002
                    self.vz = 0
                    self.grounded = True
                    self.safe = self.feet.copy()
                    break
            resolved = world.resolve(candidate, height, radius)
            self.feet = resolved
            if dz > 0 and resolved.z < candidate.z-.001:
                self.vz = 0
                break
        if self.feet.z < self.safe.z-100:
            self.feet = self.safe.copy()
            self.vz = 0


class RWSettings(bpy.types.PropertyGroup):
    mode: EnumProperty(name='Input', items=[('GAMEPAD', 'Xbox / Gamepad', 'Mouse and keyboard remain available for modeling'), ('KEYBOARD', 'Keyboard + Mouse', 'WASD and mouse look; Esc exits')], default='GAMEPAD')
    eye_height: FloatProperty(name='Eye Height', default=1.60, min=.3, max=3, subtype='DISTANCE')
    body_height: FloatProperty(name='Body Height', default=1.70, min=.6, max=4, subtype='DISTANCE')
    radius: FloatProperty(name='Body Radius', default=.24, min=.1, max=1, subtype='DISTANCE')
    speed: FloatProperty(name='Walk Speed (m/s)', default=3.5, min=.1, max=20)
    fly_speed: FloatProperty(name='Fly Speed (m/s)', default=6.0, min=.1, max=100)
    sprint_multiplier: FloatProperty(name='Sprint Multiplier', default=2, min=1, max=5)
    step_height: FloatProperty(name='Step Height', default=.28, min=0, max=1, subtype='DISTANCE')
    gravity: BoolProperty(name='Gravity', default=True)
    gravity_strength: FloatProperty(name='Gravity (m/s²)', default=9.81, min=0, max=30)
    jump_speed: FloatProperty(name='Jump Speed', default=3.8, min=.1, max=10)
    look_speed: FloatProperty(name='Stick Look Speed', default=1.7, min=.1, max=6)
    sensitivity: FloatProperty(name='Mouse Sensitivity', default=.0025, min=.0001, max=.02, precision=4)
    deadzone: FloatProperty(name='Stick Deadzone', default=.18, min=.02, max=.8)
    invert_y: BoolProperty(name='Invert Stick Y', default=False)
    ignore_collection: PointerProperty(name='Ignore Collisions', type=bpy.types.Collection)
    auto_refresh: BoolProperty(name='Refresh After Modeling', description='Rebuild after edits; large scenes may pause while rebuilding. Use X or Refresh Collisions for manual updates', default=False)
    spawn: EnumProperty(name='Start From', items=[('VIEW', 'Current View', 'Start at current viewport eye position'), ('HUMAN', '1.70 m Reference', 'Start at reference figure position and snap to ground'), ('CURSOR', '3D Cursor', 'Use cursor as feet position and snap to ground')], default='VIEW')


class Runtime:
    def __init__(self, context, mode):
        self.window = context.window
        self.area = context.area
        self.space = context.space_data
        self.scene = context.scene
        self.mode = mode
        self.world = CollisionWorld()
        self.bridge = None
        self.paused = False
        self.previous_buttons = {}
        self.sprinting = False
        self.last_l3_press = -100.0
        self.stick_idle_since = None
        self.keys = set()
        self.last = time.monotonic()
        self.dirty = False
        self.changed_at = 0
        self.last_build = 0
        self.last_error = ''
        self.manual_view = False
        self.view_signature = None
        self.zoom_active = False
        self.zoom_base_lens = self.space.lens
        self.original_lens = self.space.lens
        self.original_clip = self.space.clip_start
        s = self.scene.roomwalker
        self.world.build(context, s)
        rv = self.space.region_3d
        eye = rv.view_matrix.inverted().translation
        forward = rv.view_rotation @ Vector((0, 0, -1))
        yaw = math.atan2(-forward.x, forward.y)
        pitch = math.asin(max(-1, min(1, forward.z)))
        feet = eye-UP*s.eye_height
        if s.spawn == 'HUMAN':
            human = next((o for o in self.scene.objects if 'v40-HumanReference' in o.name), None)
            if human:
                feet = human.matrix_world.translation.copy()+Vector((.85, 0, 0))
        elif s.spawn == 'CURSOR':
            feet = self.scene.cursor.location.copy()
        if s.spawn != 'VIEW':
            z = self.world.floor(feet, 50, 200)
            if z is not None:
                feet.z = z+.002
        self.player = Player(feet, yaw, pitch)
        self.space.lens = 50
        self.space.clip_start = .03
        rv.view_perspective = 'PERSP'
        if mode == 'GAMEPAD':
            self.bridge = Bridge()
        self.view()

    def view(self):
        p, s = self.player, self.scene.roomwalker
        forward = Vector((-math.sin(p.yaw)*math.cos(p.pitch), math.cos(p.yaw)*math.cos(p.pitch), math.sin(p.pitch)))
        rv = self.space.region_3d
        rv.view_perspective = 'PERSP'
        rv.view_rotation = forward.to_track_quat('-Z', 'Y')
        rv.view_distance = 0
        rv.view_location = p.feet+UP*s.eye_height
        self.view_signature = self.signature()
        self.area.tag_redraw()

    def signature(self):
        rv = self.space.region_3d
        return tuple(rv.view_location)+tuple(rv.view_rotation)+(rv.view_distance,)

    def adopt_external_view(self):
        current = self.signature()
        if self.view_signature is None or any(abs(a-b)>1e-5 for a,b in zip(current, self.view_signature)):
            rv = self.space.region_3d
            # Read editable view properties directly; view_matrix can lag one redraw.
            eye = rv.view_location + rv.view_rotation @ Vector((0, 0, rv.view_distance))
            forward = rv.view_rotation @ Vector((0, 0, -1))
            self.player.feet = eye-UP*self.scene.roomwalker.eye_height
            self.player.yaw = math.atan2(-forward.x, forward.y)
            self.player.pitch = math.asin(max(-1, min(1, forward.z)))
            self.player.vz = 0
            self.player.grounded = False
            self.player.safe = self.player.feet.copy()
            self.view_signature = current
            self.manual_view = True
            return True
        return False

    def tick(self):
        global _status
        now = time.monotonic()
        dt = min(.05, max(.001, now-self.last))
        self.last = now
        if not any(w == self.window for w in bpy.context.window_manager.windows) or self.area.type != 'VIEW_3D':
            stop()
            return None
        s = self.scene.roomwalker
        if self.mode == 'GAMEPAD':
            self.adopt_external_view()
        # Rebuild on idle after edits; avoid rebuilding per mouse movement / per edit-mode vertex.
        if self.dirty and s.auto_refresh and now-self.changed_at > .65 and now-self.last_build > 1.5 and bpy.context.mode == 'OBJECT':
            self.rebuild()
        x = y = 0.0
        jump = sprint = False
        vertical = 0.0
        speed_factor = 1.0
        mode_changed = False
        if self.mode == 'GAMEPAD':
            data = self.bridge.state
            if self.bridge.process.poll() is not None:
                _status = 'Gamepad helper stopped. Stop and restart RoomWalker.'
                return 1/30
            if now-self.bridge.received > .3 or not data.get('connected'):
                _status = 'Waiting for Xbox / gamepad connection…'
                self.area.tag_redraw()
                return 1/30
            _status = ('Paused — Menu to resume' if self.paused else ('Xbox Walk' if s.gravity else 'Xbox Fly'))+' | '+data.get('name', 'Gamepad')
            # Helper can receive background events; only move Blender when it is foreground.
            foreground = data.get('foreground', '').lower()
            if foreground and 'blender' not in foreground:
                return 1/30
            self.apply_zoom(float(data.get('lt', 0)))
            pressed = lambda key: data.get(key, False) and not self.previous_buttons.get(key, False)
            if pressed('menu'):
                self.paused = not self.paused
            if pressed('y') and not self.paused:
                s.gravity = not s.gravity
                self.player.vz = 0
                self.player.grounded = False
                self.manual_view = False
                mode_changed = True
            if pressed('x'):
                self.rebuild()
            jump = pressed('a') if s.gravity else False
            if not s.gravity:
                vertical = float(bool(data.get('a')))-float(bool(data.get('b')))
            self.update_sprint(pressed('l3'), now)

            self.previous_buttons = data.copy()
            if self.paused:
                return 1/60
            x, y = deadzone(data.get('lx', 0), data.get('ly', 0), s.deadzone)
            rx, ry = deadzone(data.get('rx', 0), data.get('ry', 0), s.deadzone)
            self.player.yaw -= rx*s.look_speed*dt
            self.player.pitch += ry*s.look_speed*dt*(-1 if s.invert_y else 1)
            if abs(x)+abs(y) < .001:
                if self.stick_idle_since is None:
                    self.stick_idle_since = now
                elif now-self.stick_idle_since > .25:
                    self.sprinting = False
            else:
                self.stick_idle_since = None
            sprint = self.sprinting
            trigger = max(0.0, min(1.0, float(data.get('rt', 0))))
            if trigger > .03:
                # RT alone drives forward; with the stick, it controls speed in that direction.
                speed_factor = throttle_factor(trigger)
                sprint = False
                self.sprinting = False
                if abs(x)+abs(y) < .001 and not vertical:
                    y = 1.0
        else:
            if self.paused:
                return 1/60
            x = int('D' in self.keys)-int('A' in self.keys)
            y = int('W' in self.keys)-int('S' in self.keys)
            jump = 'JUMP' in self.keys
            self.keys.discard('JUMP')
            sprint = 'LEFT_SHIFT' in self.keys or 'RIGHT_SHIFT' in self.keys
            _status = 'Keyboard walk — Esc to stop'
        self.player.pitch = max(-1.48, min(1.48, self.player.pitch))
        # No inputs while stationary: preserve modeling orbit/zoom until the next stick movement.
        movement = abs(x)+abs(y) > .001 or jump or abs(vertical) > .001 or mode_changed
        look = self.mode == 'GAMEPAD' and (abs(rx)+abs(ry) > .001)
        # Manual orbit/pan/zoom belongs to the editor until actual controller input.
        # Holding a neutral controller must never pull the viewport back or drop it.
        if self.mode == 'GAMEPAD' and self.manual_view and not movement and not look:
            return 1/60
        if movement or look:
            self.manual_view = False
        active = movement or (s.gravity and not self.player.grounded)
        if active or look:
            self.player.step(self.world, dt, x, y, jump, sprint, s, speed_factor)
            if not s.gravity and vertical:
                self.fly_vertical(vertical*s.fly_speed*(s.sprint_multiplier if sprint else 1)*dt*speed_factor, s)
            self.view()
        return 1/60

    def apply_zoom(self, value):
        value = max(0.0, min(1.0, value))
        if value > .03:
            if not getattr(self, 'zoom_active', False):
                self.zoom_base_lens = self.space.lens
                self.zoom_active = True
            self.space.lens = self.zoom_base_lens*(1+(value-.03)/.97)
            self.area.tag_redraw()
        elif getattr(self, 'zoom_active', False):
            self.space.lens = self.zoom_base_lens
            self.zoom_active = False
            self.area.tag_redraw()

    def update_sprint(self, pressed, now):
        if pressed:
            self.sprinting = True

    def fly_vertical(self, distance, s):
        # Substep ascent/descent so flying still respects floor and ceiling.
        steps = max(1, math.ceil(abs(distance)/max(.025, s.radius*.4)))
        for _ in range(steps):
            target = self.player.feet+UP*(distance/steps)
            self.player.feet = self.world.resolve(target, s.body_height, min(s.radius, s.body_height*.49))

    def rebuild(self):
        with bpy.context.temp_override(window=self.window, area=self.area):
            self.world.build(bpy.context, self.scene.roomwalker)
        self.last_build = time.monotonic()
        self.dirty = False

    def close(self):
        self.apply_zoom(0)
        if self.bridge:
            self.bridge.close()
        try:
            self.space.clip_start = self.original_clip
            self.area.tag_redraw()
        except ReferenceError:
            pass


def stop():
    global _runtime, _status
    runtime, _runtime = _runtime, None
    if runtime:
        runtime.close()
    _status = 'Stopped'


def timer():
    global _status
    if _runtime is None:
        return None
    try:
        return _runtime.tick()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        stop()
        _status = 'Stopped: '+str(exc)[:140]
        return None


@persistent
def changed(scene, depsgraph):
    if _runtime and any(u.is_updated_geometry or u.is_updated_transform for u in depsgraph.updates):
        _runtime.dirty = True
        _runtime.changed_at = time.monotonic()


@persistent
def loading(_):
    stop()


class RW_OT_start(bpy.types.Operator):
    bl_idname = 'view3d.roomwalker_start'
    bl_label = 'Start Walking'
    bl_description = 'Start in this viewport; gamepad mode never captures mouse or keyboard'
    _timer = None
    _last_mouse = None

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == 'VIEW_3D' and _runtime is None

    def execute(self, context):
        return self.invoke(context, None)

    def invoke(self, context, event):
        global _runtime, _status
        try:
            _runtime = Runtime(context, context.scene.roomwalker.mode)
        except Exception as exc:
            stop()
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _status = 'Starting…'
        if not bpy.app.timers.is_registered(timer):
            bpy.app.timers.register(timer, first_interval=.02)
        if _runtime.mode == 'KEYBOARD':
            self._window = context.window
            self._area = context.area
            self._last_mouse = (event.mouse_x, event.mouse_y) if event else None
            self._timer = context.window_manager.event_timer_add(.03, window=context.window)
            context.window.cursor_modal_set('CROSSHAIR')
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        return {'FINISHED'}

    def cleanup(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        self._window.cursor_modal_restore()

    def modal(self, context, event):
        if _runtime is None or _runtime.mode != 'KEYBOARD':
            self.cleanup(context)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE', 'WINDOW_DEACTIVATE'}:
            stop()
            self.cleanup(context)
            return {'FINISHED'}
        if event.type == 'MOUSEMOVE':
            if self._last_mouse:
                dx = event.mouse_x-self._last_mouse[0]
                dy = event.mouse_y-self._last_mouse[1]
                _runtime.player.yaw -= dx*context.scene.roomwalker.sensitivity
                _runtime.player.pitch = max(-1.48, min(1.48, _runtime.player.pitch+dy*context.scene.roomwalker.sensitivity))
                _runtime.view()
            self._last_mouse = (event.mouse_x, event.mouse_y)
            # Recenter only near viewport boundary, preventing screen-edge look limits.
            a = self._area
            if event.mouse_x < a.x+35 or event.mouse_x > a.x+a.width-35 or event.mouse_y < a.y+35 or event.mouse_y > a.y+a.height-35:
                center = (a.x+a.width//2, a.y+a.height//2)
                self._last_mouse = center
                self._window.cursor_warp(*center)
        elif event.type in {'W', 'A', 'S', 'D', 'LEFT_SHIFT', 'RIGHT_SHIFT'}:
            if event.value == 'PRESS':
                _runtime.keys.add(event.type)
            elif event.value == 'RELEASE':
                _runtime.keys.discard(event.type)
        elif event.type == 'SPACE' and event.value == 'PRESS':
            _runtime.keys.add('JUMP')
        elif event.type == 'TAB' and event.value == 'PRESS':
            context.scene.roomwalker.gravity = not context.scene.roomwalker.gravity
        return {'RUNNING_MODAL'}


class RW_OT_stop(bpy.types.Operator):
    bl_idname = 'view3d.roomwalker_stop'
    bl_label = 'Stop Walking'
    def execute(self, context):
        stop()
        return {'FINISHED'}


class RW_OT_pause(bpy.types.Operator):
    bl_idname = 'view3d.roomwalker_pause'
    bl_label = 'Pause / Resume'
    def execute(self, context):
        if _runtime:
            _runtime.paused = not _runtime.paused
        return {'FINISHED'}


class RW_OT_refresh(bpy.types.Operator):
    bl_idname = 'view3d.roomwalker_refresh'
    bl_label = 'Refresh Collisions'
    def execute(self, context):
        if _runtime:
            _runtime.rebuild()
            self.report({'INFO'}, f'{_runtime.world.triangles:,} collision triangles')
        return {'FINISHED'}


class RW_PT_panel(bpy.types.Panel):
    bl_label = 'RoomWalker'
    bl_idname = 'RW_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'RoomWalker'
    def draw(self, context):
        layout = self.layout
        s = context.scene.roomwalker
        layout.label(text=_status[:65])
        if _runtime:
            row = layout.row(align=True)
            row.operator('view3d.roomwalker_pause', text='Resume' if _runtime.paused else 'Pause')
            row.operator('view3d.roomwalker_stop', text='Stop', icon='CANCEL')
            layout.operator('view3d.roomwalker_refresh', icon='FILE_REFRESH')
            layout.label(text=f'Collision triangles: {_runtime.world.triangles:,}')
        else:
            layout.prop(s, 'mode')
            layout.prop(s, 'spawn')
            layout.operator('view3d.roomwalker_start', icon='PLAY')
        box = layout.box()
        if s.mode == 'GAMEPAD':
            box.label(text='Left stick: move | Right stick: look')
            box.label(text='A: jump | L3 click: sprint')
            box.label(text='Y: walk / fly | Menu: pause')
            box.label(text='RT: throttle | LT: 2x zoom')
            box.label(text='Fly toward look direction')
            box.label(text='Hold A up / B down')
            box.label(text='X: refresh | Stop: panel button')
            box.label(text='Mouse and keyboard stay free')
        else:
            box.label(text='WASD: move | Mouse: look')
            box.label(text='Space: jump | Shift: sprint')
            box.label(text='Tab: gravity | Esc: stop')
        layout.prop(s, 'speed')
        layout.prop(s, 'fly_speed')
        layout.prop(s, 'eye_height')
        layout.prop(s, 'gravity')
        col = layout.column(align=True)
        col.prop(s, 'body_height'); col.prop(s, 'radius'); col.prop(s, 'step_height')
        if s.mode == 'GAMEPAD':
            layout.prop(s, 'deadzone'); layout.prop(s, 'look_speed'); layout.prop(s, 'invert_y')
        layout.prop(s, 'ignore_collection')
        layout.prop(s, 'auto_refresh')


classes = (RWSettings, RW_OT_start, RW_OT_stop, RW_OT_pause, RW_OT_refresh, RW_PT_panel)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.roomwalker = PointerProperty(type=RWSettings)
    bpy.app.handlers.depsgraph_update_post.append(changed)
    bpy.app.handlers.load_pre.append(loading)


def unregister():
    stop()
    if bpy.app.timers.is_registered(timer):
        bpy.app.timers.unregister(timer)
    for collection, handler in [(bpy.app.handlers.depsgraph_update_post, changed), (bpy.app.handlers.load_pre, loading)]:
        if handler in collection:
            collection.remove(handler)
    del bpy.types.Scene.roomwalker
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
