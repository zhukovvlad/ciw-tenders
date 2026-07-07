import { useMemo } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Plus } from "lucide-react"
import type { TFunction } from "i18next"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { apiErrorText } from "@/lib/api/errorText"
import { createArticle } from "@/lib/api/articles"

function buildSchema(t: TFunction) {
  return z.object({
    article_code: z.string().trim().min(1, t("articles.enterCode")),
    name: z.string().trim().min(1, t("articles.enterName")),
    parent_code: z.string().optional(),
  })
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>

export function ManualAddForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation()
  const schema = useMemo(() => buildSchema(t), [t])

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { article_code: "", name: "", parent_code: "" },
  })

  async function onSubmit(values: FormValues) {
    try {
      await createArticle({
        article_code: values.article_code,
        name: values.name,
        parent_code: values.parent_code?.trim() || null,
      })
      toast.success(t("articles.added", { code: values.article_code }))
      form.reset()
      onCreated()
    } catch (err) {
      toast.error(apiErrorText(err, t, "articles.addFailed"))
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="grid gap-3 sm:grid-cols-[160px_1fr_160px_auto]"
      >
        <FormField
          control={form.control}
          name="article_code"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs text-[var(--ds-text-2)]">
                {t("articles.codeLabel")}
              </FormLabel>
              <FormControl>
                <Input className="mt-1" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs text-[var(--ds-text-2)]">
                {t("articles.nameLabel")}
              </FormLabel>
              <FormControl>
                <Input className="mt-1" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="parent_code"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs text-[var(--ds-text-2)]">
                {t("articles.parentLabel")}
              </FormLabel>
              <FormControl>
                <Input className="mt-1" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button
          type="submit"
          disabled={form.formState.isSubmitting}
          className="self-end"
        >
          <Plus className="size-4" />
          {t("articles.add")}
        </Button>
      </form>
    </Form>
  )
}
