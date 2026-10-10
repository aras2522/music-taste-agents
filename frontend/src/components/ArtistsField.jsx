import Field from "./Field";

export default function ArtistsField({ value, onChange }) {
  return (
    <Field
      label="Seed artists"
      placeholder="Bad Bunny, Olivia Rodrigo"
      value={value}
      onChange={onChange}
    />
  );
}
