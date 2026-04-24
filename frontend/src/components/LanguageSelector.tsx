import { useState } from "react"

interface Opt {
  value: string
  label: string
}

export default function LanguageSelector({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  const [open, setOpen] = useState(false)
  const opts: Opt[] = [
    { value: "en", label: "English" },
    { value: "ru", label: "Русский" },
  ]
  const selected = opts.find((o) => o.value === value)
  return (
    <div className="lang-dropdown">
      <button className="lang-trigger" onClick={() => setOpen(!open)}>
        <span>{selected?.label}</span>
        <svg
          width="10"
          height="6"
          viewBox="0 0 10 6"
          fill="none"
          style={{
            transform: open ? "rotate(180deg)" : "rotate(0)",
            transition: "transform 0.2s",
          }}
        >
          <path
            d="M1 1L5 5L9 1"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open && (
        <div className="lang-menu">
          {opts.map((o) => (
            <button
              key={o.value}
              className={`lang-option ${o.value === value ? "active" : ""}`}
              onClick={() => {
                onChange(o.value)
                setOpen(false)
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
