'use client'

import { motion } from 'framer-motion'
import Image from 'next/image'
import Link from 'next/link'

import { ThemeToggle } from '@/components/ThemeToggle'
import { GridPattern } from '@/components/GridPattern'

function Header() {
  return (
    <header className="fixed inset-x-0 top-0 z-50 flex h-14 items-center justify-between px-4 backdrop-blur-sm sm:px-6 lg:px-8 bg-white/80 dark:bg-zinc-900/80">
      <Link href="/" className="flex items-center gap-2">
        <Image
          src="/images/m4_logo_transparent.png"
          alt="M4"
          width={456}
          height={237}
          className="h-7 w-auto"
        />
      </Link>
      <div className="flex items-center gap-6">
        <nav className="hidden md:block">
          <ul className="flex items-center gap-6">
            <li>
              <Link
                href="/docs"
                className="text-sm text-zinc-600 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
              >
                Documentation
              </Link>
            </li>
            <li>
              <Link
                href="https://github.com/hannesill/m4"
                className="text-sm text-zinc-600 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
              >
                GitHub
              </Link>
            </li>
            <li>
              <Link
                href="https://pypi.org/project/m4-infra/"
                className="text-sm text-zinc-600 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
              >
                PyPI
              </Link>
            </li>
          </ul>
        </nav>
        <ThemeToggle />
      </div>
    </header>
  )
}

function Hero() {
  return (
    <div className="relative overflow-hidden">
      <div className="absolute inset-0 -z-10">
        <div className="absolute top-0 left-1/2 -ml-152 h-100 w-325 dark:mask-[linear-gradient(white,transparent)]">
          <div className="absolute inset-0 bg-linear-to-r from-[#dc2626] to-[#3b82f6] mask-[radial-gradient(farthest-side_at_top,white,transparent)] opacity-40 dark:from-[#dc2626]/30 dark:to-[#3b82f6]/30 dark:opacity-100">
            <GridPattern
              width={72}
              height={56}
              x={-12}
              y={4}
              squares={[
                [4, 3],
                [2, 1],
                [7, 3],
                [10, 6],
              ]}
              className="absolute inset-x-0 inset-y-[-50%] h-[200%] w-full skew-y-[-18deg] fill-black/45 stroke-black/60 mix-blend-overlay dark:fill-white/4 dark:stroke-white/8"
            />
          </div>
        </div>
      </div>
      <div className="mx-auto max-w-7xl px-6 pt-32 pb-24 sm:pt-40 sm:pb-32 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="text-4xl font-bold tracking-tight text-zinc-900 sm:text-6xl dark:text-white"
          >
            Infrastructure for AI-Assisted Clinical Research
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="mt-6 text-lg/8 text-zinc-600 dark:text-zinc-400"
          >
            Give your AI agents clinical intelligence & access to MIMIC-IV,
            eICU, and more. Initialize datasets as fast local databases, connect
            your AI client, and start asking clinical questions in natural
            language.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="mt-10 flex items-center justify-center gap-x-4"
          >
            <Link
              href="/docs/getting-started"
              className="rounded-full bg-zinc-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-zinc-700 dark:bg-red-500 dark:hover:bg-red-400"
            >
              Get started
            </Link>
            <Link
              href="/docs"
              className="rounded-full px-4 py-2 text-sm font-semibold text-zinc-900 ring-1 ring-inset ring-zinc-900/10 hover:bg-zinc-50 dark:text-white dark:ring-white/10 dark:hover:bg-white/5"
            >
              Documentation
            </Link>
          </motion.div>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="mt-8"
          >
            <InstallSnippet />
          </motion.div>
        </div>
      </div>
    </div>
  )
}

