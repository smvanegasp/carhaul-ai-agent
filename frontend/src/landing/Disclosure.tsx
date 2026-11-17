import { BELINDA, CARHAULER, Ext, REPO, SERGIO } from "../credits";

/** The disclosure, shared by the landing page's footer and the intro dialog so they never
 * say different things. */
export function Disclosure() {
  return (
    <div className="space-y-2 text-sm leading-relaxed text-muted">
      <p>
        <strong className="text-ink">Disclosure:</strong> Mia is an academic, non-commercial AI
        project developed by <Ext href={SERGIO}>Sergio Vanegas</Ext> and{" "}
        <Ext href={BELINDA}>Belinda Hu</Ext>. Shipping estimates use the public API of{" "}
        <Ext href={CARHAULER}>CarHauler247</Ext> and are not binding quotes.
      </p>
      <p>
        There are no real agents or booking services. The transfer-to-agent feature is a
        demonstration that routes to Sergio’s phone. Calls are saved as transcripts to improve
        Mia. The code is available on <Ext href={REPO}>GitHub</Ext>.
      </p>
    </div>
  );
}
