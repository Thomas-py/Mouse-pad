import SwiftUI
import UIKit

/// Superficie de pad (F-04..F-08): delega todos los touches a `GestureEngine`
/// salvo la zona superior de 24pt, reservada para salir con swipe-down (F-10).
struct PadView: UIViewRepresentable {
    var engineConfig: (GestureEngine) -> Void = { _ in }
    var onIntent: (GestureIntent) -> Void
    var onExit: () -> Void

    func makeUIView(context: Context) -> PadUIView {
        let view = PadUIView()
        engineConfig(view.gestureEngine)
        view.gestureEngine.onIntent = onIntent
        view.onExit = onExit
        return view
    }

    func updateUIView(_ uiView: PadUIView, context: Context) {
        uiView.gestureEngine.onIntent = onIntent
        uiView.onExit = onExit
    }
}

/// Zona superior de 24pt (F-10): swipe hacia abajo para salir. El resto de
/// la vista alimenta `GestureEngine` con todos los touches activos.
final class PadUIView: UIView {
    let gestureEngine = GestureEngine()
    var onExit: (() -> Void)?

    private static let topExitZoneHeight: CGFloat = 24
    private static let exitSwipeThreshold: CGFloat = 40

    private var exitTouch: UITouch?
    private var exitStartLocation: CGPoint?

    private var tickLink: CADisplayLink?

    override init(frame: CGRect) {
        super.init(frame: frame)
        isMultipleTouchEnabled = true
        backgroundColor = .black
        startTickLoop()
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) no implementado — PadUIView se crea por código")
    }

    deinit {
        tickLink?.invalidate()
    }

    private func startTickLoop() {
        let link = CADisplayLink(target: self, selector: #selector(handleTick))
        link.add(to: .main, forMode: .common)
        tickLink = link
    }

    @objc private func handleTick() {
        gestureEngine.tick(now: CACurrentMediaTime())
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        let now = CACurrentMediaTime()
        var engineTouches: [(id: GestureTouchID, location: CGPoint)] = []
        for touch in touches {
            let location = touch.location(in: self)
            if location.y <= Self.topExitZoneHeight, exitTouch == nil {
                exitTouch = touch
                exitStartLocation = location
                continue
            }
            engineTouches.append((GestureTouchID(ObjectIdentifier(touch)), location))
        }
        if !engineTouches.isEmpty {
            gestureEngine.touchesBegan(engineTouches, now: now)
        }
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        let now = CACurrentMediaTime()

        if let exitTouch, touches.contains(exitTouch) {
            let location = exitTouch.location(in: self)
            if let start = exitStartLocation, location.y - start.y > Self.exitSwipeThreshold {
                onExit?()
                self.exitTouch = nil
                exitStartLocation = nil
            }
        }

        let engineTouches: [(id: GestureTouchID, location: CGPoint)] = touches
            .filter { $0 != exitTouch }
            .map { (GestureTouchID(ObjectIdentifier($0)), $0.location(in: self)) }
        if !engineTouches.isEmpty {
            gestureEngine.touchesMoved(engineTouches, now: now)
        }
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        release(touches, cancelled: false)
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        release(touches, cancelled: true)
    }

    private func release(_ touches: Set<UITouch>, cancelled: Bool) {
        let now = CACurrentMediaTime()

        if let exitTouch, touches.contains(exitTouch) {
            self.exitTouch = nil
            exitStartLocation = nil
        }

        let ids = touches.filter { $0 != exitTouch }.map { GestureTouchID(ObjectIdentifier($0)) }
        guard !ids.isEmpty else { return }
        if cancelled {
            gestureEngine.touchesCancelled(ids, now: now)
        } else {
            gestureEngine.touchesEnded(ids, now: now)
        }
    }
}
