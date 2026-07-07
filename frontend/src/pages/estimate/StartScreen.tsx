import { useTranslation } from "react-i18next"
import { Dropzone } from "@/components/Dropzone"
import { EstimateList } from "@/components/estimate/EstimateList"
import type { EstimateListItem } from "@/lib/api/estimates"

interface StartScreenProps {
  onFile: (file: File) => void
  onOpen: (item: EstimateListItem) => void
}

export function StartScreen({ onFile, onOpen }: StartScreenProps) {
  const { t } = useTranslation()
  return (
    <div className="space-y-8 p-8">
      <Dropzone
        onFile={onFile}
        accept=".xlsx,.xls"
        id="estimate-file"
        ariaLabel={t("estimates.dropAriaLabel")}
        idleText={t("estimates.dropIdle")}
        hotText={t("estimates.dropHot")}
        hint={t("estimates.dropHint")}
        className="min-h-64"
      />
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          {t("estimates.parsedHeading")}
        </h2>
        <EstimateList onOpen={onOpen} />
      </section>
    </div>
  )
}
