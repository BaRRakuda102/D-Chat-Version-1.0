import { Routes, Route, Navigate } from "react-router-dom"
import { Suspense, lazy, useEffect } from "react"
import { useAuthStore } from "./store/authStore"
import { apiJson, tryRefreshSession } from "./lib/api"

const LoginPage = lazy(() => import("./pages/LoginPage"))
const ChatPage = lazy(() => import("./pages/ChatPage"))
const VerifyEmailPage = lazy(() => import("./pages/VerifyEmailPage"))
const ResetPasswordPage = lazy(() => import("./pages/ResetPasswordPage"))

function AuthCheck({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, setUser, logout } = useAuthStore()

  useEffect(() => {
    let isCancelled = false

    const checkAuth = async () => {
      const isProtectedRoute = window.location.pathname.startsWith("/chat")

      try {
        const data = await apiJson<{ user: any }>("/api/v1/auth/me", {
          skipAutoRefresh: !isProtectedRoute,
        })
        if (!isCancelled) {
          setUser(data.user)
        }
      } catch {
        if (!isCancelled) {
          logout()
        }
      }
    }

    checkAuth()

    return () => {
      isCancelled = true
    }
  }, [logout, setUser])

  useEffect(() => {
    if (!isAuthenticated || !window.location.pathname.startsWith("/chat")) {
      return
    }

    const timer = window.setInterval(() => {
      void tryRefreshSession()
    }, 10 * 60 * 1000)

    return () => {
      window.clearInterval(timer)
    }
  }, [isAuthenticated])

  if (isLoading) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner" />
        <p>Loading...</p>
      </div>
    )
  }

  return <>{children}</>
}

export default function App() {
  const { isAuthenticated } = useAuthStore()

  return (
    <AuthCheck>
      <Suspense
        fallback={
          <div className="loading-screen">
            <div className="loading-spinner" />
            <p>Loading...</p>
          </div>
        }
      >
        <Routes>
          <Route
            path="/"
            element={isAuthenticated ? <Navigate to="/chat/0" /> : <LoginPage />}
          />
          <Route
            path="/chat/:roomId?"
            element={isAuthenticated ? <ChatPage /> : <Navigate to="/" />}
          />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Suspense>
    </AuthCheck>
  )
}
