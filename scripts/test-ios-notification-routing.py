#!/usr/bin/env python3
"""Compile and exercise the notification routing methods used by AppDelegate."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.tmp/ios-notification-routing-tests'
WORK.mkdir(parents=True, exist_ok=True)
source = (ROOT / 'mobile/ios/BridgePreview/App.swift').read_text()
start = source.index('    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response:')
end = source.index('    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification:', start)
methods = source[start:end]

fixture = r'''
import Foundation

struct UNNotificationRequest { let identifier: String; let content: UNNotificationContent }
struct UNNotificationContent { let userInfo: [String: Any] }
struct UNNotification { let request: UNNotificationRequest }
final class UNNotificationResponse {
    let notification: UNNotification
    let actionIdentifier: String
    init(notification: UNNotification, actionIdentifier: String) {
        self.notification = notification
        self.actionIdentifier = actionIdentifier
    }
}
struct UNUserNotificationCenter {}
final class View { var window: Bool? }
final class BridgeController {
    var viewIfLoaded: View? = View()
    var routes: [String] = []
    func openNotification(_ origin: String, thread: String?, host: String) {
        routes.append(origin + "/" + (thread ?? "") + "/" + host)
    }
}
final class AppDelegate {
    let controller = BridgeController()
    private var pendingNotification: UNNotificationResponse?
    private var lastNotificationRoute: (response: UNNotificationResponse, fromScene: Bool)?
'''
fixture += methods + r'''
}
func response(_ id: String, thread: String = "thread") -> UNNotificationResponse {
    UNNotificationResponse(notification: UNNotification(request: UNNotificationRequest(
        identifier: id, content: UNNotificationContent(userInfo: ["origin": "https://saved.example", "thread": thread, "host": "local"]))),
        actionIdentifier: "default")
}
func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
let center = UNUserNotificationCenter()
let cold = AppDelegate()
let first = response("first")
cold.receiveNotification(first, fromScene: true)
check(cold.controller.routes.isEmpty, "cold response should wait for the window")
cold.controller.viewIfLoaded?.window = true
cold.openPendingNotification()
check(cold.controller.routes.count == 1, "scene response should route once")
cold.userNotificationCenter(center, didReceive: first) {}
RunLoop.main.run(until: Date().addingTimeInterval(0.02))
check(cold.controller.routes.count == 1, "delegate callback should not duplicate scene response")
cold.userNotificationCenter(center, didReceive: response("second")) {}
RunLoop.main.run(until: Date().addingTimeInterval(0.02))
check(cold.controller.routes.count == 2, "a later distinct tap should route")
cold.userNotificationCenter(center, didReceive: response("first", thread: "another")) {}
RunLoop.main.run(until: Date().addingTimeInterval(0.02))
check(cold.controller.routes.count == 3, "a new response for the same notification should route")

let reverse = AppDelegate()
reverse.controller.viewIfLoaded?.window = true
let launch = response("reverse")
reverse.userNotificationCenter(center, didReceive: launch) {}
RunLoop.main.run(until: Date().addingTimeInterval(0.02))
reverse.receiveNotification(launch, fromScene: true)
check(reverse.controller.routes.count == 1, "scene callback should not duplicate delegate response")
reverse.userNotificationCenter(center, didReceive: response("third")) {}
RunLoop.main.run(until: Date().addingTimeInterval(0.02))
check(reverse.controller.routes.count == 2, "later distinct callback should route")
print("iOS notification routing passed")
'''
(WORK / 'main.swift').write_text(fixture)
subprocess.run(['xcrun', 'swiftc', '-module-cache-path', str(WORK / 'cache'), str(WORK / 'main.swift'), '-o', str(WORK / 'notification-routing')], check=True)
subprocess.run([str(WORK / 'notification-routing')], check=True)
