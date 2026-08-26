import { createContext, useCallback, useContext, useEffect, useState } from 'react'

interface ToastState {
  toast: (message: string) => void
}

const ToastContext = createContext<ToastState | null>(null)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [message, setMessage] = useState('')

  const toast = useCallback((next: string) => setMessage(next), [])

  useEffect(() => {
    if (!message) return
    const timer = setTimeout(() => setMessage(''), 2600)
    return () => clearTimeout(timer)
  }, [message])

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* polite: a confirmation should never interrupt what's being read */}
      <div className="toast-region" role="status" aria-live="polite">
        {message && <div className="toast">{message}</div>}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastState {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast outside ToastProvider')
  return ctx
}
