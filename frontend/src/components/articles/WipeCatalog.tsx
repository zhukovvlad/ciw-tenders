import { useState } from "react"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiErrorText } from "@/lib/api/errorText"
import { deleteAllArticles } from "@/lib/api/articles"

export function WipeCatalog({ onWiped }: { onWiped: () => void }) {
  const { t } = useTranslation()
  const confirmWord = t("articles.wipeConfirmWord")
  const [open, setOpen] = useState(false)
  const [word, setWord] = useState("")
  const [busy, setBusy] = useState(false)
  const canConfirm = word === confirmWord

  async function wipe() {
    setBusy(true)
    try {
      const n = await deleteAllArticles()
      toast.success(t("articles.wiped", { n }))
      setWord("")
      setOpen(false)
      onWiped()
    } catch (err) {
      toast.error(apiErrorText(err, t, "articles.wipeFailed"))
      setWord("")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="text-sm">
      <p className="mb-2 text-xs text-muted-foreground">
        {t("articles.wipeDesc")}
      </p>
      <AlertDialog
        open={open}
        onOpenChange={(next) => {
          // не закрывать диалог, пока идёт очистка
          if (!next && busy) return
          setOpen(next)
          if (!next) setWord("")
        }}
      >
        <AlertDialogTrigger asChild>
          <Button variant="destructive">{t("articles.wipeButton")}</Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("articles.wipeTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("articles.wipeBody", { word: confirmWord })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Label htmlFor="wipe-confirm" className="sr-only">
            {t("articles.wipeInputLabel")}
          </Label>
          <Input
            id="wipe-confirm"
            value={word}
            onChange={(e) => setWord(e.target.value)}
            placeholder={confirmWord}
          />
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={busy || !canConfirm}
              onClick={() => void wipe()}
            >
              {t("articles.wipeButton")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
