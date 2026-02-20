import Image from 'next/image'

export function Logo(props: React.ComponentPropsWithoutRef<'div'>) {
  return (
    <div className="flex items-center gap-2" {...props}>
      <Image
        src="/images/m4_logo_transparent.png"
        alt="M4"
        width={456}
        height={237}
        className="h-7 w-auto"
      />
    </div>
  )
}
