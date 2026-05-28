const runtimeFallback =
	typeof window !== "undefined" &&
	window.location.hostname !== "localhost" &&
	window.location.hostname !== "127.0.0.1"
		? window.location.origin
		: "http://localhost:8000"

export const API_BASE = runtimeFallback.replace(/\/$/, "")
export const API = `${API_BASE}/api`
