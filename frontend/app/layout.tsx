'use client'
import './globals.css'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import Sidebar from '@/components/Sidebar'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, retry: 2 } },
  }))

  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        <QueryClientProvider client={queryClient}>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-y-auto">
              {children}
            </main>
          </div>
        </QueryClientProvider>
      </body>
    </html>
  )
}
