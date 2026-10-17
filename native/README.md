# Native gamepad bridge

GamepadBridge.swift reads Xbox-compatible controller input through Apple GameController and streams JSON to Blender.

Build on macOS:

```sh
xcrun swiftc -swift-version 5 -O -framework GameController -framework AppKit native/GamepadBridge.swift -o native/gamepad_bridge
```

The bundled gamepad_bridge binary targets macOS Apple Silicon.
