import "@testing-library/jest-dom";

function createStorageShim(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear() {
      data.clear();
    },
    getItem(key: string) {
      return data.has(key) ? data.get(key)! : null;
    },
    key(index: number) {
      return Array.from(data.keys())[index] ?? null;
    },
    removeItem(key: string) {
      data.delete(key);
    },
    setItem(key: string, value: string) {
      data.set(String(key), String(value));
    }
  };
}

function ensureStorage(name: "localStorage" | "sessionStorage") {
  const existing = (globalThis as Record<string, unknown>)[name] as Partial<Storage> | undefined;
  const hasStorageApi =
    existing &&
    typeof existing.getItem === "function" &&
    typeof existing.setItem === "function" &&
    typeof existing.removeItem === "function" &&
    typeof existing.clear === "function";
  if (hasStorageApi) return;
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: createStorageShim()
  });
}

ensureStorage("localStorage");
ensureStorage("sessionStorage");

afterEach(() => {
  if (typeof localStorage?.clear === "function") {
    localStorage.clear();
  }
  if (typeof sessionStorage?.clear === "function") {
    sessionStorage.clear();
  }
});

