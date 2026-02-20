import { type Metadata } from 'next'

import { Providers } from '@/app/providers'

import '@/styles/tailwind.css'

export const metadata: Metadata = {
  title: {
    template: '%s - M4',
    default: 'M4 - Infrastructure for AI-Assisted Clinical Research',
  },
  description:
    'Give your AI agents clinical intelligence & access to MIMIC-IV, eICU, and more.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="flex min-h-full bg-white antialiased dark:bg-zinc-900">
        <Providers>
          <div className="w-full">{children}</div>
        </Providers>
      </body>
    </html>
  )
}
