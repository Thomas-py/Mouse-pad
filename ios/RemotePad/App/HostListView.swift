import SwiftUI

/// Lista de hosts descubiertos por Bonjour (F-01). Tocar un host nuevo abre
/// el pairing (F-02); tocar uno emparejado todavía no abre el Pad (F-03,
/// pendiente de S-09+) — placeholder por ahora.
struct HostListView: View {
    @StateObject private var browser = HostBrowser()
    @State private var showEmptyHint = false
    @State private var showManualEntry = false
    @State private var manualIPText = ""
    @State private var manualHost: DiscoveredHost?

    var body: some View {
        NavigationStack {
            Group {
                if browser.permissionDenied {
                    permissionDeniedView
                } else if browser.hosts.isEmpty {
                    emptyStateView
                } else {
                    hostList
                }
            }
            .navigationTitle("RemotePad")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        showManualEntry = true
                    } label: {
                        Image(systemName: "network")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink {
                        SettingsView(store: .shared)
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            // NavigationLink oculto: la navegación programática por
            // `navigationDestination(item:)` es iOS 17+, y el deployment
            // target de este proyecto es iOS 16 (00-CONTEXTO.md). Este es el
            // patrón equivalente compatible con 16.
            .background(
                NavigationLink(
                    isActive: Binding(
                        get: { manualHost != nil },
                        set: { active in if !active { manualHost = nil } }
                    )
                ) {
                    if let manualHost { destination(for: manualHost) }
                } label: { EmptyView() }
                .hidden()
            )
        }
        .sheet(isPresented: $showManualEntry) {
            manualEntrySheet
        }
        .onAppear {
            browser.start()
            showEmptyHint = false
            Task {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                if browser.hosts.isEmpty {
                    showEmptyHint = true
                }
            }
        }
        .onDisappear {
            browser.stop()
        }
    }

    private var hostList: some View {
        List(browser.hosts) { host in
            NavigationLink {
                destination(for: host)
            } label: {
                HStack {
                    Image(systemName: systemImageName(for: host.os))
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading) {
                        Text(host.name)
                            .font(.body)
                        Text(isPaired(host) ? "emparejado" : "nuevo")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func destination(for host: DiscoveredHost) -> some View {
        if isPaired(host) {
            PadScreen(host: host)
        } else {
            PairingScreen(host: host)
        }
    }

    private func isPaired(_ host: DiscoveredHost) -> Bool {
        TokenKeychain.load(forHostId: host.id) != nil
    }

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            ProgressView()
            if showEmptyHint {
                Text("Asegurate de que el servidor esté corriendo en la misma Wi-Fi")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                Button("Conectar por IP") {
                    showManualEntry = true
                }
                .font(.callout)
            }
        }
    }

    private var manualEntrySheet: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("IP de la PC (ej. 192.168.0.23)", text: $manualIPText)
                        .keyboardType(.numbersAndPunctuation)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                } footer: {
                    Text("Usá esto si la app no encuentra la PC sola — algunos routers no dejan pasar el descubrimiento automático. Asume los puertos por defecto del servidor (52100/52101).")
                }
            }
            .navigationTitle("Conectar por IP")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancelar") { showManualEntry = false }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Conectar") {
                        guard let host = DiscoveredHost.manual(ip: manualIPText) else { return }
                        showManualEntry = false
                        manualHost = host
                    }
                    .disabled(manualIPText.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }

    private var permissionDeniedView: some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.exclamationmark")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("RemotePad necesita acceso a la red local para encontrar tu PC.")
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            Button("Abrir Ajustes") {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            }
        }
    }

    private func systemImageName(for os: String) -> String {
        switch os {
        case "macos": return "desktopcomputer"
        case "windows": return "pc"
        case "linux": return "terminal"
        default: return "questionmark.circle"
        }
    }
}

#Preview {
    HostListView()
}
