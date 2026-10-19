#!/usr/bin/env python3
"""Compile the production console() method against deterministic fake AX state."""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "bridge/platforms/macos/claude-helper.swift").read_text()


def extract(start, end):
    return SOURCE[SOURCE.index(start):SOURCE.index(end)]


SWIFT = r'''
import Foundation
import CoreFoundation

struct SetupError: Error { let state: String; let reason: String }
func fail(_ state: String, _ reason: String) throws -> Never { throw SetupError(state: state, reason: reason) }

struct Date: Comparable {
    let time: Double
    init() { time = Double(scenario.tick) * 0.25 }
    init(_ time: Double) { self.time = time }
    func addingTimeInterval(_ seconds: Double) -> Date { Date(time + seconds) }
    static func < (lhs: Date, rhs: Date) -> Bool { lhs.time < rhs.time }
}
enum Thread { static func sleep(forTimeInterval: Double) { scenario.tick += 1 } }
struct Flags: OptionSet {
    let rawValue: Int
    static let maskCommand = Flags(rawValue: 1)
    static let maskAlternate = Flags(rawValue: 2)
}
let kAXFocusedWindowAttribute = "AXFocusedWindow"
let kAXWindowsAttribute = "AXWindows"
let kAXChildrenAttribute = "AXChildren"
let kAXRoleAttribute = "AXRole"
let kAXTitleAttribute = "AXTitle"
let kAXIdentifierAttribute = "AXIdentifier"
let kAXDescriptionAttribute = "AXDescription"
let kAXPressAction = "AXPress" as CFString

final class AXUIElement {
    let id: String
    let role: String
    let title: String
    let description: String
    let owner: pid_t
    init(_ id: String, _ role: String = "", _ title: String = "", _ description: String = "", _ owner: pid_t = 42) {
        self.id = id; self.role = role; self.title = title; self.description = description; self.owner = owner
    }
}
func CFEqual(_ a: AXUIElement, _ b: AXUIElement) -> Bool { a === b }
enum AXResult { case success, failure }
func AXUIElementGetPid(_ element: AXUIElement, _ pid: inout pid_t) -> AXResult { pid = element.owner; return .success }
func AXUIElementPerformAction(_ element: AXUIElement, _ action: CFString) -> AXResult {
    scenario.tabPresses += 1
    return scenario.name == "tab_press_rejected" ? .failure : .success
}
func AXUIElementSetAttributeValue(_ element: AXUIElement, _ name: CFString, _ value: CFTypeRef) -> AXResult {
    precondition(element === scenario.root && scenario.activated)
    precondition(CFEqual(name, "AXManualAccessibility" as CFString))
    precondition(CFEqual(value, kCFBooleanTrue))
    scenario.manualCalls += 1
    if scenario.name == "cold_ax_unsupported" { return .failure }
    scenario.manualEnabled = true
    return .success
}
final class Scenario {
    let name: String
    var tick = 0
    var hotkeys = 0
    var tabPresses = 0
    var manualCalls = 0
    var manualEnabled = false
    var activated = false
    var root = AXUIElement("root")
    var main = AXUIElement("main", "AXWindow", "Claude")
    var dev = AXUIElement("dev", "AXWindow", "Developer Tools - app://localhost/epitaxy?coldLaunch=1")
    var prompt = AXUIElement("prompt", "AXTextArea", "", "Console prompt")
    var tab = AXUIElement("tab", "AXRadioButton", "", "Console")
    init(_ name: String) {
        self.name = name
        if name == "other_app_refocus" { dev = AXUIElement("dev", "AXWindow", "Developer Tools", "", 99) }
        if name == "ordinary_refocus" { dev = AXUIElement("dev", "AXWindow", "Claude") }
        if name == "ambiguous_refocus" { dev = AXUIElement("dev", "AXWindow", "Developer Tools Preview") }
    }
    var focused: AXUIElement {
        switch name {
        case "existing_open_focused", "cold_ax_unsupported": return dev
        case "existing_open_refocus", "other_app_refocus", "ordinary_refocus", "ambiguous_refocus": return tick >= 1 ? dev : main
        case "late_window": return tick >= 3 ? dev : main
        case "late_subtree", "focus_loss", "lost_prompt", "no_prompt", "tab_press_rejected", "cold_ax_off": return tick >= 1 ? dev : main
        case "focused_stale": return main
        default: return main
        }
    }
    var windows: [AXUIElement] {
        switch name {
        case "existing_open_focused", "existing_open_refocus", "other_app_refocus", "ordinary_refocus", "ambiguous_refocus": return [main, dev]
        default: return [main]
        }
    }
    var promptVisible: Bool {
        switch name {
        case "late_window": return tick >= 3
        case "late_subtree": return tick >= 4
        case "existing_open_focused", "existing_open_refocus", "other_app_refocus", "ordinary_refocus", "ambiguous_refocus", "focused_stale", "cold_ax_unsupported": return true
        case "cold_ax_off": return manualEnabled && tick >= 1
        case "lost_prompt": return tick == 1
        default: return false
        }
    }
}
let scenario = Scenario(CommandLine.arguments[1])
func attribute(_ element: AXUIElement, _ name: String) -> Any? {
    if element === scenario.root {
        if name == kAXFocusedWindowAttribute { return scenario.focused }
        if name == kAXWindowsAttribute { return scenario.windows }
    }
    if name == kAXChildrenAttribute {
        if scenario.name == "cold_ax_off" && !scenario.manualEnabled { return [AXUIElement]() }
        if element === scenario.dev { return scenario.promptVisible ? [scenario.prompt, scenario.tab] : [scenario.tab] }
        return [AXUIElement]()
    }
    switch name {
    case kAXRoleAttribute: return element.role
    case kAXTitleAttribute: return element.title
    case kAXDescriptionAttribute: return element.description
    case kAXIdentifierAttribute: return ""
    default: return nil
    }
}
func text(_ element: AXUIElement, _ name: String) -> String { attribute(element, name) as? String ?? "" }
func child(_ element: AXUIElement, _ name: String) -> AXUIElement? { attribute(element, name) as? AXUIElement }
func children(_ element: AXUIElement) -> [AXUIElement] { attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? [] }

__FIND__
__DEVTOOLS__

struct FakeApp { let processIdentifier: pid_t = 42 }
final class Connector {
    let app = FakeApp()
    var root: AXUIElement { scenario.root }
    func activate() throws { scenario.activated = true }
    func check() throws {
        if scenario.name == "focus_loss" && scenario.tick >= 2 {
            try fail("needs-attention", "焦点已离开 Claude，自动连接已停止，请重试")
        }
    }
    func checkWindow(_ window: AXUIElement) throws {
        try check()
        if !CFEqual(window, scenario.focused) { try fail("needs-attention", "Claude 窗口已改变") }
    }
    func key(_ code: Int, flags: Flags = []) throws { scenario.hotkeys += 1 }
__CONSOLE__
}

do {
    let found = try Connector().console()
    let foundAt = scenario.tick
    scenario.tick += 1
    print("result=success prompt=\(found.id) tick=\(foundAt) hotkeys=\(scenario.hotkeys) tabPresses=\(scenario.tabPresses) manualCalls=\(scenario.manualCalls) promptNextTick=\(scenario.promptVisible)")
} catch let error as SetupError {
    print("result=\(error.state) reason=\(error.reason) tick=\(scenario.tick) hotkeys=\(scenario.hotkeys) tabPresses=\(scenario.tabPresses) manualCalls=\(scenario.manualCalls)")
} catch { print("result=unexpected \(error)"); exit(2) }
'''


