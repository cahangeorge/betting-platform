# Product Marketing Context

*Last updated: 2026-07-13 — auto-draft V1 from `DESIGN.md`, platform documentation and the public frontend copy. Unknown fields require product-owner validation.*

## Product Overview
**One-liner:** Betfront este un spațiu de lucru pentru analiza pariurilor sportive care păstrează trasabilitatea de la date și modele statistice până la revizuirea biletelor.

**What it does:** Platforma ajută utilizatorul să pregătească date sportive, să ruleze și să compare strategii predictive, să revizuiască oportunități și să genereze sau să urmărească bilete. Stările parțiale, erorile, sursa datasetului și rularea de predicție rămân vizibile. Analiza sprijină o decizie umană și nu reprezintă o garanție de câștig.

**Product category:** Sports betting analytics / decision-support workbench.

**Product type:** Aplicație web SvelteKit + API FastAPI, cu acces autentificat și capabilități PWA.

**Business model:** Unknown.

**Pricing:** Unknown.

## Target Audience
**Target companies:** Unknown. Repo-ul dovedește utilizatori individuali și roluri operaționale, dar nu dovedește un segment B2B sau o dimensiune de companie.

**Decision-makers:** Unknown.

**Primary use case:** Transformarea unui scope de date sportive pregătit într-o analiză comparabilă și într-un set de bilete care pot fi revizuite fără pierderea contextului.

**Jobs to be done:**
- să confirme că datele pentru competițiile și intervalele dorite sunt pregătite;
- să ruleze strategiile compatibile și să înțeleagă ce a reușit, eșuat, fost omis sau reutilizat;
- să compare candidați, să genereze bilete și să le revizuiască înainte de orice plasare;
- să urmărească joburi, rezultate și settlement fără a ascunde stările parțiale.

**Use cases:**
- configurare și comparație repetată pe desktop;
- revizuire pe tabletă;
- verificări de stare și ajustări mici pe mobil;
- lucru în condiții de scraping sau predicție lentă/degradată.

## Personas
| Persona | Cares about | Challenge | Value we promise |
|---------|-------------|-----------|------------------|
| Operator / non-expert | Un flux ghidat și setări implicite sigure | Instrumentele tehnice și stările joburilor sunt greu de interpretat | Pași expliciți, rezumate înainte de acțiuni și motive vizibile pentru blocaje |
| Betting analyst / power user | Strategii, piețe, edge, fiabilitate și lineage | Compararea rezultatelor din surse și rulări diferite | Context păstrat de la dataset la selecție și bilet |
| Technical administrator | Joburi, schedule-uri, erori și adevărul backendului | Eșecurile parțiale și side-effect-urile pot fi ascunse | Stări persistate, loguri inspectabile și rezultate parțiale etichetate |

## Problems & Pain Points
**Core problem:** Datele, analiza și biletele pot deveni pași izolați, iar utilizatorul pierde sursa, starea și limitele rezultatului.

**Why alternatives fall short:** Unknown — repo-ul nu conține cercetare validată despre competitori sau feedback comparativ de la clienți.

**What it costs them:** Timp de verificare, decizii bazate pe date vechi sau parțiale și risc de a confunda o estimare cu un rezultat sigur.

**Emotional tension:** Incertitudine privind prospețimea datelor, corectitudinea rulării și semnificația probabilităților.

## Competitive Landscape
**Direct competitors:** Unknown.

**Secondary competitors:** Unknown.

**Indirect competitors:** Foi de calcul, scripturi separate și verificare manuală — repo-ul sugerează că acestea fragmentează contextul, dar nu există cercetare de client care să confirme comparația.

## Differentiation
**Key differentiators:**
- lineage vizibil între dataset, rularea de predicție, candidat și bilet;
- rezultate parțiale, omise, reutilizate sau eșuate prezentate explicit;
- revizuire și confirmare înainte de plasare;
- execuție paper diferențiată de plasarea externă;
- un flux operațional comun: Prepare → Analyze → Opportunities → Tickets → Monitoring.

