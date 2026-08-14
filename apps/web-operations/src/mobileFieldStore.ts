import type { MobileEvidenceUpload, MobileOfflinePackage, MobilePendingOperation, MobileTrackPayload } from "./api/types";

const STORAGE_KEY = "smart-bamboo-mobile-field-v1";
const DB_NAME = "smart-bamboo-mobile-field";
const BLOB_STORE = "evidence-blobs";

export interface MobileFieldState {
  offlinePackage: MobileOfflinePackage | null;
  operations: MobilePendingOperation[];
  tracks: MobileTrackPayload[];
  evidence: MobileEvidenceUpload[];
  activeTrack: MobileTrackPayload | null;
  lastSyncedAt: string;
}

export function emptyMobileFieldState(): MobileFieldState {
  return { offlinePackage: null, operations: [], tracks: [], evidence: [], activeTrack: null, lastSyncedAt: "" };
}

export function readMobileFieldState(): MobileFieldState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyMobileFieldState();
    return { ...emptyMobileFieldState(), ...(JSON.parse(raw) as Partial<MobileFieldState>) };
  } catch {
    return emptyMobileFieldState();
  }
}

export function writeMobileFieldState(state: MobileFieldState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function createClientId(prefix: string): string {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${random}`;
}

function openEvidenceDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(BLOB_STORE)) request.result.createObjectStore(BLOB_STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("无法打开现场文件仓库。"));
  });
}

export async function saveEvidenceBlob(id: string, blob: Blob): Promise<void> {
  const database = await openEvidenceDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(BLOB_STORE, "readwrite");
    transaction.objectStore(BLOB_STORE).put(blob, id);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error("现场文件保存失败。"));
  });
  database.close();
}

export async function readEvidenceBlob(id: string): Promise<Blob | null> {
  const database = await openEvidenceDatabase();
  const blob = await new Promise<Blob | null>((resolve, reject) => {
    const request = database.transaction(BLOB_STORE, "readonly").objectStore(BLOB_STORE).get(id);
    request.onsuccess = () => resolve((request.result as Blob | undefined) || null);
    request.onerror = () => reject(request.error || new Error("现场文件读取失败。"));
  });
  database.close();
  return blob;
}

export async function deleteEvidenceBlob(id: string): Promise<void> {
  const database = await openEvidenceDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(BLOB_STORE, "readwrite");
    transaction.objectStore(BLOB_STORE).delete(id);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error("现场文件清理失败。"));
  });
  database.close();
}