def main():
    code = SWIFT.replace("__FIND__", extract("func find(", "func submissionAccepted("))
    code = code.replace("__DEVTOOLS__", extract("func devToolsWindow(", "func contents("))
    code = code.replace("__CONSOLE__", extract("    func console() throws", "    func verify("))
    expected = {
        "late_window": "result=success prompt=prompt tick=3",
        "late_subtree": "result=success prompt=prompt tick=4",
        "focus_loss": "result=needs-attention reason=焦点已离开 Claude",
        "existing_open_focused": "result=success prompt=prompt tick=0",
        "existing_open_refocus": "result=success prompt=prompt tick=1",
        "other_app_refocus": "result=needs-attention reason=Claude 窗口已改变",
        "ordinary_refocus": "result=needs-attention reason=Claude 窗口已改变",
        "ambiguous_refocus": "result=needs-attention reason=Claude 窗口已改变",
        "focused_stale": "result=failed reason=未找到 Claude Console",
        "no_prompt": "result=failed reason=未找到 Claude Console",
        "tab_press_rejected": "result=failed reason=未找到 Claude Console",
        "lost_prompt": "result=success prompt=prompt tick=1",
        "cold_ax_off": "result=success prompt=prompt tick=1",
        "cold_ax_unsupported": "result=success prompt=prompt tick=0",
    }
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as folder:
        folder = pathlib.Path(folder)
        out, binary = folder / "console-ax.swift", folder / "console-ax"
        out.write_text(code)
        subprocess.run(["swiftc", "-suppress-warnings", "-module-cache-path", str(folder / "modules"),
                        str(out), "-o", str(binary)], check=True)
        for name in sys.argv[1:] or [
            "late_window", "late_subtree", "focus_loss", "existing_open_focused",
            "existing_open_refocus", "other_app_refocus", "ordinary_refocus", "ambiguous_refocus",
            "focused_stale", "no_prompt", "tab_press_rejected", "lost_prompt",
            "cold_ax_off", "cold_ax_unsupported",
        ]:
            result = subprocess.run([str(binary), name], capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            assert expected[name] in output, (name, output)
            if name == "lost_prompt":
                assert "promptNextTick=false" in output, output
            if name in ("cold_ax_off", "cold_ax_unsupported"):
                assert "manualCalls=1" in output, output
            print(name + ": " + output)


if __name__ == "__main__":
    main()
