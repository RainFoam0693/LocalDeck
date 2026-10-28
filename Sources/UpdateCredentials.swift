import Foundation
import Security

/// A generic password stays in the current user's Keychain, separate from app preferences.
enum DeckUpdateCredentials {
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "dev.localdeck.github-updates",
         kSecAttrAccount as String: "GitHub"]
    }
    private static func failure() -> NSError {
        NSError(domain: "LocalDeck.Keychain", code: 1, userInfo: [NSLocalizedDescriptionKey: "无法访问更新授权，请检查系统钥匙串。"])
    }
    static func read() throws -> String {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var value: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &value)
        if status == errSecItemNotFound { return "" }
        guard status == errSecSuccess, let data = value as? Data, let token = String(data: data, encoding: .utf8) else { throw failure() }
        return token
    }
    static func save(_ token: String) throws {
        if token.isEmpty {
            let status = SecItemDelete(query as CFDictionary)
            guard status == errSecSuccess || status == errSecItemNotFound else { throw failure() }
            return
        }
        let data = Data(token.utf8)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var item = query
            item[kSecValueData as String] = data
            item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw failure() }
        } else if status != errSecSuccess { throw failure() }
    }
}
