import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
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
import { useAuth } from "@/lib/auth/useAuth"

const schema = z.object({
  email: z.string().min(1, "Введите логин"),
  password: z.string().min(1, "Введите пароль"),
})

type FormValues = z.infer<typeof schema>

export function LoginScreen() {
  const { login } = useAuth()

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  })

  async function onSubmit(values: FormValues) {
    try {
      await login(values.email, values.password)
    } catch (err) {
      const is401 = err instanceof ApiError && err.status === 401
      toast.error(
        is401 ? "Неверный логин или пароль" : "Не удалось войти, попробуйте позже"
      )
    }
  }

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-1 bg-background">
      <div className="font-display text-2xl">
        MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
      </div>
      <div className="mb-5 text-xs text-muted-foreground">
        Автоматизатор строительных смет
      </div>
      <Card>
        <CardContent className="pt-6">
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onSubmit)}
              className="flex w-60 flex-col gap-3"
            >
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs text-[var(--ds-text-2)]">
                      Логин
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
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs text-[var(--ds-text-2)]">
                      Пароль
                    </FormLabel>
                    <FormControl>
                      <Input type="password" className="mt-1" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" disabled={form.formState.isSubmitting}>
                Войти
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  )
}
