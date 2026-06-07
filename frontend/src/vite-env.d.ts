/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL for the CogPrint backend API. Defaults to "/api" (Vite dev proxy).
   *  In a deploy, set this to the backend's absolute URL, e.g.
   *  https://cogprint-api.onrender.com */
  readonly VITE_API_BASE?: string;
  /** Researcher-dashboard gate password (client-side convenience only —
   *  real protection is the backend COGPRINT_API_KEY). */
  readonly VITE_RESEARCHER_PASSWORD?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
