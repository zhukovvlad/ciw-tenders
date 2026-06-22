import { Dropzone } from "@/components/Dropzone"

interface StartScreenProps {
  onFile: (file: File) => void
}

export function StartScreen({ onFile }: StartScreenProps) {
  return (
    <div className="p-8">
      <Dropzone
        onFile={onFile}
        accept=".xlsx,.xls"
        id="estimate-file"
        ariaLabel="файл сметы"
        idleText="Перетащите смету или выберите файл"
        hotText="Отпустите файл сметы"
        hint=".xlsx · .xls — обрабатываются строки «Вид раздела = СМР»"
        className="min-h-64"
      />
    </div>
  )
}
