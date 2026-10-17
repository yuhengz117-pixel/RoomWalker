"""Run inside Blender. Tests use synthetic BVHs and never modify the scene."""
from types import SimpleNamespace
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location('roomwalker_public_test', Path(__file__).with_name('__init__.py'))
rw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rw)

s=SimpleNamespace(radius=.24,body_height=1.7,speed=2.2,sprint_multiplier=2,step_height=.28,gravity=True,jump_speed=3.8,gravity_strength=9.81)

def world(boxes=()):
    v=[(-20,-20,0),(20,-20,0),(20,20,0),(-20,20,0)]
    f=[(0,1,2),(0,2,3)]
    for low,high in boxes:
        x,y,z=low;X,Y,Z=high;b=len(v)
        v.extend([(x,y,z),(X,y,z),(X,Y,z),(x,Y,z),(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)])
        for q in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:
            f.extend([(b+q[0],b+q[1],b+q[2]),(b+q[0],b+q[2],b+q[3])])
    return rw.CollisionWorld(BVHTree.FromPolygons(v,f,all_triangles=True))

def advance(p,w,frames,x=0,y=0,jump=False,sprint=False):
    for i in range(frames):p.step(w,1/60,x,y,jump and i==0,sprint,s)
    return p

checks={}
w=world([((2,-10,0),(2.05,10,5))])
p=advance(rw.Player((0,0,2)),w,180)
checks['gravity_lands']=abs(p.feet.z-.002)<.005 and p.grounded
advance(p,w,180,x=1)
checks['thin_wall_stops_walk']=1.70<p.feet.x<1.77
advance(p,w,120,x=1,y=1,sprint=True)
checks['wall_slide_without_tunneling']=p.feet.x<1.77 and p.feet.y>4
p=advance(rw.Player((0,0,.002)),world(),2)
z=p.feet.z
advance(p,world(),12,jump=True)
checks['jump_rises']=p.feet.z>z+.3
advance(p,world(),180)
checks['jump_lands']=p.grounded and abs(p.feet.z-.002)<.005
w=world([((-2,2,0),(2,5,.18))])
p=advance(rw.Player((0,0,.002)),w,2)
advance(p,w,90,y=1)
checks['climbs_small_step']=p.feet.y>2.5 and .17<p.feet.z<.20
w=world([((-2,2,0),(2,5,.8))])
p=advance(rw.Player((0,0,.002)),w,2)
advance(p,w,120,y=1)
checks['tall_step_blocks']=p.feet.y<1.78
w=world([((-3,-3,2),(3,3,2.1))])
p=advance(rw.Player((0,0,.002)),w,2)
maxhead=0
for i in range(60):
 p.step(w,1/60,0,0,i==0,False,s)
 maxhead=max(maxhead,p.feet.z+1.7)
checks['ceiling_blocks_jump']=maxhead<2.01
checks['deadzone_zero']=rw.deadzone(.05,.05,.18)==(0,0)
checks['full_stick_normalized']=abs(sum(v*v for v in rw.deadzone(1,1,.18))-1)<1e-6
result={'checks':checks,'all_passed':all(checks.values()),'max_head_z':maxhead}

# Flight follows view pitch and throttle scales translation.
s.gravity=False
s.fly_speed=6
p=rw.Player((0,0,2),0,.785398)
for _ in range(60):p.step(world(),1/60,0,1,False,False,s)
checks['flight_ascends_with_pitch']=p.feet.z>6
p=rw.Player((0,0,8),0,-.785398)
for _ in range(60):p.step(world(),1/60,0,1,False,False,s)
checks['flight_descends_with_pitch']=p.feet.z<4
p=rw.Player((0,0,3));empty=rw.CollisionWorld()
for _ in range(60):p.step(empty,1/60,0,1,False,False,s,rw.throttle_factor(1))
checks['full_RT_12_mps']=abs(p.feet.y-12)<.001
checks['RT_progressive']=rw.throttle_factor(.15)<rw.throttle_factor(.5)<rw.throttle_factor(1)
runtime=rw.Runtime.__new__(rw.Runtime)
runtime.sprinting=False
runtime.update_sprint(True,0)
checks['single_L3_sprints']=runtime.sprinting
runtime.space=SimpleNamespace(lens=50.0)
runtime.area=SimpleNamespace(tag_redraw=lambda:None)
runtime.zoom_active=False
runtime.apply_zoom(1)
checks['LT_2x_zoom']=runtime.space.lens==100
runtime.apply_zoom(0)
checks['LT_release_restores']=runtime.space.lens==50
result={'checks':checks,'all_passed':all(checks.values()),'count':len(checks)}
if not result['all_passed']:
    raise AssertionError(result)
print(result)
