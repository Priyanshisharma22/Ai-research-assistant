interface ImportMetaEnv {
  readonly VITE_BACKEND_URL?: string
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any
  }
}

declare namespace React {
  type CSSProperties = Record<string, string | number | undefined>
  type ChangeEvent<T = any> = {
    target: T
    currentTarget: T
  }
}