**How we do it differently:** Păstrăm contextul și starea în același workbench în loc să prezentăm doar un scor sau o selecție finală.

**Why that's better:** Utilizatorul poate verifica de unde provine un rezultat, ce limitări are și ce acțiune urmează.

**Why customers choose us:** Unknown — nu există dovezi de achiziție sau interviuri cu clienți în repo.

## Objections
| Objection | Response |
|-----------|----------|
| „Îmi garantează un câștig?” | Nu. Betfront oferă analiză și trasabilitate; probabilitățile și performanța istorică nu garantează rezultate viitoare. |
| „Pot avea încredere în date?” | Platforma expune sursa, momentul, starea și erorile disponibile, dar sursele externe pot fi incomplete sau întârziate. |
| „Plasează automat?” | Nu în fluxul documentat. Biletele sunt revizuite și confirmate, iar execuția paper este separată vizibil de orice plasare externă. |

**Anti-persona:** Persoane care caută certitudini, promisiuni de profit, recuperarea rapidă a pierderilor sau automatizare opacă fără revizuire. Utilizarea este destinată exclusiv adulților care îndeplinesc cerințele legale aplicabile.

## Switching Dynamics
**Push:** Date fragmentate, rulări greu de urmărit și rezultate fără lineage.

**Pull:** Un flux ghidat, stări explicite și comparație într-un singur spațiu.

**Habit:** Instrumente separate, foi de calcul și verificări manuale.

**Anxiety:** Calitatea datelor, acuratețea modelelor, migrarea procesului existent și riscul financiar.

## Customer Language
**How they describe the problem:** Unknown — nu există citate verbatim validate de la clienți.

**How they describe us:** Unknown — nu există testimoniale validate.

**Words to use:** trasabil, verificabil, probabilitate, estimare, revizuire, sursă, stare, limită, paper, decizie informată.

**Words to avoid:** garantat, sigur, fără risc, câștig rapid, recuperează pierderea, pariu sigur, profit garantat, urgență artificială.

**Glossary:**
| Term | Meaning |
|------|---------|
| Dataset pregătit | Scope-ul de date selectat și persistat înaintea analizei |
| Prediction run | Execuția unei strategii sau a unui grup de strategii pe un dataset |
| Lineage | Legătura verificabilă dintre date, rulare, candidat și bilet |
| Edge | Diferența estimată dintre probabilitatea modelului și probabilitatea implicită a cotei |
| Paper execution | Simulare separată de plasarea externă cu bani reali |
| Settlement | Clasificarea rezultatului unui bilet după disponibilitatea scorurilor finale |

## Brand Voice
**Tone:** Calm, profesionist și responsabil.

**Style:** Direct, operațional, bazat pe dovezi; explică motivele și limitele înaintea detaliilor tehnice.

**Personality:** Trustworthy, precise, calm, operational, configurable.

## Proof Points
**Metrics:** Unknown. Nu publica rate de succes, ROI sau acuratețe fără o sursă verificată și context metodologic.

**Customers:** Unknown.

**Testimonials:** Unknown. Nu există testimoniale validate în repo.

**Value themes:**
| Theme | Proof |
|-------|-------|
| Trasabilitate | Contractul de produs cere dataset, prediction run, timestamp și stare persistată |
| Onestitate operațională | Rezultatele parțiale și eșecurile rămân vizibile |
| Control uman | Revizuirea și confirmarea preced plasarea |
| Separarea riscului | Execuția paper este diferențiată de plasarea externă |

## Goals
**Business goal:** Unknown.

**Conversion action:** Crearea unui cont este CTA-ul public curent; validarea acestuia ca obiectiv comercial este Unknown.

**Current metrics:** Unknown.

## Validation Backlog
- validați piața principală și limba publică;
- definiți business model și pricing;
- documentați competitorii numai după cercetare;
- adăugați customer language, proof și testimoniale numai din surse reale;
- confirmați claims permise pentru date în timp real, modele și disponibilitatea plasării externe.
