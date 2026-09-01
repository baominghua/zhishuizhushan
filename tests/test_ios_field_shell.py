from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
IOS = ROOT / "ios-zhushan-app"


def read(relative: str) -> str:
    return (IOS / relative).read_text(encoding="utf-8")


def test_ios_i1_reuses_shared_mobile_workspace_and_protocol_cache():
    info = read("SmartBambooField/Info.plist")
    webview = read("SmartBambooField/FieldWebView.swift")
    coordinator = read("SmartBambooField/NativeCoordinator.swift")

    ElementTree.parse(IOS / "SmartBambooField/Info.plist")
    assert "https://36.140.138.117:18081/v2/field/mobile" in info
    assert ".useProtocolCachePolicy" in webview
    assert "WKWebsiteDataStore.default" not in webview  # Swift spelling is the instance shorthand below.
    assert "configuration.websiteDataStore = .default()" in webview
    assert "smart-bamboo-native:network" in coordinator
    assert "smart-bamboo-native:\\(type)" in coordinator
    assert 'emit("location"' in coordinator
    assert "window.SmartBambooNative" in coordinator


def test_ios_i1_has_location_network_keychain_and_offline_support():
    coordinator = read("SmartBambooField/NativeCoordinator.swift")
    offline = read("SmartBambooField/offline.html")
    for evidence in (
        "CLLocationManager",
        "NWPathMonitor",
        "SecItemAdd",
        "kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly",
        "allowsBackForwardNavigationGestures = true",
    ):
        assert evidence in coordinator + read("SmartBambooField/FieldWebView.swift")
    assert "暂时无法连接平台" in offline
    assert "SmartBambooNative?.reload" in offline


def test_ios_i1_restricts_navigation_and_does_not_bypass_tls():
    config = read("SmartBambooField/AppConfig.swift")
    coordinator = read("SmartBambooField/NativeCoordinator.swift")
    assert 'url.scheme == "https"' in config
    assert "AppConfig.isTrusted(url)" in coordinator
    assert "UIApplication.shared.open(url)" in coordinator
    assert "serverTrust" not in coordinator
    assert "URLCredential" not in coordinator
    assert "performDefaultHandling" not in coordinator
