package com.zhushan.smartbamboo;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class MainActivity extends Activity implements LocationListener {
    private static final int REQUEST_FILE_PERMISSIONS = 201;
    private static final int REQUEST_LOCATION_PERMISSION = 202;
    private static final int REQUEST_FILE_CHOOSER = 203;
    private static final int REQUEST_NOTIFICATION_PERMISSION = 204;
    private static final String OFFLINE_URL = "file:///android_asset/offline.html";

    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private WebChromeClient.FileChooserParams pendingFileChooser;
    private Uri pendingCameraUri;
    private GeolocationPermissions.Callback pendingGeolocationCallback;
    private String pendingGeolocationOrigin;
    private boolean pendingLocationStart;
    private boolean networkCallbackRegistered;
    private ConnectivityManager.NetworkCallback networkCallback;
    private LocationManager locationManager;

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.rgb(7, 50, 42));
        getWindow().setNavigationBarColor(Color.rgb(7, 50, 42));

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(244, 248, 246));
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setWebViewClient(new SecureWebViewClient());
        webView.setWebChromeClient(new FieldWebChromeClient());
        webView.addJavascriptInterface(new NativeBridge(), "SmartBambooNative");

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setGeolocationEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.setSafeBrowsingEnabled(true);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        }

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false);
        webView.setDownloadListener(this::enqueueDownload);
        setContentView(webView);

        locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        registerNetworkObserver();
        requestNotificationPermissionIfNeeded();
        loadApplication();
    }

    private void loadApplication() {
        webView.loadUrl(isOnline() ? BuildConfig.SMART_BAMBOO_URL : OFFLINE_URL);
    }

    private boolean isTrustedApplicationUri(Uri uri) {
        Uri configured = Uri.parse(BuildConfig.SMART_BAMBOO_URL);
        return "https".equalsIgnoreCase(uri.getScheme())
            && configured.getHost() != null
            && configured.getHost().equalsIgnoreCase(uri.getHost())
            && effectivePort(configured) == effectivePort(uri);
    }

    private int effectivePort(Uri uri) {
        return uri.getPort() >= 0 ? uri.getPort() : ("https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80);
    }

    private void openExternal(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException error) {
            Toast.makeText(this, R.string.no_application_for_link, Toast.LENGTH_SHORT).show();
        }
    }

    private final class SecureWebViewClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            return handleNavigation(request.getUrl());
        }

        @Override
        @SuppressWarnings("deprecation")
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            return handleNavigation(Uri.parse(url));
        }

        private boolean handleNavigation(Uri uri) {
            if (isTrustedApplicationUri(uri) || "file".equalsIgnoreCase(uri.getScheme())) {
                return false;
            }
            openExternal(uri);
            return true;
        }

        @Override
        public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
            handler.cancel();
            view.loadUrl("file:///android_asset/certificate-error.html");
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                view.loadUrl(OFFLINE_URL);
            }
        }
    }

    private final class FieldWebChromeClient extends WebChromeClient {
        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (filePathCallback != null) {
                filePathCallback.onReceiveValue(null);
            }
            filePathCallback = callback;
            pendingFileChooser = params;
            if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.CAMERA}, REQUEST_FILE_PERMISSIONS);
            } else {
                launchFileChooser(params);
            }
            return true;
        }

        @Override
        public void onPermissionRequest(PermissionRequest request) {
            request.deny();
        }

        @Override
        public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
            if (!isTrustedApplicationUri(Uri.parse(origin))) {
                callback.invoke(origin, false, false);
                return;
            }
            if (hasLocationPermission()) {
                callback.invoke(origin, true, false);
                return;
            }
            pendingGeolocationOrigin = origin;
            pendingGeolocationCallback = callback;
            requestLocationPermission();
        }
    }

    private void launchFileChooser(WebChromeClient.FileChooserParams params) {
        Intent contentIntent;
        try {
            contentIntent = params.createIntent();
        } catch (ActivityNotFoundException error) {
            contentIntent = new Intent(Intent.ACTION_OPEN_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType("*/*");
        }

        Intent cameraIntent = createCameraIntent();
        Intent chooser = Intent.createChooser(contentIntent, getString(R.string.choose_evidence));
        if (cameraIntent != null) {
            chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{cameraIntent});
        }
        try {
            startActivityForResult(chooser, REQUEST_FILE_CHOOSER);
        } catch (ActivityNotFoundException error) {
            finishFileSelection(null);
            Toast.makeText(this, R.string.no_file_picker, Toast.LENGTH_SHORT).show();
        }
    }

    private Intent createCameraIntent() {
        Intent intent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
        if (intent.resolveActivity(getPackageManager()) == null) {
            return null;
        }
        try {
            File directory = getExternalFilesDir(Environment.DIRECTORY_PICTURES);
            if (directory == null) return null;
            String timestamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date());
            File photo = File.createTempFile("SB_" + timestamp + "_", ".jpg", directory);
            pendingCameraUri = FileProvider.getUriForFile(this, BuildConfig.APPLICATION_ID + ".files", photo);
            intent.putExtra(MediaStore.EXTRA_OUTPUT, pendingCameraUri);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            return intent;
        } catch (Exception error) {
            pendingCameraUri = null;
            return null;
        }
    }

    private void finishFileSelection(Uri[] values) {
        if (filePathCallback != null) {
            filePathCallback.onReceiveValue(values);
        }
        filePathCallback = null;
        pendingFileChooser = null;
        pendingCameraUri = null;
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_FILE_CHOOSER) return;
        Uri[] result = null;
        if (resultCode == RESULT_OK) {
            result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            if ((result == null || result.length == 0) && pendingCameraUri != null) {
                result = new Uri[]{pendingCameraUri};
            }
        }
        finishFileSelection(result);
    }

    private boolean hasLocationPermission() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
            || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void requestLocationPermission() {
        requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION}, REQUEST_LOCATION_PERMISSION);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_FILE_PERMISSIONS) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED && pendingFileChooser != null) {
                launchFileChooser(pendingFileChooser);
            } else {
                finishFileSelection(null);
            }
            return;
        }
        if (requestCode == REQUEST_LOCATION_PERMISSION) {
            boolean granted = hasLocationPermission();
            if (pendingGeolocationCallback != null) {
                pendingGeolocationCallback.invoke(pendingGeolocationOrigin, granted, false);
                pendingGeolocationCallback = null;
                pendingGeolocationOrigin = null;
            }
            if (granted && pendingLocationStart) {
                pendingLocationStart = false;
                startLocationUpdates();
            }
        }
    }

    @SuppressLint("MissingPermission")
    private void startLocationUpdates() {
        if (!hasLocationPermission()) {
            pendingLocationStart = true;
            requestLocationPermission();
            return;
        }
        try {
            locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 3000L, 3f, this);
            dispatchEvent("location", json("status", "started"));
        } catch (RuntimeException error) {
            dispatchEvent("location", json("status", "unavailable"));
        }
    }

    private void stopLocationUpdates() {
        locationManager.removeUpdates(this);
        dispatchEvent("location", json("status", "stopped"));
    }

    @Override
    public void onLocationChanged(Location location) {
        JSONObject payload = new JSONObject();
        try {
            payload.put("status", "update");
            payload.put("latitude", location.getLatitude());
            payload.put("longitude", location.getLongitude());
            payload.put("accuracy", location.hasAccuracy() ? location.getAccuracy() : JSONObject.NULL);
            payload.put("altitude", location.hasAltitude() ? location.getAltitude() : JSONObject.NULL);
            payload.put("timestamp", location.getTime());
        } catch (JSONException ignored) { }
        dispatchEvent("location", payload);
    }

    @Override public void onStatusChanged(String provider, int status, Bundle extras) { }
    @Override public void onProviderEnabled(String provider) { }
    @Override public void onProviderDisabled(String provider) { dispatchEvent("location", json("status", "provider-disabled")); }

    private void registerNetworkObserver() {
        ConnectivityManager manager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network network) { dispatchNetworkState(true); }
            @Override public void onLost(Network network) { dispatchNetworkState(isOnline()); }
            @Override public void onCapabilitiesChanged(Network network, NetworkCapabilities capabilities) {
                dispatchNetworkState(capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET));
            }
        };
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                manager.registerDefaultNetworkCallback(networkCallback);
            } else {
                NetworkRequest request = new NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .build();
                manager.registerNetworkCallback(request, networkCallback);
            }
            networkCallbackRegistered = true;
        } catch (RuntimeException ignored) { }
    }

    private boolean isOnline() {
        ConnectivityManager manager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        Network network = manager.getActiveNetwork();
        NetworkCapabilities capabilities = manager.getNetworkCapabilities(network);
        return capabilities != null
            && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
    }

    private void dispatchNetworkState(boolean online) { dispatchEvent("network", json("online", online)); }

    private void dispatchEvent(String type, JSONObject detail) {
        runOnUiThread(() -> {
            if (webView == null) return;
            String script = "window.dispatchEvent(new CustomEvent('smart-bamboo-native:" + type + "',{detail:" + detail + "}));";
            webView.evaluateJavascript(script, null);
        });
    }

    private JSONObject json(String key, Object value) {
        JSONObject payload = new JSONObject();
        try { payload.put(key, value); } catch (JSONException ignored) { }
        return payload;
    }

    private void enqueueDownload(String url, String userAgent, String contentDisposition, String mimeType, long contentLength) {
        if (!isTrustedApplicationUri(Uri.parse(url))) {
            openExternal(Uri.parse(url));
            return;
        }
        String filename = URLUtil.guessFileName(url, contentDisposition, mimeType);
        DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
        request.setMimeType(mimeType);
        request.addRequestHeader("User-Agent", userAgent);
        String cookies = CookieManager.getInstance().getCookie(url);
        if (cookies != null && !cookies.isEmpty()) request.addRequestHeader("Cookie", cookies);
        request.setTitle(filename);
        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
        request.setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, filename);
        ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(request);
        Toast.makeText(this, R.string.download_started, Toast.LENGTH_SHORT).show();
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQUEST_NOTIFICATION_PERMISSION);
        }
    }

    public final class NativeBridge {
        private final SecureStore secureStore = new SecureStore(MainActivity.this);

        @JavascriptInterface public String version() { return "1.0"; }
        @JavascriptInterface public boolean isOnline() { return MainActivity.this.isOnline(); }
        @JavascriptInterface public String get(String key) { return secureStore.get(key); }
        @JavascriptInterface public boolean set(String key, String value) { return secureStore.set(key, value); }
        @JavascriptInterface public void remove(String key) { secureStore.remove(key); }
        @JavascriptInterface public void startLocation() { runOnUiThread(MainActivity.this::startLocationUpdates); }
        @JavascriptInterface public void stopLocation() { runOnUiThread(MainActivity.this::stopLocationUpdates); }
        @JavascriptInterface public void reload() { runOnUiThread(MainActivity.this::loadApplication); }
        @JavascriptInterface public void openLocationSettings() {
            runOnUiThread(() -> startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)));
        }
    }

    private static final class SecureStore {
        private static final String ALIAS = "smart-bamboo-mobile-session-v1";
        private static final String PREFS = "smart-bamboo-secure-store";
        private final SharedPreferences preferences;

        SecureStore(Context context) { preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }

        String get(String key) {
            try {
                String encoded = preferences.getString(key, null);
                if (encoded == null) return "";
                byte[] payload = Base64.decode(encoded, Base64.NO_WRAP);
                int ivLength = payload[0] & 0xff;
                byte[] iv = new byte[ivLength];
                byte[] encrypted = new byte[payload.length - ivLength - 1];
                System.arraycopy(payload, 1, iv, 0, ivLength);
                System.arraycopy(payload, ivLength + 1, encrypted, 0, encrypted.length);
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
                return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
            } catch (Exception error) {
                preferences.edit().remove(key).apply();
                return "";
            }
        }

        boolean set(String key, String value) {
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.ENCRYPT_MODE, key());
                byte[] encrypted = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
                byte[] iv = cipher.getIV();
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                output.write(iv.length);
                output.write(iv);
                output.write(encrypted);
                preferences.edit().putString(key, Base64.encodeToString(output.toByteArray(), Base64.NO_WRAP)).apply();
                return true;
            } catch (Exception error) {
                return false;
            }
        }

        void remove(String key) { preferences.edit().remove(key).apply(); }

        private SecretKey key() throws Exception {
            KeyStore store = KeyStore.getInstance("AndroidKeyStore");
            store.load(null);
            if (store.containsAlias(ALIAS)) {
                return ((KeyStore.SecretKeyEntry) store.getEntry(ALIAS, null)).getSecretKey();
            }
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build());
            return generator.generateKey();
        }
    }

    @Override
    protected void onDestroy() {
        if (locationManager != null) locationManager.removeUpdates(this);
        if (networkCallbackRegistered) {
            ((ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE)).unregisterNetworkCallback(networkCallback);
        }
        if (webView != null) {
            webView.removeJavascriptInterface("SmartBambooNative");
            webView.destroy();
        }
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
}
