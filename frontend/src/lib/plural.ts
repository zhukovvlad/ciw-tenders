// Русская плюрализация: forms = [один, несколько, много]
// («замечание», «замечания», «замечаний»). Возвращает форму — число
// подставляет вызывающий. Задел под i18n (этап 4): вызовы точечно заменятся
// i18next-плюрализацией, места уже параметризованы.
export function pluralizeRu(
  n: number,
  forms: [one: string, few: string, many: string]
): string {
  const abs = Math.abs(n)
  const mod10 = abs % 10
  const mod100 = abs % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1]
  return forms[2]
}
