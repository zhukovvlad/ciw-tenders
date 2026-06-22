import { useState } from "react"
import { toast } from "sonner"
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
import { ApiError } from "@/lib/api/client"
import { deleteAllArticles } from "@/lib/api/articles"

const CONFIRM_WORD = "УДАЛИТЬ"

export function WipeCatalog({ onWiped }: { onWiped: () => void }) {
  const [open, setOpen] = useState(false)
  const [word, setWord] = useState("")
  const [busy, setBusy] = useState(false)

  async function wipe() {
    setBusy(true)
    try {
      const n = await deleteAllArticles()
      toast.success(`Удалено ${n}`)
      setWord("")
      setOpen(false)
      onWiped()
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось очистить справочник"
      )
      setWord("")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="text-sm">
      <p className="mb-2 text-xs text-muted-foreground">
        Полностью удалит все статьи. Потребуется подтверждение вводом слова.
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
          <Button variant="destructive">Очистить справочник</Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Очистить весь справочник?</AlertDialogTitle>
            <AlertDialogDescription>
              Все статьи будут удалены безвозвратно. Введите «{CONFIRM_WORD}»,
              чтобы подтвердить.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Label htmlFor="wipe-confirm" className="sr-only">
            Подтверждение
          </Label>
          <Input
            id="wipe-confirm"
            value={word}
            onChange={(e) => setWord(e.target.value)}
            placeholder={CONFIRM_WORD}
          />
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={busy || word !== CONFIRM_WORD}
              onClick={() => void wipe()}
            >
              Очистить справочник
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
