import SwiftUI

/// Contenedor de pairing para un host "nuevo": conecta, muestra el PIN y,
/// al emparejar, confirma éxito. Abrir el Pad de verdad es F-03 (S-09+).
struct PairingScreen: View {
    let host: DiscoveredHost
    @StateObject private var flow: PairingFlow

    init(host: DiscoveredHost) {
        self.host = host
        _flow = StateObject(wrappedValue: PairingFlow(host: host))
    }

    var body: some View {
        VStack {
            switch flow.state {
            case .connecting:
                ProgressView("Conectando con \(host.name)...")
            case .waitingForPin, .verifying, .badPin, .locked:
                PinEntryView(flow: flow)
            case .paired:
                pairedView
            case .failed(let reason):
                VStack(spacing: 12) {
                    Text("No se pudo emparejar").font(.headline)
                    Text(reason).foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle(host.name)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await flow.start()
        }
        .onDisappear {
            flow.cancel()
        }
    }

    private var pairedView: some View {
        VStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill")
                .font(.largeTitle)
                .foregroundStyle(.green)
            Text("Emparejado")
                .font(.headline)
        }
    }
}
