import Combine
import Foundation

/// Ajustes persistentes en UserDefaults (F-09). Se aplican en vivo: quien
/// los usa (MotionFilter, GestureEngine, PadSession) los vuelve a leer en
/// cada uso, no hace falta reconectar.
final class SettingsStore: ObservableObject {
    static let shared = SettingsStore()

    static let sensitivityRange: ClosedRange<Double> = 0.5...3.0
    static let accelerationRange: ClosedRange<Double> = 0...0.05

    private enum Keys {
        static let sensitivity = "settings.sensitivity"
        static let acceleration = "settings.acceleration"
        static let naturalScroll = "settings.naturalScroll"
        static let tapToDrag = "settings.tapToDrag"
        static let hapticsEnabled = "settings.hapticsEnabled"
        static let showDebug = "settings.showDebug"
    }

    private let defaults: UserDefaults

    @Published var sensitivity: Double {
        didSet { defaults.set(sensitivity, forKey: Keys.sensitivity) }
    }
    @Published var acceleration: Double {
        didSet { defaults.set(acceleration, forKey: Keys.acceleration) }
    }
    @Published var naturalScroll: Bool {
        didSet { defaults.set(naturalScroll, forKey: Keys.naturalScroll) }
    }
    @Published var tapToDrag: Bool {
        didSet { defaults.set(tapToDrag, forKey: Keys.tapToDrag) }
    }
    @Published var hapticsEnabled: Bool {
        didSet { defaults.set(hapticsEnabled, forKey: Keys.hapticsEnabled) }
    }
    @Published var showDebug: Bool {
        didSet { defaults.set(showDebug, forKey: Keys.showDebug) }
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        sensitivity = (defaults.object(forKey: Keys.sensitivity) as? Double) ?? 1.5
        acceleration = (defaults.object(forKey: Keys.acceleration) as? Double) ?? 0.02
        naturalScroll = (defaults.object(forKey: Keys.naturalScroll) as? Bool) ?? true
        tapToDrag = (defaults.object(forKey: Keys.tapToDrag) as? Bool) ?? true
        hapticsEnabled = (defaults.object(forKey: Keys.hapticsEnabled) as? Bool) ?? true
        showDebug = (defaults.object(forKey: Keys.showDebug) as? Bool) ?? false
    }
}
