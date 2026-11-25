export async function request<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const res = await fetch("/api/projects" + path, {
    method,
    headers: data ? { "Content-Type": "application/json" } : undefined,
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string" ? error.detail : res.statusText,
    );
  }
  return res.json();
}
