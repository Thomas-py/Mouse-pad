import SwiftUI

/// Pantalla de ajustes (F-09). Todos los controles escriben directo a
/// `SettingsStore`, que persiste en UserDefaults al toque.
struct SettingsView: View {
    @ObservedObject var store: SettingsStore

    var body: some View {
        Form {
            Section("Movimiento") {
                VStack(alignment: .leading) {
                    Text("Sensibilidad: \(store.sensitivity, specifier: "%.1f")")
                    Slider(value: $store.sensitivity, in: SettingsStore.sensitivityRange, step: 0.1)
                }
                VStack(alignment: .leading) {
                    Text("Aceleración: \(store.acceleration, specifier: "%.3f")")
                    Slider(value: $store.acceleration, in: SettingsStore.accelerationRange, step: 0.005)
                }
            }

            Section("Gestos") {
                Toggle("Scroll natural", isOn: $store.naturalScroll)
                Toggle("Tap para arrastrar", isOn: $store.tapToDrag)
                Toggle("Háptico", isOn: $store.hapticsEnabled)
            }

            Section("Avanzado") {
                Toggle("Mostrar debug (RTT, paquetes/s)", isOn: $store.showDebug)
            }
        }
        .navigationTitle("Ajustes")
    }
}

#Preview {
    NavigationStack {
        SettingsView(store: SettingsStore.shared)
    }
}
