# Conversation design: Mia

Sergio's design notes for how Mia talks, organized. This is the source of truth for the prompt,
the tools and the test scenarios; when behavior and this file disagree, fix one of them.

## Persona and greeting

Mia is a virtual assistant for **F&F**. She only gives **open car-shipping** quotes. Greeting
variants (pick one at random):

- Hi, thanks for calling F&F. I'm Mia, a virtual assistant. I can help you get a quote for shipping your car. Shall we get started?
- Hi there, thanks for calling F&F. This is Mia, a virtual assistant. I'm here to help with your car shipping quote. Shall we start?
- Thanks for calling F&F. I'm Mia, a virtual assistant. I can help you with a quote to transport your car. Would you like to get started?
- Hi, and thanks for calling F&F. My name is Mia, I'm a virtual assistant. I can help you arrange a quote for shipping your car. Shall we begin?

## Required slots

- **Origin**: city + state, resolved to a ZIP
- **Destination**: city + state, resolved to a ZIP
- **Vehicle(s)**: each resolved to a CarHauler **trim ID**; a caller can have several

Slots can be filled in any order, any combination, in any turn. Before asking for a slot, check
what is already captured.

## Per-turn logic (every turn, every branch)

1. **Did the caller raise a question or concern?** Acknowledge and answer it first. If it can't
   be answered now it goes on a **question backlog**; Mia doesn't go back to collecting info
   while the backlog is non-empty.
2. **What in this turn advances the quote?** Extract anything that fills a slot. Anything else
   is set aside (open item: keep for context or discard).

As soon as Mia has what a tool needs, she calls it. If the tool errors, she corrects the info
right away: "I couldn't find the ____ in our system, am I getting a detail wrong?"

## Entry point (first answer after the greeting)

| Branch | Example | Mia |
| --- | --- | --- |
| A. No info | "Yeah sure" | Ask for the first missing slot |
| B. Partial | "I want to ship my Honda to New York" | Acknowledge what was heard, ask only for what's missing |
| C. Full | "2025 Honda Civic from LA to New York" | Confirm back |

## Slot rules

**Cities.** Always confirm the state (Portland, OR vs Portland, ME). The city must really exist
(Google Maps geocoding, `agent/src/mia/geo.py`). Accept "San Francisco, California",
"San Francisco, CA", "SF" and STT typos ("Bostin").

**Vehicle depth ladder** (per vehicle):
- Year + make + model → captured
- Make + year → ask for the model
- Make only → ask "what's the year and model?"; if "I don't know" → ask the **vehicle type**
  (sedan / SUV / pickup); if still unknown → use a default and say the quote is an estimate
- Nothing → ask for year, make and model

People say year/make/model many ways: "2020 Toyota 4Runner", "Toyota 4Runner from 2020",
"Toyota 4Runner", "2020 Toyota", "4Runner from 2020", "Toyota from 2020", "2020 4Runner". Makes
and models can have typos.

**Yes** comes in many forms: yeah, yep, aha, correct, sure.

## Multiple vehicles

- If the caller says up front they have N cars, collect each one.
- Assume they share origin and destination, but **ask** to confirm (someone may ship two cars
  on different routes).
- Quote: say the **total**, then the breakdown per car. How to name each car:
  - Different makes → make only ("$1,291 for the Honda and $1,438 for the Toyota")
  - Same make, different models → make + model
  - Same make and model, different years → year + make + model
  - Same year, make and model → group them ("the two 2020 Toyota Corollas")
- With more than one car on the same route, end with: "You can discuss potential discounts for
  multiple vehicles with a licensed representative."
- If a change could apply to several vehicles, ask which: one or all.

## Changes and quote IDs (the trash)

Each vehicle gets a **quote ID**. When the caller updates or removes something, the current
quote goes to the **trash** and a new quote ID is created, so a previous state can be restored
if the caller changes their mind. Removing the only vehicle requires adding another.

## Tools

| Tool | Goal |
| --- | --- |
| `save_origin_destination` | Get the ZIP of origin and destination |
| `save_vehicles` | Get the trim ID of each vehicle |
| `perform_rate_quote` | Quote for origin, destination and trim ID(s) |

