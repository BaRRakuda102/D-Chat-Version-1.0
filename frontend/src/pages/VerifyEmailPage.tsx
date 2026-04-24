import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { CheckCircle2, MailWarning } from "lucide-react"
import { apiJson } from "../lib/api"
import { useThemeStore } from "../store/themeStore"
import { useTranslation } from "../hooks/useTranslation"

export default function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get("token") || ""
  const { language } = useThemeStore()
  const { t } = useTranslation(language)
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading")
  const [message, setMessage] = useState(t("verifyEmailPending"))

  useEffect(() => {
    const verify = async () => {
      if (!token) {
        setStatus("error")
        setMessage(t("error"))
        return
      }

      try {
        const data = await apiJson<{ message: string }>(`/api/v1/auth/verify-email?token=${encodeURIComponent(token)}`)
        setStatus("success")
        setMessage(data.message || t("verifyEmailSuccess"))
      } catch (err) {
        setStatus("error")
        setMessage(err instanceof Error ? err.message : t("error"))
      }
    }

    verify()
  }, [token, t])

  return (
    <div className="login-page">
      <div className="login-bg" />
      <div className="login-card" style={{ maxWidth: 440, width: "100%" }}>
        <div className="login-header">
          <h1>{t("verifyEmail")}</h1>
        </div>
        <div className="modal-body center">
          {status === "success" ? <CheckCircle2 size={56} /> : <MailWarning size={56} />}
          <p>{message}</p>
          <Link className="glass-button primary" to="/">
            {t("backToLogin")}
          </Link>
        </div>
      </div>
    </div>
  )
}
