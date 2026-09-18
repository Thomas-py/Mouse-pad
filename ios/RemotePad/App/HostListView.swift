import SwiftUI

/// Lista de hosts descubiertos por Bonjour (F-01). Tocar un host nuevo abre
/// el pairing (F-02); tocar uno emparejado todavía no abre el Pad (F-03,
/// pendiente de S-09+) — placeholder por ahora.
struct HostListView: View {
    @StateObject private var browser = HostBrowser()
    @State private var showEmptyHint = false

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
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink {
                        SettingsView(store: .shared)
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
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
