import Foundation
import Security

/// Guarda el token de pairing por host (clave = `DiscoveredHost.id`, el uuid
/// persistente del servidor — F-02: `kSecAttrAccessibleAfterFirstUnlock`).
enum TokenKeychain {
    private static let service = "com.thomaslescano.remotepad.token"

    private static func query(forHostId hostId: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: hostId,
        ]
    }

    static func save(token: Data, forHostId hostId: String) throws {
        var query = query(forHostId: hostId)
        SecItemDelete(query as CFDictionary)

        query[kSecValueData as String] = token
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock

        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw NSError(domain: NSOSStatusErrorDomain, code: Int(status))
        }
    }

    static func load(forHostId hostId: String) -> Data? {
        var attributes = query(forHostId: hostId)
        attributes[kSecReturnData as String] = true
        attributes[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: AnyObject?
        let status = SecItemCopyMatching(attributes as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return data
    }

    /// "Olvidar host" (F-02).
    static func delete(forHostId hostId: String) {
        SecItemDelete(query(forHostId: hostId) as CFDictionary)
    }
}
