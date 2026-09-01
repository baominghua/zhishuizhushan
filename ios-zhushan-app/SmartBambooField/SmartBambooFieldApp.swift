import SwiftUI

@main
struct SmartBambooFieldApp: App {
    var body: some Scene {
        WindowGroup {
            FieldWebView()
                .ignoresSafeArea(.container, edges: .bottom)
        }
    }
}

