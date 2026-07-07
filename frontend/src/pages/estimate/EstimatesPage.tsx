import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"
import { uploadEstimate } from "@/lib/api/estimates"
import type { EstimateListItem } from "@/lib/api/estimates"
import { apiErrorText } from "@/lib/api/errorText"
import { StartScreen } from "@/pages/estimate/StartScreen"
import { ProcessingScreen } from "@/pages/estimate/ProcessingScreen"

export function EstimatesPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [uploadingName, setUploadingName] = useState<string | null>(null)

  async function handleFile(file: File) {
    setUploadingName(file.name)
    try {
      const { id } = await uploadEstimate(file)
      navigate(`/estimates/${id}`)
    } catch (err) {
      console.error(err)
      toast.error(apiErrorText(err, t, "estimates.openFailed"))
      setUploadingName(null)
    }
  }

  if (uploadingName !== null)
    return (
      <ProcessingScreen
        fileName={uploadingName}
        progress={{ phase: "parsing", done: 0, total: 0, etaSeconds: null }}
      />
    )
  return (
    <StartScreen
      onFile={handleFile}
      onOpen={(item: EstimateListItem) => navigate(`/estimates/${item.id}`)}
    />
  )
}
