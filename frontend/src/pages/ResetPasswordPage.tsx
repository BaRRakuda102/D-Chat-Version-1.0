import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { apiJson } from "../lib/api"
import { useThemeStore } from "../store/themeStore"
import { useTranslation } from "../hooks/useTranslation"

export default function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get("token") || ""
  const { language } = useThemeStore()
  const { t } = useTranslation(language)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")

  const requestReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setMessage("")

    try {
      const data = await apiJson<{ message: string }>("/api/v1/auth/password-reset/request", {
        method: "POST",
        body: JSON.stringify({ email }),
      })
      setMessage(data.message || t("resetEmailSent"))
    } catch (err) {
      setError(err instanceof Error ? err.message : t("error"))
    }
  }

  const confirmReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setMessage("")

    try {
      const data = await apiJson<{ message: string }>("/api/v1/auth/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
      })
      setMessage(data.message || t("resetPassword"))
    } catch (err) {
      setError(err instanceof Error ? err.message : t("error"))
    }
  }

  return (
    <div className="login-page">
      <div className="login-bg" />
      <div className="login-card" style={{ maxWidth: 460, width: "100%" }}>
        <div className="login-header">
          <h1>{t("resetPassword")}</h1>
          <p>{token ? t("resetPasswordDesc") : t("resetPasswordRequestDesc")}</p>
        </div>

        <form onSubmit={token ? confirmReset : requestReset} className="login-form">
          {token ? (
            <div className="form-group">
              <label>{t("newPassword")}</label>
              <input
                className="glass-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t("newPassword")}
                required
              />
            </div>
          ) : (
            <div className="form-group">
              <label>{t("email")}</label>
              <input
                className="glass-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("email")}
                required
              />
            </div>
          )}

          {error && <div className="login-error">{error}</div>}
          {message && <div className="login-success">{message}</div>}

          <button className="login-btn" type="submit">
            {token ? t("save") : t("requestReset")}
          </button>
        </form>

        <div className="auth-link-row">
          <span className="auth-note">{t("openInboxHint")}</span>
        </div>
        <div className="auth-link-row">
          <Link className="auth-link" to="/">
            {t("backToLogin")}
          </Link>
        </div>
      </div>
    </div>
  )
}
