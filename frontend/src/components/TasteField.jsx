import Field from "./Field";

export default function TasteField({ value, onChange }) {
  return (
    <Field
      label="What do you like?"
      placeholder="e.g. dreamy bedroom pop, soft indie rock"
      multiline
      required
      value={value}
      onChange={onChange}
    />
  );
}
