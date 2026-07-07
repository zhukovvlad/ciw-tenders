import LanguageDetector from "i18next-browser-languagedetector"
import i18n from "i18next"
import { initReactI18next } from "react-i18next"

import ru from "@/locales/ru.json"
import tr from "@/locales/tr.json"

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { ru: { translation: ru }, tr: { translation: tr } },
    fallbackLng: "ru",
    supportedLngs: ["ru", "tr"],
    load: "languageOnly", // tr-TR / ru-RU → базовый tr / ru (иначе регион-вариант
    // не найдётся в supportedLngs и упадёт на fallback ru — турецкий браузер дал бы русский)
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "ciw.ui.lang",
      caches: ["localStorage"],
    },
    interpolation: { escapeValue: false }, // React уже экранирует
  })

i18n.on("languageChanged", (lng) => {
  document.documentElement.lang = lng
  document.title = i18n.t("common.appTitle") // локализуем title (§ниже)
})
document.documentElement.lang = i18n.language
document.title = i18n.t("common.appTitle")

export default i18n
