import { useMemo } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import type { TFunction } from "i18next"
import { useTranslation } from "react-i18next"
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

function buildSchema(t: TFunction) {
  return z.object({
    email: z.string().trim().min(1, t("auth.enterLogin")),
    password: z.string().min(1, t("auth.enterPassword")),
  })
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>

export function LoginScreen() {
  const { login } = useAuth()
  const { t } = useTranslation()

  const schema = useMemo(() => buildSchema(t), [t])
  const [brandLeft, brandRight] = t("auth.brandHeading").split(" · ")

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  })

  async function onSubmit(values: FormValues) {
    // автоочистка root-ошибок в RHF менялась между версиями — сбрасываем явно
    form.clearErrors("root")
    try {
      await login(values.email, values.password)
    } catch (err) {
      const is401 = err instanceof ApiError && err.status === 401
      form.setError("root", {
        message: is401 ? t("auth.invalidCredentials") : t("auth.loginFailed"),
      })
    }
  }

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-1 bg-background">
      <div className="font-display text-2xl">
        {brandLeft} <span className="text-[var(--ds-accent-hover)]">·</span>{" "}
        {brandRight}
      </div>
      <div className="mb-5 text-xs text-muted-foreground">
        {t("auth.subtitle")}
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
                      {t("auth.loginLabel")}
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
                      {t("auth.passwordLabel")}
                    </FormLabel>
                    <FormControl>
                      <Input type="password" className="mt-1" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {t("auth.submit")}
              </Button>
              {form.formState.errors.root?.message && (
                <p className="text-sm text-destructive" role="alert">
                  {form.formState.errors.root.message}
                </p>
              )}
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  )
}
