// Narrow macOS accessibility bridge for VinciSub. No fixed coordinates or clipboard.
import AppKit
import ApplicationServices
import Foundation

struct Failure: Error { let message: String }
func fail(_ message: String) throws -> Never { throw Failure(message: message) }
func attr(_ e: AXUIElement, _ key: String) -> CFTypeRef? {
    var result: CFTypeRef?
    return AXUIElementCopyAttributeValue(e, key as CFString, &result) == .success ? result : nil
}
func text(_ e: AXUIElement, _ key: String) -> String { attr(e, key) as? String ?? "" }
func descendants(_ root: AXUIElement) -> [AXUIElement] {
    var out = [AXUIElement](), queue = [(root, 0)]
    while !queue.isEmpty && out.count < 12000 {
        let (node, depth) = queue.removeLast()
        if out.contains(where: { CFEqual($0, node) }) { continue }
        out.append(node)
        if depth < 35, let children = attr(node, "AXChildren") as? [AXUIElement] {
            queue.append(contentsOf: children.reversed().map { ($0, depth + 1) })
        }
    }
    return out
}
func unique(_ elements: [AXUIElement], _ names: [String], _ role: String) throws -> AXUIElement {
    let found = elements.filter { text($0, "AXRole") == role &&
        (names.contains(text($0, "AXTitle")) || names.contains(text($0, "AXDescription"))) }
    guard found.count == 1 else { try fail("无法唯一定位界面控件：" + names[0] + "（匹配数 " + String(found.count) + "）") }
    return found[0]
}
func press(_ e: AXUIElement) throws {
    guard AXUIElementPerformAction(e, kAXPressAction as CFString) == .success else { try fail("无法操作达芬奇界面控件。") }
    RunLoop.current.run(until: Date().addingTimeInterval(0.15))
}
func run(_ request: [String: Any]) throws {
    guard AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary) else {
        try fail("需要 macOS 辅助功能权限：请在系统设置 → 隐私与安全性 → 辅助功能中允许VinciSub Helper后重试；尚未写入字幕。")
    }
    guard CGPreflightPostEventAccess() else { try fail("界面助手没有键盘事件权限，请在辅助功能中允许 VinciSub 界面助手后重试。") }
    guard let running = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == "DaVinci Resolve" }) else { try fail("达芬奇未运行。") }
    let app = AXUIElementCreateApplication(running.processIdentifier)
    AXUIElementSetMessagingTimeout(app, 3)
    let command = request["command"] as? String ?? ""
    if command == "preflight" {
        var error: NSDictionary?
        NSAppleScript(source: "tell application \"System Events\" to get count of processes")?.executeAndReturnError(&error)
        if error != nil { try fail("需要允许界面助手控制 System Events：请检查系统设置中的自动化权限后重试；尚未写入字幕。") }
        return
    }
    guard let title = request["project"] as? String else { try fail("缺少项目身份。") }
    let windows = attr(app, "AXWindows") as? [AXUIElement] ?? []
    let mains = windows.filter { text($0,"AXTitle") == title }
    guard mains.count == 1 else { try fail("达芬奇当前项目窗口不匹配，已停止自动定位。") }
    let window = mains[0]
    if command == "activate" {
        running.activate(options: [.activateAllWindows])
        AXUIElementPerformAction(window, kAXRaiseAction as CFString)
        RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        guard running.isActive else { try fail("无法激活达芬奇主窗口。") }
        return
    }
    // Never take focus back after the operation begins: user intervention aborts.
    guard running.isActive else { try fail("达芬奇失去焦点，已停止自动定位。") }
    func checkFocus() throws {
        guard running.isActive, text(window,"AXTitle") == title else { try fail("窗口焦点或项目发生变化。") }
    }
    if command == "select" {
        let inspector = try unique(descendants(window), ["检查器", "Inspector"], "AXCheckBox")
        if (attr(inspector,"AXValue") as? NSNumber)?.intValue == 0 { try press(inspector) }
        guard let bar = attr(app, "AXMenuBar") else { try fail("无法读取达芬奇菜单。") }
        let menuBar = bar as! AXUIElement
        try press(unique(descendants(menuBar), ["工作区", "Workspace"], "AXMenuBarItem"))
        let active = try unique(descendants(menuBar), ["选择活跃的面板", "Active Panel Selection"], "AXMenuItem")
        try press(active)
        try press(unique(descendants(active), ["时间线", "Timeline"], "AXMenuItem"))
        try press(unique(descendants(menuBar), ["时间线", "Timeline"], "AXMenuBarItem"))
        let select = try unique(descendants(menuBar), ["选择片段", "Select Clips"], "AXMenuItem")
        try press(select)
        try press(unique(descendants(select), ["在所有轨道上向前", "Forward on All Tracks", "Forward On All Tracks"], "AXMenuItem"))
        return
    }
    guard command == "edit", let expected = request["text"] as? String,
          let oldStart = request["old_start"] as? String, let oldEnd = request["old_end"] as? String,
          let start = request["start"] as? String, let end = request["end"] as? String else { try fail("界面定位请求无效。") }
    guard [oldStart, oldEnd, start, end].allSatisfy({ $0.range(of: "^[0-9]{2}:[0-9]{2}:[0-9]{2}:[0-9]{2}$", options: .regularExpression) != nil }) else { try fail("时间码格式无效。") }
    var areas = [AXUIElement]()
    for _ in 0..<15 {
        areas = descendants(window).filter { text($0,"AXRole") == "AXTextArea" && text($0,"AXValue") == expected }
        if areas.count == 1 { break }
        RunLoop.current.run(until: Date().addingTimeInterval(0.2))
    }
    guard areas.count == 1 else { try fail("检查器字幕与目标文字不一致。") }
    guard let parent = attr(areas[0], "AXParent") else { try fail("无法定位字幕检查器。") }
    let fields = descendants(parent as! AXUIElement).filter { text($0,"AXRole") == "AXTextField" }
    let starts = fields.filter { text($0,"AXValue") == oldStart }
    let ends = fields.filter { text($0,"AXValue") == oldEnd }
    guard starts.count == 1 && ends.count == 1 else { try fail("检查器字幕时间与目标不一致。") }
    func setTime(_ element: AXUIElement, _ value: String) throws {
        try checkFocus()
        guard AXUIElementSetAttributeValue(element, "AXFocused" as CFString, kCFBooleanTrue) == .success else { try fail("无法聚焦字幕时间码。") }
        guard let rawPosition = attr(element, "AXPosition"), let rawSize = attr(element, "AXSize") else { try fail("无法定位时间码输入框。") }
        var point = CGPoint.zero; var size = CGSize.zero
        AXValueGetValue(rawPosition as! AXValue, .cgPoint, &point)
        AXValueGetValue(rawSize as! AXValue, .cgSize, &size)
        guard size.width > 0 && size.height > 0 else { try fail("时间码输入框不可见。") }
        point.x += size.width / 2; point.y += size.height / 2
        for kind in [CGEventType.leftMouseDown, CGEventType.leftMouseUp] {
            CGEvent(mouseEventSource:nil, mouseType:kind, mouseCursorPosition:point, mouseButton:.left)?.post(tap:.cghidEventTap)
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        var error: NSDictionary?
        let script = "tell application \"System Events\"\nkey code 0 using command down\nkeystroke \"" + value + "\"\nkey code 36\nend tell"
        try checkFocus()
        guard let automation = NSAppleScript(source: script) else { try fail("无法创建系统按键请求。") }
        automation.executeAndReturnError(&error)
        if let error = error { try fail("系统按键服务未授权或失败：" + String(describing:error)) }
        RunLoop.current.run(until: Date().addingTimeInterval(0.15))
    }
    try setTime(starts[0], start)
    try setTime(ends[0], end)
}
let application = NSApplication.shared
application.setActivationPolicy(.accessory)
application.finishLaunching()
let responsePath = CommandLine.arguments.count == 3 ? CommandLine.arguments[2] : nil
func output(_ value: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: value) else { return }
    if let path = responsePath { try? data.write(to: URL(fileURLWithPath:path), options:.atomic) }
    else { FileHandle.standardOutput.write(data) }
}
do {
    let data: Data
    if CommandLine.arguments.count == 3 {
        data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    } else { data = FileHandle.standardInput.readDataToEndOfFile() }
    guard let request = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { try fail("无效的界面助手请求。") }
    try run(request)
    output(["ok":true])
} catch {
    let message = (error as? Failure)?.message ?? String(describing: error)
    output(["ok":false, "message":message]); exit(1)
}
