import glob from 'fast-glob'

import { Layout } from '@/components/Layout'
import { type Section } from '@/components/SectionProvider'

export default async function DocsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  let pages = await glob('**/*.mdx', { cwd: 'src/app/docs' })
  let allSectionsEntries = (await Promise.all(
    pages.map(async (filename) => [
      '/docs/' + filename.replace(/(^|\/)page\.mdx$/, ''),
      (await import(`./${filename}`)).sections,
    ]),
  )) as Array<[string, Array<Section>]>
  let allSections = Object.fromEntries(allSectionsEntries)

  return <Layout allSections={allSections}>{children}</Layout>
}
