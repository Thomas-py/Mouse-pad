import SwiftUI
import UIKit

/// Superficie de pad (F-04): un dedo mueve el cursor con deltas relativos.
/// Taps, doble tap, clic derecho, drag y scroll son F-05..F-08 (S-11, S-12,
/// S-13) — acá solo hay movimiento de 1 dedo y salida por swipe-down (F-10).
struct PadView: UIViewRepresentable {
    var onMove: (Double, Double) -> Void
    var onExit: () -> Void

    func makeUIView(context: Context) -> PadUIView {
        let view = PadUIView()
        view.onMove = onMove
        view.onExit = onExit
        return view
    }

    func updateUIView(_ uiView: PadUIView, context: Context) {
        uiView.onMove = onMove
        uiView.onExit = onExit
    }
}

/// Zona superior de 24pt (F-10): swipe hacia abajo para salir. El resto de
/// la vista reporta el delta del primer touch activo (relativo, F-04: subir
/// el dedo y apoyar en otro lado no mueve el cursor).
final class PadUIView: UIView {
    var onMove: ((Double, Double) -> Void)?
    var onExit: (() -> Void)?

    private static let topExitZoneHeight: CGFloat = 24
    private static let exitSwipeThreshold: CGFloat = 40

    private var trackedTouch: UITouch?
    private var lastLocation: CGPoint?

    private var exitTouch: UITouch?
    private var exitStartLocation: CGPoint?

    override init(frame: CGRect) {
        super.init(frame: frame)
        isMultipleTouchEnabled = true
        backgroundColor = .black
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) no implementado — PadUIView se crea por código")
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        for touch in touches {
            let location = touch.location(in: self)
            if location.y <= Self.topExitZoneHeight, exitTouch == nil {
                exitTouch = touch
                exitStartLocation = location
                continue
            }
            if trackedTouch == nil {
                trackedTouch = touch
                lastLocation = location
            }
        }
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        if let exitTouch, touches.contains(exitTouch) {
            let location = exitTouch.location(in: self)
            if let start = exitStartLocation, location.y - start.y > Self.exitSwipeThreshold {
                onExit?()
                self.exitTouch = nil
                exitStartLocation = nil
            }
        }

        guard let trackedTouch, touches.contains(trackedTouch), let last = lastLocation else { return }
        let location = trackedTouch.location(in: self)
        let dx = location.x - last.x
        let dy = location.y - last.y
        lastLocation = location
        if dx != 0 || dy != 0 {
            onMove?(Double(dx), Double(dy))
        }
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        release(touches)
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        release(touches)
    }

    private func release(_ touches: Set<UITouch>) {
        if let trackedTouch, touches.contains(trackedTouch) {
            self.trackedTouch = nil
            lastLocation = nil
        }
        if let exitTouch, touches.contains(exitTouch) {
            self.exitTouch = nil
            exitStartLocation = nil
        }
    }
}
