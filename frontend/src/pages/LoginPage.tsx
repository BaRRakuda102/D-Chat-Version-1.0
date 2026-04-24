import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import {
  Shield,
  Users,
  Image as ImageIcon,
  Settings,
  Languages,
  X,
  Lock,
  Smartphone,
  Moon,
  Sun,
  Mail,
} from "lucide-react"
import { useAuthStore } from "../store/authStore"
import { useThemeStore } from "../store/themeStore"
import { useTranslation } from "../hooks/useTranslation"
import LanguageSelector from "../components/LanguageSelector"
import { apiJson } from "../lib/api"

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((state) => state.setAuth)
  const { theme, toggleTheme, language, setLanguage } = useThemeStore()
  const { t } = useTranslation(language)

  const [mode, setMode] = useState<"login" | "register">("login")
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [showSettings, setShowSettings] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setNotice("")

    if (!username.trim() || !password.trim() || (mode === "register" && !email.trim())) {
      setError(t("fillAllFields"))
      return
    }

    try {
      if (mode === "login") {
        const data = await apiJson<{ user: any }>("/api/v1/auth/login", {
          method: "POST",
          body: JSON.stringify({
            username: username.trim(),
            password,
          }),
        })
        setAuth(data.user)
        navigate("/chat/0")
        return
      }

      const data = await apiJson<{ message: string }>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          username: username.trim(),
          email: email.trim(),
          display_name: username.trim(),
          password,
        }),
      })
      setMode("login")
      setEmail("")
      setPassword("")
      setNotice(data.message || t("verificationSent"))
    } catch (err) {
      setError(err instanceof Error ? err.message : t("networkError"))
    }
  }

  const features = [
    {
      icon: <Lock size={20} />,
      title: t("encryption"),
      desc: t("encryptionDesc"),
    },
    {
      icon: <Users size={20} />,
      title: t("groupChats"),
      desc: t("groupChatsDesc"),
    },
    {
      icon: <ImageIcon size={20} />,
      title: t("mediaSharing"),
      desc: t("mediaSharingDesc"),
    },
    {
      icon: <Smartphone size={20} />,
      title: t("crossPlatform"),
      desc: t("crossPlatformDesc"),
    },
  ]

  return (
    <div className="login-page">
      <div className="login-bg" />
      <div className="login-container">
        <div className="login-left">
          <div className="login-brand">
            <div className="login-brand-icon">
              <Shield size={24} />
            </div>
            <div className="login-brand-text">D-Chat</div>
          </div>
          <div>
            <h2 className="login-headline">{t("welcomeTitle")}</h2>
            <p className="login-subheadline">{t("welcomeDesc")}</p>
          </div>
          <div className="login-features">
            {features.map((feature, index) => (
              <div key={index} className="login-feature-card">
                <div className="login-feature-icon">{feature.icon}</div>
                <div>
                  <p className="login-feature-title">{feature.title}</p>
                  <p className="login-feature-desc">{feature.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="login-card">
          <div className="login-header">
            <h1>{mode === "login" ? t("welcomeBack") : t("createAccount")}</h1>
            <p>{mode === "login" ? t("signInToContinue") : t("signUpToGetStarted")}</p>
          </div>
          <form onSubmit={handleSubmit} className="login-form">
            <div className="form-group">
              <label>{t("username")}</label>
              <input
                className="glass-input"
                placeholder={t("username")}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            {mode === "register" && (
              <div className="form-group">
                <label>{t("email")}</label>
                <input
                  className="glass-input"
                  type="email"
                  placeholder={t("email")}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            )}
            <div className="form-group">
              <label>{t("password")}</label>
              <input
                className="glass-input"
                type="password"
                placeholder={t("password")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && <div className="login-error">{error}</div>}
            {notice && <div className="login-success">{notice}</div>}
            <button type="submit" className="login-btn">
              {mode === "login" ? t("signIn") : t("signUp")}
            </button>
          </form>
          {mode === "login" && (
            <div className="auth-link-row">
              <Link className="auth-link" to="/reset-password">
                <Mail size={14} /> {t("forgotPassword")}
              </Link>
            </div>
          )}
          <div className="login-switch">
            {mode === "login" ? (
              <span>
                {t("dontHaveAccount")}{" "}
                <button
                  className="link"
                  onClick={() => {
                    setMode("register")
                    setError("")
                    setNotice("")
                  }}
                >
                  {t("signUp")}
                </button>
              </span>
            ) : (
              <span>
                {t("alreadyHaveAccount")}{" "}
                <button
                  className="link"
                  onClick={() => {
                    setMode("login")
                    setError("")
                    setNotice("")
                  }}
                >
                  {t("signIn")}
                </button>
              </span>
            )}
          </div>
          <div className="login-footer">{t("securePrivateEncrypted")}</div>
        </div>
      </div>

      <button
        className="settings-toggle"
        onClick={() => setShowSettings(true)}
        title={t("settings")}
      >
        <Settings size={20} />
      </button>

      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <Settings size={16} /> {t("settings")}
              <button className="icon-btn" onClick={() => setShowSettings(false)}>
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              <div className="settings-block">
                <div className="settings-label">
                  <Languages size={14} /> {t("language")}
                </div>
                <LanguageSelector value={language} onChange={setLanguage} />
              </div>
              <div className="settings-block">
                <div className="settings-label">
                  {theme === "dark" ? <Moon size={14} /> : <Sun size={14} />} {t("theme")}
                </div>
                <button className="glass-button small" onClick={toggleTheme}>
                  {theme === "dark" ? t("light") : t("dark")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
