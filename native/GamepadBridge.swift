import Foundation
import GameController
import AppKit

GCController.shouldMonitorBackgroundEvents = true
GCController.startWirelessControllerDiscovery(completionHandler: nil)
let parent = getppid()
let timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { _ in
    if getppid() != parent { exit(0) }
    let controller = GCController.controllers().first { $0.extendedGamepad != nil }
    let foreground = NSWorkspace.shared.frontmostApplication?.bundleIdentifier ?? ""
    var state: [String: Any] = ["connected": controller != nil, "foreground": foreground, "time": Date().timeIntervalSince1970]
    if let c = controller, let g = c.extendedGamepad {
        state["name"] = c.vendorName ?? "Gamepad"
        state["lx"] = g.leftThumbstick.xAxis.value
        state["ly"] = g.leftThumbstick.yAxis.value
        state["rx"] = g.rightThumbstick.xAxis.value
        state["ry"] = g.rightThumbstick.yAxis.value
        state["a"] = g.buttonA.isPressed
        state["b"] = g.buttonB.isPressed
        state["x"] = g.buttonX.isPressed
        state["y"] = g.buttonY.isPressed
        state["lb"] = g.leftShoulder.isPressed
        state["rb"] = g.rightShoulder.isPressed
        state["lt"] = g.leftTrigger.value
        state["rt"] = g.rightTrigger.value
        state["menu"] = g.buttonMenu.isPressed
        state["l3"] = g.leftThumbstickButton?.isPressed ?? false
        state["r3"] = g.rightThumbstickButton?.isPressed ?? false
    }
    if let data = try? JSONSerialization.data(withJSONObject: state), let line = String(data: data, encoding: .utf8) {
        print(line)
        fflush(stdout)
    }
}
RunLoop.main.run()