function InstallSnippet() {
  return (
    <div className="mx-auto max-w-md">
      <div className="rounded-xl bg-zinc-900 p-4 ring-1 ring-white/10 dark:bg-zinc-800">
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <div className="flex gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
            <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
            <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
          </div>
          <span className="ml-2">Terminal</span>
        </div>
        <div className="mt-3 font-mono text-sm">
          <div className="text-zinc-400">
            <span className="text-red-400">$</span> uv add m4-infra
          </div>
          <div className="text-zinc-400">
            <span className="text-red-400">$</span> m4 init mimic-iv-demo
          </div>
          <div className="text-zinc-400">
            <span className="text-red-400">$</span> m4 config claude
            --quick
          </div>
        </div>
      </div>
    </div>
  )
}

function FeatureCard({
  title,
  description,
  icon,
}: {
  title: string
  description: string
  icon: React.ReactNode
}) {
  return (
    <div className="relative rounded-2xl border border-zinc-900/5 p-6 dark:border-white/5">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-900/5 dark:bg-white/5">
        {icon}
      </div>
      <h3 className="mt-4 text-sm font-semibold text-zinc-900 dark:text-white">
        {title}
      </h3>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        {description}
      </p>
    </div>
  )
}

function Features() {
  return (
    <div className="mx-auto max-w-7xl px-6 py-24 lg:px-8">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="text-3xl font-bold tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
          Built for clinical research
        </h2>
        <p className="mt-4 text-lg text-zinc-600 dark:text-zinc-400">
          Everything you need to go from clinical question to published result.
        </p>
      </div>
      <div className="mx-auto mt-16 grid max-w-5xl grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <FeatureCard
          title="Clinical semantics"
          description="Agent skills encode validated clinical concepts from MIT-LCP repositories. 'Find sepsis patients' produces clinically correct queries, not just valid SQL."
          icon={
            <svg
              className="h-5 w-5 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"
              />
            </svg>
          }
        />
        <FeatureCard
          title="Multi-modal data"
          description="Query labs in MIMIC-IV, search discharge summaries in MIMIC-IV-Note, all through the same interface. Tools adapt to each dataset's modality."
          icon={
            <svg
              className="h-5 w-5 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 0 1-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0 1 12 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M13.125 12h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125M20.625 12c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5M12 14.625v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 14.625c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125m0 0v1.5c0 .621-.504 1.125-1.125 1.125"
              />
            </svg>
          }
        />
        <FeatureCard
          title="Python API"
          description="Returns DataFrames that integrate with pandas, scipy, and matplotlib. Turn your AI assistant into a research partner that executes complete analysis workflows."
          icon={
            <svg
              className="h-5 w-5 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5"
              />
            </svg>
          }
        />
        <FeatureCard
          title="Cross-dataset research"
          description="Switch between MIMIC-IV and eICU seamlessly. Skills handle database-specific translations for external validation studies."
          icon={
            <svg
              className="h-5 w-5 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"
              />
            </svg>
          }
        />
        <FeatureCard
          title="63 derived tables"
          description="Pre-computed SOFA, APACHE III, SAPS-II, sepsis cohorts, KDIGO AKI staging, and more from peer-reviewed MIT-LCP repositories."
          icon={
            <svg
              className="h-5 w-5 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125"
              />
            </svg>
          }
        />
        <FeatureCard
          title="Local & cloud"
          description="Prototype locally with DuckDB, scale to BigQuery for full datasets. Same queries work on both backends without changes."
          icon={
            <svg
              className="h-5 w-5 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.25 15a4.5 4.5 0 0 0 4.5 4.5H18a3.75 3.75 0 0 0 1.332-7.257 3 3 0 0 0-3.758-3.848 5.25 5.25 0 0 0-10.233 2.33A4.502 4.502 0 0 0 2.25 15Z"
              />
            </svg>
          }
        />
      </div>
    </div>
  )
}