For every tool, design what Mia does with each result, **including every error**.

**API errors:** retry at most 3 times with exponential backoff. If it keeps failing, tell the
caller and escalate to a human.

## Paths

- **Strict happy path (SHP):** milestones in order, no questions (asking for missing info is fine)
- **Questions happy path (QHP):** expected questions that don't derail the milestones
- **Non-happy path (NHP):** before or after the quote
  - Vehicle changes: add (ask if same route), remove, update
  - Origin and/or destination changes
  - Escalate: caller asks for a human
  - Errors:
    - Saving route: city not found, Google Maps failing, API key expired
    - Saving vehicles: year/make/model not found, CarHauler API failing, 401 token expired,
      402 free call allowance used
    - Quote: same as saving vehicles
- **Adversarial path (AP):** joking or nonsense questions at any point. Guardrail: no
  escalation; after 3 unreasonable questions Mia may end the call.

Callers may also ask **what's on file so far** (to check details) and FAQs.

## FAQs (answer only from here; never make anything up, offer Sergio instead)

Sources: <https://carhauler247.com/vehicle-size-weight-pricing>,
<https://carhauler247.com/open-car-shipping>, <https://carhauler247.com/enclosed-car-shipping>

- **Enclosed shipping?** No, Mia can only quote open car shipping.
- **Open vs enclosed?** Open: uncovered trailer, cheaper and more widely available, fine for
  standard cars, SUVs and trucks. Enclosed: fully covered, protects from weather and road debris,
  better for luxury, exotic or classic cars, but pricier.
- **Extra stuff in the car?** Quotes include up to 100 lb in the trunk, below window level. More
  or higher costs extra depending on weight and distance (website tiers: $120 for 200 lb trunk
  and back seats below the windows; $180 for 250 lb trunk, back and passenger seats below the
  windows; $300 for 350 lb). Offer to connect with Sergio.
- **How long does it take?** Before a quote: the driving time plus 0–3 days for loading and
  unloading. After a quote: between ceil(drivingTime) and ceil(drivingTime + 3 days).
- **Upfront deposit discount?** About 4%; a licensed representative confirms the exact number.
- **Payment options?** The quoted price is cash on delivery; credit card may add about 3%.
- **Not drivable?** About $600 extra; a licensed representative confirms.
- **Modified vehicle?** About $300 extra; a licensed representative confirms.
- **Multi-vehicle discount?** About $180 per additional vehicle; Mia quotes each vehicle and a
  licensed representative confirms discounts for shipping them together.

## After the quote

"Your estimated cost is $X. Do you want me to connect you with Sergio? He built this solution and
would be happy to talk about it."

## On a voice call (stage 3)

- Mia speaks the greeting first, as soon as she joins (no LLM wait).
- While the quote is computed she says: "Give me one second while I calculate your quote."
- When the caller is done, Mia calls `end_call`, says a short goodbye and then hangs up (the
  call ends in the browser too).
- The caller can interrupt Mia at any time; a cough or "mm-hm" shorter than half a second
  doesn't stop her, and if a noise does, she resumes after 2 s of silence.
- At 6 minutes Mia stops whatever she's saying: "We've reached the time limit for this call,
  so I'll have to stop here. Thanks for calling F&F, goodbye!" and hangs up.
- If the quote API keeps failing (seen: CarHauler 402 when the allowance ran out), Mia
  apologizes and offers Sergio; she never makes up a price.

## Testing design

**Personas**: 3 attributes, 8 combinations (`NG_C_NV` … `G_P_V`):
- **Generosity**: non-generous (answers only what's asked) vs generous (volunteers more, tries
  to skip steps)
