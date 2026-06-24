import { Dropzone } from "@/components/Dropzone"
import { EstimateList } from "@/components/estimate/EstimateList"
import type { EstimateListItem } from "@/lib/api/estimates"

interface StartScreenProps {
  onFile: (file: File) => void
  onOpen: (item: EstimateListItem) => void
}

export function StartScreen({ onFile, onOpen }: StartScreenProps) {
  return (
    <div className="space-y-8 p-8">
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
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          Разобранные сметы
        </h2>
        <EstimateList onOpen={onOpen} />
      </section>
    </div>
  )
}
