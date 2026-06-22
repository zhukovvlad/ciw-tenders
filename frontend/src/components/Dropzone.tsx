import { useState } from "react"
import { UploadCloud } from "lucide-react"
import { cn } from "@/lib/utils"

interface DropzoneProps {
  onFile: (file: File) => void
  accept: string
  id: string
  ariaLabel: string
  disabled?: boolean
  idleText?: string
  hotText?: string
  hint?: string
  className?: string
}

function matchesAccept(name: string, accept: string): boolean {
  const exts = accept
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s.startsWith("."))
  if (exts.length === 0) return true
  const lower = name.toLowerCase()
  return exts.some((ext) => lower.endsWith(ext))
}

export function Dropzone({
  onFile,
  accept,
  id,
  ariaLabel,
  disabled = false,
  idleText = "Перетащите файл или выберите",
  hotText = "Отпустите файл",
  hint,
  className,
}: DropzoneProps) {
  const [hot, setHot] = useState(false)

  function take(file: File | undefined | null) {
    if (!file) return
    if (matchesAccept(file.name, accept)) onFile(file)
  }

  return (
    <label
      htmlFor={id}
      onDragOver={(e) => {
        if (disabled) return
        e.preventDefault()
        setHot(true)
      }}
      onDragLeave={() => setHot(false)}
      onDrop={(e) => {
        e.preventDefault()
        setHot(false)
        if (disabled) return
        take(e.dataTransfer.files?.[0])
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-6 text-center transition-colors",
        hot
          ? "border-primary bg-[color-mix(in_srgb,var(--primary)_6%,transparent)]"
          : "border-[var(--ds-border-strong)]",
        disabled && "cursor-not-allowed opacity-60",
        className
      )}
    >
      <UploadCloud className="pointer-events-none size-7 text-muted-foreground" />
      <div className="pointer-events-none text-foreground">
        {hot ? hotText : idleText}
      </div>
      {hint && (
        <div className="pointer-events-none font-mono text-xs text-muted-foreground">
          {hint}
        </div>
      )}
      <input
        id={id}
        aria-label={ariaLabel}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(e) => take(e.target.files?.[0])}
      />
    </label>
  )
}
