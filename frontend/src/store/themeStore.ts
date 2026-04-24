import { create } from "zustand"

interface ThemeState {
  theme: "dark" | "light"
  language: string
  setTheme: (theme: "dark" | "light") => void
  setLanguage: (language: string) => void
  toggleTheme: () => void
}

function getStored() {
  try {
    return {
      theme: (localStorage.getItem("theme") as "dark" | "light") || "dark",
      language: localStorage.getItem("language") || "en",
    }
  } catch {
    return { theme: "dark" as const, language: "en" }
  }
}

const stored = getStored()

if (typeof window !== "undefined") {
  document.documentElement.classList.remove("light", "dark")
  document.documentElement.classList.add(stored.theme)
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: stored.theme,
  language: stored.language,
  setTheme: (theme) => {
    localStorage.setItem("theme", theme)
    document.documentElement.classList.remove("light", "dark")
    document.documentElement.classList.add(theme)
    set({ theme })
  },
  setLanguage: (language) => {
    localStorage.setItem("language", language)
    set({ language })
  },
  toggleTheme: () => {
    set((state) => {
      const newTheme = state.theme === "dark" ? "light" : "dark"
      localStorage.setItem("theme", newTheme)
      document.documentElement.classList.remove("light", "dark")
      document.documentElement.classList.add(newTheme)
      return { theme: newTheme }
    })
  },
}))
