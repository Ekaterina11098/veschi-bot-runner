export async function readStateResponse(response) {
  if (!response.ok) throw new Error('State unavailable');
  const text=await response.text();
  return text.trim() ? JSON.parse(text) : null;
}
