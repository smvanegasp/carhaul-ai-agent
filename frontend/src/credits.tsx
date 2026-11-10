/** Who built Mia, and where things come from (About popup and sidebar). */
export const SERGIO = "https://www.linkedin.com/in/sergio-vanegas/";
export const BELINDA = "https://www.linkedin.com/in/belinda-hu/";
export const REPO = "https://github.com/smvanegasp/carhaul-ai-agent";
export const CARHAULER = "https://carhauler247.com/";

export function Ext({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-brand underline-offset-2 hover:underline"
    >
      {children}
    </a>
  );
}
