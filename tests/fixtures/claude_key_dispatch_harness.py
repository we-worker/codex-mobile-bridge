#!/usr/bin/env python3
"""Run the production Connector.key body with fake CGEvents and focus checks."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT/'bridge/platforms/macos/claude-helper.swift').read_text()
actual = source[source.index('    func key(_ code: CGKeyCode'):source.index('    func developerMode()')]
fixture = r'''import Foundation
typealias CGKeyCode = Int
struct CGEventFlags: OptionSet {
    let rawValue: Int
    static let maskCommand = CGEventFlags(rawValue: 1)
}
struct AXUIElement {}
struct SetupError: Error { let state: String }
func fail(_ state: String, _ reason: String) throws -> Never { throw SetupError(state: state) }
enum Tap { case cghidEventTap }
final class Scenario {
    var events = [String]()
    var checks = 0
    var loseFocusAt: Int?
    var loseFocusOnDown = false
    var failUpCreation = false
}
var scenario = Scenario()
final class CGEvent {
    let down: Bool
    var flags: CGEventFlags = []
    init?(keyboardEventSource: Any?, virtualKey: CGKeyCode, keyDown: Bool) {
        if !keyDown && scenario.failUpCreation { return nil }
        down = keyDown
    }
    func post(tap: Tap) {
        precondition(flags == .maskCommand)
        scenario.events.append(down ? "hid-down" : "hid-up")
        if down && scenario.loseFocusOnDown { scenario.loseFocusAt = scenario.checks + 1 }
    }
    func postToPid(_ pid: Int32) {
        precondition(flags == .maskCommand)
        scenario.events.append(down ? "pid-down" : "pid-up")
    }
}
struct FakeApp { let processIdentifier: Int32 = 42 }
final class Connector {
    let app = FakeApp()
    func check(_ prompt: AXUIElement? = nil) throws {
        scenario.checks += 1
        if scenario.loseFocusAt == scenario.checks { try fail("needs-attention", "focus changed") }
    }
__KEY__
}
func run(_ name: String, prompt: Bool, loseFocusAt: Int? = nil, loseFocusOnDown: Bool = false,
         failUpCreation: Bool = false, expected: [String], throwsError: Bool = false) {
    scenario = Scenario()
    scenario.loseFocusAt = loseFocusAt
    scenario.loseFocusOnDown = loseFocusOnDown
    scenario.failUpCreation = failUpCreation
    var failed = false
    do { try Connector().key(126, flags: .maskCommand, prompt: prompt ? AXUIElement() : nil) }
    catch let issue as SetupError { failed = issue.state == "needs-attention" }
    catch { fatalError(name + ": unexpected error") }
    precondition(failed == throwsError, name + ": error state")
    precondition(scenario.events == expected, name + ": " + String(describing: scenario.events))
    print(name + ": " + scenario.events.joined(separator: ","))
}
run("prompt", prompt: true, expected: ["hid-down", "hid-up"])
run("app-shortcut", prompt: false, expected: ["pid-down", "pid-up"])
run("focus-lost-before-dispatch", prompt: true, loseFocusAt: 1, expected: [], throwsError: true)
run("focus-lost-after-down", prompt: true, loseFocusOnDown: true,
    expected: ["hid-down", "hid-up"], throwsError: true)
run("up-creation-failed", prompt: true, failUpCreation: true, expected: [], throwsError: true)
'''.replace('__KEY__', actual)

(ROOT/'.tmp').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
    folder = Path(folder)
    script = folder/'key-dispatch.swift'
    script.write_text(fixture)
    result = subprocess.run(['swift', '-module-cache-path', str(folder/'modules'), str(script)],
                            capture_output=True, text=True, timeout=90)
    print(result.stdout, end='')
    if result.returncode:
        print(result.stderr, end='')
        raise SystemExit(result.returncode)
