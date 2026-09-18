import CryptoKit
import Foundation

/// HMAC-SHA256 y HKDF del protocolo — espejo exacto de
/// server/remotepad_server/session.py. Ver docs/02-PROTOCOLO.md §2, §5.
enum Signer {
    static func randomBytes(_ count: Int) -> Data {
        var bytes = [UInt8](repeating: 0, count: count)
        let status = SecRandomCopyBytes(kSecRandomDefault, count, &bytes)
        precondition(status == errSecSuccess, "SecRandomCopyBytes falló: \(status)")
        return Data(bytes)
    }

    private static func hmacSHA256(key: Data, message: Data) -> Data {
        let symmetricKey = SymmetricKey(data: key)
        let mac = HMAC<SHA256>.authenticationCode(for: message, using: symmetricKey)
        return Data(mac)
    }

    /// proof = HMAC-SHA256(pin_utf8, nonce_s + nonce_c), hex completo.
    static func pairProof(pin: String, nonceServer: Data, nonceClient: Data) -> String {
        hmacSHA256(key: Data(pin.utf8), message: nonceServer + nonceClient).hexEncoded
    }

    /// token = HKDF-SHA256(ikm=pin, salt=nonce_s+nonce_c, info="remotepad-v1", len=32).
    /// 32 bytes = un solo bloque de HKDF-Expand (L == tamaño de hash), no hace
    /// falta iterar T(1), T(2)... — igual que server/remotepad_server/session.py.
    static func deriveToken(pin: String, nonceServer: Data, nonceClient: Data) -> Data {
        let salt = nonceServer + nonceClient
        let prk = hmacSHA256(key: salt, message: Data(pin.utf8))
        let info = Data("remotepad-v1".utf8) + Data([0x01])
        return hmacSHA256(key: prk, message: info)
    }

    /// sig del mensaje `auth` = HMAC-SHA256(token, nonce_s + nonce_c), hex completo.
    static func authSig(token: Data, nonceServer: Data, nonceClient: Data) -> String {
        hmacSHA256(key: token, message: nonceServer + nonceClient).hexEncoded
    }

    /// sig de mensajes post-auth = hex(HMAC-SHA256(token, session+id+t))[:16].
    static func messageSig(token: Data, session: String, id: String, type: String) -> String {
        let payload = Data("\(session)\(id)\(type)".utf8)
        let full = hmacSHA256(key: token, message: payload).hexEncoded
        return String(full.prefix(16))
    }
}
