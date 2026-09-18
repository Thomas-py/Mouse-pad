import Foundation

/// client_id estable de este iPhone — no es secreto, se manda en claro en
/// `hello`/`pair_start`. Se genera una sola vez y se guarda en UserDefaults.
enum ClientIdentity {
    private static let key = "remotepad.client_id"

    static var current: String {
        if let existing = UserDefaults.standard.string(forKey: key), !existing.isEmpty {
            return existing
        }
        let generated = "iphone-\(UUID().uuidString.prefix(8))"
        UserDefaults.standard.set(generated, forKey: key)
        return generated
    }
}
