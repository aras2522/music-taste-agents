const fieldClass =
  "rounded-md border border-[#d9cfc4] bg-white/80 p-3 outline-none ring-accent focus:ring-2";

export default function Field({
  label,
  value,
  onChange,
  placeholder,
  multiline = false,
  required = false,
  type = "text",
  className = "w-full",
  ...rest
}) {
  return (
    <label className="block">
      <span className="mb-1 block font-medium">{label}</span>
      {multiline ? (
        <textarea
          className={`${fieldClass} ${className}`}
          rows={4}
          required={required}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          {...rest}
        />
      ) : (
        <input
          className={`${fieldClass} ${className}`}
          type={type}
          required={required}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          {...rest}
        />
      )}
    </label>
  );
}
