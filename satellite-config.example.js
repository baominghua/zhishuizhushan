window.SATELLITE_CONFIG = {
  // Browser key from Tianditu. Add your app domain/IP to the browser-key allowlist.
  tiandituTk: "YOUR_TIANDITU_BROWSER_KEY",
  tiandituType: "img",
  tiandituProxy: true,
  // Leave empty to reuse remoteApiBase. Set this if the proxy service is different.
  // tiandituProxyBaseUrl: "https://gis.example.com",
  tiandituProxyBaseUrl: "",

  // Leave empty for single-server testing on the current host:8010.
  // Set this when app and GIS are split, for example:
  // remoteApiBase: "https://gis.example.com",
  remoteApiBase: "",
};
