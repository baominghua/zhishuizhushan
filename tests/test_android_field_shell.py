from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android-zhushan-app"


def read(relative: str) -> str:
    return (ANDROID / relative).read_text(encoding="utf-8")


def test_android_shell_targets_the_shared_mobile_workspace_without_cache_reset():
    activity = read("app/src/main/java/com/zhushan/smartbamboo/MainActivity.java")
    build = read("app/build.gradle")
    guide = read("README.md")

    assert "BuildConfig.SMART_BAMBOO_URL" in activity
    assert "https://36.140.138.117:18081/v2/field/mobile" in build
    assert "SMART_BAMBOO_URL" in build
    assert "deploy-gilt-ten-84.vercel.app" not in activity + build + guide
    assert "WebSettings.LOAD_DEFAULT" in activity
    assert "LOAD_NO_CACHE" not in activity
    assert "clearCache" not in activity


def test_android_shell_exposes_required_a1_device_capabilities():
    activity = read("app/src/main/java/com/zhushan/smartbamboo/MainActivity.java")
    manifest = read("app/src/main/AndroidManifest.xml")

    assert "onShowFileChooser" in activity
    assert "MediaStore.ACTION_IMAGE_CAPTURE" in activity
    assert "FileProvider.getUriForFile" in activity
    assert "requestLocationUpdates" in activity
    assert "registerDefaultNetworkCallback" in activity
    assert "registerNetworkCallback" in activity
    assert "DownloadManager.Request" in activity
    assert "AndroidKeyStore" in activity
    assert "AES/GCM/NoPadding" in activity
    assert '@JavascriptInterface public void reload()' in activity
    for permission in (
        "android.permission.CAMERA",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.POST_NOTIFICATIONS",
    ):
        assert permission in manifest


def test_android_webview_never_bypasses_transport_security():
    activity = read("app/src/main/java/com/zhushan/smartbamboo/MainActivity.java")
    manifest_path = ANDROID / "app/src/main/AndroidManifest.xml"
    network_security = read("app/src/main/res/xml/network_security_config.xml")

    ElementTree.parse(manifest_path)
    assert "handler.cancel()" in activity
    assert "handler.proceed()" not in activity
    assert "MIXED_CONTENT_NEVER_ALLOW" in activity
    assert 'android:usesCleartextTraffic="false"' in manifest_path.read_text(encoding="utf-8")
    assert 'cleartextTrafficPermitted="false"' in network_security
    assert '<certificates src="system"' in network_security
    assert "src=\"user\"" not in network_security


def test_android_shell_has_local_offline_and_certificate_error_surfaces():
    offline = read("app/src/main/assets/offline.html")
    certificate_error = read("app/src/main/assets/certificate-error.html")

    assert "当前处于离线状态" in offline
    assert "SmartBambooNative?.reload" in offline
    assert "无法验证服务器证书" in certificate_error
    assert "不会绕过 HTTPS" in certificate_error


def test_shared_mobile_workspace_consumes_native_network_and_location_events():
    bridge = (ROOT / "apps/web-operations/src/nativeBridge.ts").read_text(encoding="utf-8")
    page = (ROOT / "apps/web-operations/src/pages/MobileFieldPage.tsx").read_text(encoding="utf-8")

    assert '"smart-bamboo-native:network"' in bridge
    assert '"smart-bamboo-native:location"' in bridge
    assert "subscribeConnectivity(setOnline)" in page
    assert "subscribeNativeLocation" in page
    assert "bridge.startLocation()" in page
    assert "nativeBridge()?.stopLocation()" in page
    assert "navigator.geolocation.watchPosition" in page
