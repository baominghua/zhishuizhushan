export interface SmartBambooNativeBridge {
  version(): string;
  platform(): "android" | "ios";
  deviceId(): string;
  isOnline(): boolean;
  get(key: string): string;
  set(key: string, value: string): boolean;
  remove(key: string): void;
  startLocation(): void;
  stopLocation(): void;
  reload(): void;
  openLocationSettings(): void;
}

export interface NativeLocationDetail {
  status: "started" | "stopped" | "update" | "unavailable" | "provider-disabled";
  latitude?: number;
  longitude?: number;
  accuracy?: number | null;
  altitude?: number | null;
  timestamp?: number;
}

declare global {
  interface Window {
    SmartBambooNative?: SmartBambooNativeBridge;
  }

  interface WindowEventMap {
    "smart-bamboo-native:network": CustomEvent<{ online: boolean }>;
    "smart-bamboo-native:location": CustomEvent<NativeLocationDetail>;
  }
}

export function nativeBridge(): SmartBambooNativeBridge | null {
  return typeof window !== "undefined" && window.SmartBambooNative ? window.SmartBambooNative : null;
}

export function currentConnectivity(): boolean {
  const bridge = nativeBridge();
  if (bridge) {
    try { return bridge.isOnline(); } catch { /* WebView bridge may still be attaching. */ }
  }
  return typeof navigator === "undefined" ? true : navigator.onLine;
}

export function subscribeConnectivity(listener: (online: boolean) => void): () => void {
  const browserUpdate = () => listener(currentConnectivity());
  const nativeUpdate = (event: CustomEvent<{ online: boolean }>) => listener(Boolean(event.detail?.online));
  window.addEventListener("online", browserUpdate);
  window.addEventListener("offline", browserUpdate);
  window.addEventListener("smart-bamboo-native:network", nativeUpdate);
  return () => {
    window.removeEventListener("online", browserUpdate);
    window.removeEventListener("offline", browserUpdate);
    window.removeEventListener("smart-bamboo-native:network", nativeUpdate);
  };
}

export function subscribeNativeLocation(listener: (detail: NativeLocationDetail) => void): () => void {
  const update = (event: CustomEvent<NativeLocationDetail>) => listener(event.detail);
  window.addEventListener("smart-bamboo-native:location", update);
  return () => window.removeEventListener("smart-bamboo-native:location", update);
}
