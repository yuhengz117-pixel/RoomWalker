# RoomWalker

**Explore your Blender scene with an Xbox controller while keeping your mouse and keyboard free for modeling.**

RoomWalker is a small, free, open-source Blender add-on for first-person architectural walkthroughs and spatial design. Walk with gravity and collision detection, switch to flight, control movement speed with the right trigger, and zoom with the left trigger.

**Prototype release · v0.1.7 · MIT license**

[Download the latest release](https://github.com/yuhengz117-pixel/RoomWalker/releases/latest) · [Report a bug](https://github.com/yuhengz117-pixel/RoomWalker/issues)

## Why RoomWalker?

When reviewing a large space, switching between orbit navigation and editing interrupts the workflow. RoomWalker lets one hand navigate with a gamepad while the mouse and keyboard stay available for selecting and modifying geometry. A separate keyboard-and-mouse mode is also included.

- First-person walking with gravity, jumping, wall sliding, and step handling.
- Collision-aware flight that follows your viewing direction.
- Analog **RT throttle**: squeeze gently for precise movement or fully for faster travel.
- Analog **LT zoom**, up to **2×**, with the original focal length restored on release.
- One-click **L3 sprint**, plus adjustable walk and fly speeds.
- Manual viewport navigation is preserved; using the controller continues from your current view.
- Collision cache refresh after modeling changes, with an optional automatic refresh mode.
- Local operation through Apple's GameController framework; no account, telemetry, or network service in the add-on.

## Compatibility

| Component | Status |
| --- | --- |
| Blender | Tested in **5.1.2**; declares minimum **4.5**, other versions unverified |
| macOS Apple Silicon | Tested; gamepad helper included in the release ZIP |
| Xbox controller | Physical connection detected on the test Mac; interaction iterated in a real modeling workflow |
| Other compatible gamepads | May work through Apple's extended-gamepad API; unverified |
| Windows / Linux | Gamepad backend **not included**; keyboard mode not tested on these platforms |

## Install

1. Download **roomwalker-0.1.7-macos-arm64.zip** from [Releases](https://github.com/yuhengz117-pixel/RoomWalker/releases/latest). Use the release asset rather than GitHub's generic source archive.
2. In Blender, open **Edit → Preferences → Add-ons**.
3. Open the menu arrow and choose **Install from Disk…**, then select the ZIP.
4. Enable **RoomWalker — Keyboard & Xbox**.
5. In the 3D Viewport press **N**, then open the **RoomWalker** sidebar tab.
6. Choose an input mode and **Start From**, then click **Start Walking**.

The native helper is a local, ad-hoc-signed Apple Silicon executable. It is not Apple-notarized. If macOS prevents it from running, you can build it yourself from the included Swift source. Do not disable system security protections.

## Xbox controls

| Control | Action |
| --- | --- |
| Left stick | Move / strafe |
| Right stick | Look around |
| L3 — click left stick once | Sprint; stop moving briefly to reset |
| A | Jump when walking; hold to ascend when flying |
| B | Hold to descend when flying |
| Y | Toggle walking / flight |
| RT | Analog throttle; alone, drive forward along the view direction |
| LT | Hold for analog zoom, up to 2×; release to restore |
| X | Rebuild collisions after editing geometry |
| Menu / ≡ | Pause / resume navigation |
| Sidebar **Stop** | End the session |

When RT and the left stick are both used, the stick sets direction and RT sets speed. RT overrides sprint so the two accelerators do not stack. Look upward and move forward to fly upward; look downward to descend. A/B also provide direct vertical movement.

Default walk speed is **3.5 m/s**, default fly speed **6 m/s**. L3 doubles the base speed; full RT also reaches twice the base speed, while a light squeeze permits slower movement. Both base speeds can be adjusted in the sidebar.

Mouse and keyboard input is **not captured in gamepad mode**. For precise modeling, press Menu to pause, edit normally, then resume. Navigation pauses while Blender is not the foreground application. Reconnecting a controller resumes input.

## Keyboard and mouse controls

Choose **Keyboard + Mouse** in the sidebar before starting.

| Control | Action |
| --- | --- |
| WASD | Move |
| Mouse | Look |
| Shift | Sprint |
| Space | Jump |
| Tab | Toggle gravity |
| Esc / right mouse button | Stop, keeping the current view |

Keyboard mode captures viewport input while active. Use gamepad mode to edit and navigate concurrently. Dedicated vertical flight controls are currently gamepad-only.

## Starting position and scale

- **Current View**: start from the viewport's current eye position. Recommended for general scenes.
- **3D Cursor**: use the cursor as the feet position and search for a floor below it.
- **1.70 m Reference**: an optional compatibility preset for the original project's reference figure; use Current View or 3D Cursor in other files.

The defaults are **1.60 m eye height**, **1.70 m body height**, **0.24 m body radius**, and **0.28 m step height**. The implementation assumes **1 Blender unit = 1 metre**. Scene unit-scale conversion is not implemented.

Cursor/reference spawning searches downward from 50 units above the chosen point, so it can pick an upper floor in multilevel scenes. Use Current View for precise placement. RoomWalker does not resize or move your models.

## Collisions and editing

RoomWalker builds a BVH from visible evaluated geometry, including supported mesh/curve objects and instances. Hidden geometry, wire/bounds display objects, reference figures, objects with `roomwalker_ignore = True`, and objects in **Ignore Collisions** are excluded.

The collision cache is a snapshot. After changing geometry or transforms, press **X** on the controller or **Refresh Collisions** in the panel. Undo/redo also requires a refresh. Automatic refresh is off by default; it waits for Object Mode and a short idle interval when enabled.

Large scenes can pause while the cache rebuilds. In one local test scene, about **7.94 million triangles** took roughly **7.5 seconds** to build; this is an example, not a performance guarantee. Simpler collision proxies are preferable for dense scenes.

### Known limitations

- Experimental navigation controller, not a full rigid-body game engine. Objects cannot be pushed.
- Capsule collision is approximated with overlapping sphere samples, movement substeps, and ground ray casts. Tight corners, thin/open geometry, inconsistent normals, or overlapping surfaces may need simpler colliders.
- Collision building is synchronous and can briefly block the UI.
- Controller choice uses the first supported extended gamepad. Multiple-controller selection is not implemented.
- The built-in keyboard flight mode has no dedicated ascend/descend keys.
- Settings save with the `.blend`, but navigation never auto-starts on file open. Stop/disable/file-load ends the helper session; the helper also exits when its parent process exits.

## Build the gamepad helper

Requires macOS and Xcode Command Line Tools:

```sh
xcrun swiftc -swift-version 5 -O \
  -framework GameController -framework AppKit \
  native/GamepadBridge.swift -o native/gamepad_bridge
```

The helper reads controller input through Apple's GameController framework and streams JSON locally to Blender. Its background monitoring lets it serve the foreground Blender process; navigation ignores input while another app is foreground. Swift source is included for inspection.

## Package and test

Build an installable ZIP from the repository root:

```sh
python3 build_release.py
```

Run tests in Blender's Python Console (replace the path with your checkout):

```python
import runpy
runpy.run_path('/absolute/path/to/RoomWalker/test_roomwalker.py')
```

The test script loads this checkout without registering the add-on. It creates synthetic collision data and does not modify the scene. Tests cover gravity, floor landing, jumping, thin walls, wall sliding, small/tall steps, ceiling collision, deadzones, flight direction, throttle, L3 activation, and LT zoom. Test results do not replace testing with your actual controller and scene.

## Contributing

Bug reports and pull requests are welcome. Include Blender/macOS version, controller model, reproduction steps, and a small example scene you are allowed to share. Please avoid uploading proprietary project files or personal data.

This project was developed with AI assistance. The project owner directed the interaction design and iterated through real Blender usage; implementation and automated checks were AI-assisted.

## License

[MIT](LICENSE). This is an independent project and is not affiliated with OmniStep, Epic Games, Microsoft, or the Blender Foundation. Xbox is used only to describe controller compatibility.

## 中文简介

RoomWalker 是一个免费的 Blender 第一人称漫游插件：用 Xbox 手柄移动和观察，同时继续用鼠标键盘建模。支持步行碰撞、重力、飞行、RT 油门调速和 LT 两倍放大。

安装：从 Releases 下载插件 ZIP，在 Blender 的 **Edit → Preferences → Add-ons → Install from Disk** 安装，然后在视口右侧 **N → RoomWalker** 启动。当前主要测试环境为 **Mac Apple Silicon + Blender 5.1.2**。修改模型后按手柄 **X** 刷新碰撞；场景很大时刷新会短暂等待。