function Datasets() {
  const datasets = [
    {
      name: 'mimic-iv-demo',
      patients: '100',
      modality: 'Tabular',
      access: 'Free',
    },
    {
      name: 'mimic-iv',
      patients: '365k',
      modality: 'Tabular',
      access: 'Credentialed',
    },
    {
      name: 'mimic-iv-note',
      patients: '331k notes',
      modality: 'Notes',
      access: 'Credentialed',
    },
    {
      name: 'eicu',
      patients: '200k+',
      modality: 'Tabular',
      access: 'Credentialed',
    },
  ]

  return (
    <div className="border-t border-zinc-900/5 dark:border-white/5">
      <div className="mx-auto max-w-7xl px-6 py-24 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
            Supported datasets
          </h2>
          <p className="mt-4 text-lg text-zinc-600 dark:text-zinc-400">
            From a free 100-patient demo to full research databases. Add your
            own via JSON definitions.
          </p>
        </div>
        <div className="mx-auto mt-12 max-w-3xl">
          <div className="overflow-hidden rounded-2xl border border-zinc-900/5 dark:border-white/5">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-900/5 bg-zinc-50 dark:border-white/5 dark:bg-zinc-800/50">
                  <th className="px-4 py-3 text-left font-semibold text-zinc-900 dark:text-white">
                    Dataset
                  </th>
                  <th className="px-4 py-3 text-left font-semibold text-zinc-900 dark:text-white">
                    Patients
                  </th>
                  <th className="px-4 py-3 text-left font-semibold text-zinc-900 dark:text-white">
                    Modality
                  </th>
                  <th className="px-4 py-3 text-left font-semibold text-zinc-900 dark:text-white">
                    Access
                  </th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((d) => (
                  <tr
                    key={d.name}
                    className="border-b border-zinc-900/5 last:border-0 dark:border-white/5"
                  >
                    <td className="px-4 py-3 font-medium text-zinc-900 dark:text-white">
                      {d.name}
                    </td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                      {d.patients}
                    </td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                      {d.modality}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          d.access === 'Free'
                            ? 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400'
                            : 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-400'
                        }`}
                      >
                        {d.access}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

function Citation() {
  return (
    <div className="border-t border-zinc-900/5 dark:border-white/5">
      <div className="mx-auto max-w-7xl px-6 py-24 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
            Citation
          </h2>
          <p className="mt-4 text-lg text-zinc-600 dark:text-zinc-400">
            M4 builds on the{' '}
            <Link
              href="https://github.com/rafiattrach/m3"
              className="text-red-500 hover:text-red-600"
            >
              M3
            </Link>{' '}
            project. Please cite their work when using M4.
          </p>
        </div>
        <div className="mx-auto mt-8 max-w-2xl">
          <div className="rounded-xl bg-zinc-900 p-4 ring-1 ring-white/10 dark:bg-zinc-800">
            <pre className="overflow-x-auto text-xs text-zinc-300">
              {`@article{attrach2025conversational,
  title={Conversational LLMs Simplify Secure Clinical
         Data Access, Understanding, and Analysis},
  author={Attrach, Rafi Al and Moreira, Pedro and
          Fani, Rajna and Umeton, Renato and
          Celi, Leo Anthony},
  journal={arXiv preprint arXiv:2507.01053},
  year={2025}
}`}
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}

function Footer() {
  return (
    <footer className="border-t border-zinc-900/5 dark:border-white/5">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:px-8">
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            MIT License &copy; {new Date().getFullYear()} MIT Critical Data
          </p>
          <div className="flex gap-6">
            <Link
              href="https://github.com/hannesill/m4"
              className="text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300"
            >
              GitHub
            </Link>
            <Link
              href="https://pypi.org/project/m4-infra/"
              className="text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300"
            >
              PyPI
            </Link>
            <Link
              href="https://github.com/hannesill/m4/issues"
              className="text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300"
            >
              Report an Issue
            </Link>
          </div>
        </div>
      </div>
    </footer>
  )
}

export default function Home() {
  return (
    <>
      <Header />
      <main>
        <Hero />
        <Features />
        <Datasets />
        <Citation />
      </main>
      <Footer />
    </>
  )
}
