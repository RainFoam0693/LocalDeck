import AppKit

let root = CommandLine.arguments[1]
let fm = FileManager.default
let iconset = root + "/assets/LocalDeck.iconset"
try fm.createDirectory(atPath: iconset, withIntermediateDirectories: true)
func rounded(_ rect: NSRect, _ radius: CGFloat) -> NSBezierPath {
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
}
func render(_ pixels: Int) throws {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    let context = NSGraphicsContext(bitmapImageRep: bitmap)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = context
    context.imageInterpolation = .high
    context.cgContext.scaleBy(x: CGFloat(pixels) / 1024, y: CGFloat(pixels) / 1024)
    let base = rounded(NSRect(x: 64, y: 64, width: 896, height: 896), 204)
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow(); shadow.shadowColor = NSColor.black.withAlphaComponent(0.3); shadow.shadowBlurRadius = 28; shadow.shadowOffset = NSSize(width: 0, height: -10); shadow.set()
    NSColor(calibratedRed: 0.06, green: 0.085, blue: 0.14, alpha: 1).setFill(); base.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(colors: [NSColor(calibratedRed: 0.12, green: 0.17, blue: 0.24, alpha: 1), NSColor(calibratedRed: 0.035, green: 0.055, blue: 0.10, alpha: 1)])!.draw(in: base, angle: -70)
    let teal = NSColor(calibratedRed: 0.21, green: 0.94, blue: 0.76, alpha: 1)
    let blue = NSColor(calibratedRed: 0.40, green: 0.46, blue: 0.98, alpha: 1)
    for (index, offset) in [92.0, 46.0].enumerated() {
        let rect = NSRect(x: 211 - offset * 0.25, y: 244 - offset, width: 602 + offset * 0.5, height: 468)
        let path = rounded(rect, 68)
        (index == 0 ? blue.withAlphaComponent(0.58) : teal.withAlphaComponent(0.55)).setFill(); path.fill()
    }
    let terminal = rounded(NSRect(x: 201, y: 268, width: 622, height: 490), 70)
    NSColor(calibratedRed: 0.085, green: 0.13, blue: 0.19, alpha: 1).setFill(); terminal.fill()
    teal.withAlphaComponent(0.8).setStroke(); terminal.lineWidth = 5; terminal.stroke()
    for (idx, color) in [teal, teal.withAlphaComponent(0.55), teal.withAlphaComponent(0.28)].enumerated() {
        color.setFill(); NSBezierPath(ovalIn: NSRect(x: 252 + idx * 36, y: 692, width: 15, height: 15)).fill()
    }
    NSColor.white.withAlphaComponent(0.10).setStroke()
    let line = NSBezierPath(); line.move(to: NSPoint(x: 225, y: 662)); line.line(to: NSPoint(x: 799, y: 662)); line.lineWidth = 2; line.stroke()
    let chevron = NSBezierPath(); chevron.move(to: NSPoint(x: 302, y: 575)); chevron.line(to: NSPoint(x: 398, y: 493)); chevron.line(to: NSPoint(x: 302, y: 411)); chevron.lineWidth = 31; chevron.lineCapStyle = .round; chevron.lineJoinStyle = .round
    teal.setStroke(); chevron.stroke()
    let cursor = NSBezierPath(); cursor.move(to: NSPoint(x: 465, y: 413)); cursor.line(to: NSPoint(x: 586, y: 413)); cursor.lineWidth = 29; cursor.lineCapStyle = .round; cursor.stroke()
    let badge = NSBezierPath(ovalIn: NSRect(x: 675, y: 302, width: 74, height: 74))
    teal.withAlphaComponent(0.12).setFill(); badge.fill()
    teal.setFill(); NSBezierPath(ovalIn: NSRect(x: 695, y: 322, width: 34, height: 34)).fill()
    NSGraphicsContext.restoreGraphicsState()
    let data = bitmap.representation(using: .png, properties: [:])!
    if pixels == 1024 { try data.write(to: URL(fileURLWithPath: root + "/assets/LocalDeck.png")) }
    for size in [16, 32, 128, 256, 512] {
        if pixels == size { try data.write(to: URL(fileURLWithPath: iconset + "/icon_\(size)x\(size).png")) }
        if pixels == size * 2 { try data.write(to: URL(fileURLWithPath: iconset + "/icon_\(size)x\(size)@2x.png")) }
    }
}
for size in [16, 32, 64, 128, 256, 512, 1024] { try render(size) }