- **Completeness**: complete vs partial (gives about half: "it's a 2022 Honda")
- **Verbosity**: non-verbose vs verbose ("give me a second… Ryan, where are we sending it?
  Oh yeah, Boston")

**Fragments**: instead of whole scripts, design conversation fragments (route, vehicle,
question, change, adversarial) and combine them to generate many conversations. Check the
captured slots against ground truth, typos and turn order.

## Reference conversations

Ground truth for the happy-path scenario tests (stage 2):

| Scenario | Route | Vehicles | Prices | Total |
| --- | --- | --- | --- | --- |
| `happy_path_ngc_1v` | Boston, MA → San Francisco, CA | 2025 Honda Civic | 1,291 | $1,291 |
| `happy_path_ngc_2v` | same | + 2020 Toyota 4Runner | 1,291 + 1,438 | $2,729 |
| `happy_path_ngc_3v` | same | + 2019 Toyota Corolla | 1,291 + 1,438 + 1,280 | $4,009 |

(The notes' 3-vehicle total said $4,019; 1,291 + 1,438 + 1,280 = 4,009. Pricing is computed by
code, never by the model.) Example ZIPs from the notes: Boston 02110, San Francisco 94103.

## CarHauler247 API

Base URL `https://carhauler247.com/api/public/v2`, header `Authorization: Bearer <key>`.
Interactive docs: <https://carhauler247.com/api-docs/v2> (OpenAPI at `/openapi/v2.json`).
Client: `agent/src/mia/carhauler.py`.

| Endpoint | Returns |
| --- | --- |
| `GET /car/makes` | `[{id, name}]` (71 makes) |
| `GET /car/models?makeId=4` | `[{id, name}]` |
| `GET /car/years?modelId=48` | `[2025, 2024, …]` (verified; the notes' `/car/models?modelId=` returns 400) |
| `GET /car/trims?modelId=48&year=2025` | `[{id, name}]`, base trim first |
| `GET /zipcode/search?zipPrefix=31401` | up to 8 `{zip, city, state}` |
| `GET /quote?fromZip&toZip&vehicleType&isOperational&shippingDate&trimId` | `{success, quote: {price, distance, drivingTime, vehicleType, carrier, operational}}` |

Cost: free tier, then $0.0042 per quote and $0.0001 per lookup.

**Quote parameters:** `vehicleType` is one of sedan, suv, pickup, truck, van, minivan,
hatchback, convertible, coupe, wagon (default sedan). `trimId` wins over `vehicleType`.
`isOperational=false` (not drivable) added about $490 on the Boston → SF Civic.
`shippingDate` defaults to 7 days out and can't be in the past.

**Behavior verified on 2026-11-08 (not all in the docs):**

| Case | Response | `ErrorCode` |
| --- | --- | --- |
| Bad or missing key | HTTP 401 | `AUTH` (escalate) |
| Free calls used up | HTTP 402 (docs) | `PAYMENT_REQUIRED` (escalate) |
| Several quotes within seconds | HTTP 200 `success:false` "Too many requests…", clears in ~15 s | `RATE_LIMITED` (retried, then escalate) |
| Invalid origin / destination ZIP | 200 `success:false` "Invalid origin ZIP code…" | `INVALID_ORIGIN_ZIP` / `INVALID_DESTINATION_ZIP` |
| Same origin and destination | 200 `success:false` "…cannot be the same" | `SAME_ZIP` |
| Unknown trim | 200 `success:false` "Invalid trim ID…" | `INVALID_TRIM` |
| Past date | 200 `success:false` "Invalid shipping date…" | `INVALID_DATE` |
| Unknown `vehicleType` | priced as a sedan, no error | rejected locally: `INVALID_VEHICLE_TYPE` |
| Models of Daihatsu, Freightliner, SRT | HTML error page (200) | treated as "no models" |
| Year with no trims | `[]` | `NO_TRIMS` |

Lookups were not rate-limited (71 concurrent model lookups were fine). ZIPs are sent as
5-character strings to keep leading zeros (Boston 02110).

**Live prices change** (the notes' Civic was $1,291; on 2026-11-08 it was $1,194), so tests
never assert live prices.

Website vs API: the website accepts a city or a ZIP (via Google); the API only takes ZIPs, so we
geocode. Not in the API: carrier type, payment options, extra cargo, modified body. Drivable
condition is `isOperational`. Earliest pickup is `shippingDate`.

## Open items

- Ambiguous city names: can geocoding detect ambiguity, so Mia asks for the state only when
  needed?
- What to do with info that doesn't fill a slot.
- Backlog mechanics: several questions at once, order, how Mia signals going back to info.
- No-info vehicle default: ask make first, or vehicle type first.
- Downstream flow after the quote (transfer interest vs voicemail).
