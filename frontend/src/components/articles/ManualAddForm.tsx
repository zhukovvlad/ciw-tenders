import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Plus } from "lucide-react"
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
import { ApiError } from "@/lib/api/client"
import { createArticle } from "@/lib/api/articles"

const schema = z.object({
  article_code: z.string().trim().min(1, "Введите код статьи"),
  name: z.string().trim().min(1, "Введите наименование"),
  parent_code: z.string().optional(),
})

type FormValues = z.infer<typeof schema>

export function ManualAddForm({ onCreated }: { onCreated: () => void }) {
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
      toast.success(`Статья «${values.article_code}» добавлена`)
      form.reset()
      onCreated()
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось добавить статью"
      )
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
                Код
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
                Наименование
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
                Код родителя (необязательно)
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
          Добавить
        </Button>
      </form>
    </Form>
  )
}
