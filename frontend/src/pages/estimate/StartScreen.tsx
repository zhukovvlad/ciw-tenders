import { useState } from "react"
import { UploadCloud } from "lucide-react"

interface StartScreenProps {
  onFile: (file: File) => void
}

export function StartScreen({ onFile }: StartScreenProps) {
  const [hot, setHot] = useState(false)
  return (
    <div className="p-8">
      <label
        htmlFor="estimate-file"
        onDragOver={(e) => {
          e.preventDefault()
          setHot(true)
        }}
        onDragLeave={() => setHot(false)}
        onDrop={(e) => {
          e.preventDefault()
          setHot(false)
          const f = e.dataTransfer.files?.[0]
          if (f && /\.xlsx?$/i.test(f.name)) onFile(f)
        }}
        className={
          "flex min-h-64 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed text-center " +
          (hot
            ? "border-primary bg-[color-mix(in_srgb,var(--primary)_6%,transparent)]"
            : "border-[var(--ds-border-strong)]")
        }
      >
        <UploadCloud className="size-7 text-muted-foreground" />
        <div className="text-foreground">
          {hot ? "Отпустите файл сметы" : "Перетащите смету или выберите файл"}
        </div>
        <div className="font-mono text-xs text-muted-foreground">
          .xlsx · .xls — обрабатываются строки «Вид раздела = СМР»
        </div>
        <input
          id="estimate-file"
          aria-label="файл сметы"
          type="file"
          accept=".xlsx,.xls"
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f && /\.xlsx?$/i.test(f.name)) onFile(f)
          }}
        />
      </label>
    </div>
  )
}
