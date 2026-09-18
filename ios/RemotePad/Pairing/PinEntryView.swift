import SwiftUI

/// Pantalla de PIN de 6 dígitos (F-02): teclado numérico, autofocus, envía
/// automáticamente al completar 6 dígitos, error inline sin cerrar la pantalla.
struct PinEntryView: View {
    @ObservedObject var flow: PairingFlow
    @State private var pin: String = ""
    @FocusState private var focused: Bool

    var body: some View {
        VStack(spacing: 20) {
            Text("Ingresá el PIN que aparece en la consola de la PC")
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            TextField("······", text: $pin)
                .keyboardType(.numberPad)
                .font(.system(size: 40, weight: .semibold, design: .monospaced))
                .multilineTextAlignment(.center)
                .focused($focused)
                .disabled(flow.state == .verifying || flow.state == .locked)
                .onChange(of: pin) { _, newValue in
                    let digitsOnly = String(newValue.filter(\.isNumber).prefix(6))
                    if digitsOnly != newValue { pin = digitsOnly }
                    if digitsOnly.count == 6 {
                        Task { await flow.submit(pin: digitsOnly) }
                    }
                }

            feedback
        }
        .padding()
        .onAppear { focused = true }
        .onChange(of: flow.state) { _, newState in
            if newState == .badPin {
                pin = ""
                focused = true
            }
        }
    }

    @ViewBuilder
    private var feedback: some View {
        switch flow.state {
        case .badPin:
            Text("PIN incorrecto").foregroundStyle(.red)
        case .locked:
            Text("Bloqueado 5 minutos").foregroundStyle(.red)
        case .verifying:
            ProgressView()
        case .failed(let reason):
            Text("Error: \(reason)").foregroundStyle(.red)
        default:
            EmptyView()
        }
    }
}
