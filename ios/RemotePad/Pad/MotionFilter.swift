import Foundation

/// Sensibilidad + aceleración + acumulación sub-pixel sobre un delta crudo
/// de touch (docs/01-ARQUITECTURA.md §2 "MotionFilter", F-04).
///
/// Sensibilidad fija en 1.5 por ahora (S-10) — S-14 la hace configurable
/// desde Ajustes, reemplazando el default acá.
struct MotionFilter {
    var sensitivity: Double = 1.5      // 0.5 - 3.0 (F-09)
    var acceleration: Double = 0.02    // 0 - 0.05 (F-09)

    private var residualX: Double = 0
    private var residualY: Double = 0

    /// Convierte un delta crudo (puntos de pantalla) en un delta entero,
    /// acumulando el resto para que movimientos lentos terminen moviendo
    /// el cursor 1 px en vez de perderse en el redondeo.
    mutating func apply(dx: Double, dy: Double) -> (dx: Int, dy: Int) {
        let scaledX = accelerate(dx) * sensitivity + residualX
        let scaledY = accelerate(dy) * sensitivity + residualY

        let outX = scaledX.rounded()
        let outY = scaledY.rounded()

        residualX = scaledX - outX
        residualY = scaledY - outY

        return (Int(outX), Int(outY))
    }

    private func accelerate(_ delta: Double) -> Double {
        delta * (1 + acceleration * abs(delta))
    }

    mutating func reset() {
        residualX = 0
        residualY = 0
    }
}
