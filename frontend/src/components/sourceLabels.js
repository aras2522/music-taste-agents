export const SOURCE_LABEL = {
  pitchfork: "Pitchfork",
  rym: "Rate Your Music",
};

export function sourceName(src) {
  return SOURCE_LABEL[src] || src;
}
