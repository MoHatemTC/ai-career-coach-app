/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Where the API lives. Unset in dev, where Vite proxies /api to FastAPI. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
