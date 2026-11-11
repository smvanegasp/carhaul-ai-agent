# Testing guide: calling Mia

Thanks for testing Mia! Mia is a voice assistant that gives car-shipping quotes. You call her
from the browser, act out one of the persona cards below, and then rate the call. Each call
takes about 2 minutes.

## Before you start

- Open the link Sergio sent you in **Chrome or Safari**, on a laptop or a phone.
- Use **headphones** if you can. With speakers, Mia can hear herself and get confused.
- Find a quiet place, then press **Call Mia** and allow the microphone.
- Calls end on their own after 6 minutes. After about 6 calls in an hour the page asks you to
  wait a bit: that's a limit Sergio set on purpose.

## The evaluation workbook

[`docs/evaluation/Mia_evaluation.xlsx`](evaluation/Mia_evaluation.xlsx) has 29 planned test
calls (what to say, what Mia should do) with a row each for your result, rating, feedback and
the **call ID** (copy it with the button next to "Call ID", on the call page after the call or in
Past calls; the whole call is saved under it). The Summary sheet fills in by itself. Send the filled-in
copy back so the feedback can be turned into fixes. Tests in pink ring Sergio's phone: agree a
time with him first (10 transfers a day at most).

## Each call

1. Pick a **persona card** (below) and read it once. You don't need to follow it word for word;
   just play that kind of person.
2. Call Mia and talk to her as that person until she gives you a price or you're done.
3. When the call ends, fill in the form on the page:
   - **How did the call go?** Your overall feeling.
   - **What worked, what didn't?** Anything odd, e.g. "she cut me off when I paused", "she
     got my car wrong", "long silence after I said Boston", "she asked the same thing twice".
   - **Persona card**: the card's number and name, e.g. `3 Chatty & complete`.

The right half of the page shows what Mia is doing under the hood. You don't need to read it,
but if something looks wrong there, mention it in your comment.

**Copy JSON** (top of the conversation, also in Past calls) copies the whole call, with
everything Mia did, to your clipboard. When something went wrong, paste it into your notes or a
message along with what you noticed: it shows exactly what happened, so nothing has to be
retyped.

## Persona cards

Use a different route and car each time. There are ideas at the bottom.

**1 Quiet & complete.** You answer exactly what she asks, nothing more, and you know your car's
details. *"From Miami, Florida." / "To Boston, Massachusetts." / "A 2020 Toyota Camry."*

**2 Quiet & unsure.** You answer only what she asks and give about half the details. *"It's a
Honda." "I think it's from 2019?"* Let her ask for the rest.

**3 Chatty & complete.** You talk around the answer but give everything. *"Oh, so we're moving
my daughter's car, she's starting college in Austin, we're in Denver, it's her 2018 Subaru
Outback..."*

**4 Chatty & unsure.** Lots of words, half the details. *"Give me a second... honey, where are
we sending it? Oh right, Phoenix. It's the blue Ford, the SUV one."*

**5 Rushed & complete.** You say everything at once, right after the greeting. *"Hi, I need a
quote from Chicago to Seattle for a 2021 Tesla Model 3."*

**6 Rushed & unsure.** Everything at once, but with gaps. *"Quote from LA to New York for my
Jeep, please."*

**7 Rushed & chatty & complete.** Everything at once, wrapped in a story, maybe two cars.
*"We're relocating from Atlanta to Portland, Oregon, and need to ship both cars, a 2022 Kia
Telluride and a 2017 Honda Civic, I hope that's not too complicated..."*

**8 Rushed & chatty & unsure.** A story, half the details, maybe a correction. *"So we're
moving to San Diego, or maybe it's Los Angeles now, from Dallas, it's a pickup, a Chevy I think,
fairly new."*

### Extra cards (Mia may not handle these well yet: that's useful to know)

**9 Changes mind.** Partway through, change the destination or the car. *"Actually, make that
Orlando, not Tampa."*

**10 Wants a person.** At some point ask to talk to a real person.

**11 Questions.** Ask one or two questions along the way: *"Do you do enclosed shipping?"*,
*"How long does it take?"*, *"Can I leave some boxes in the trunk?"*, *"What if the car
doesn't start?"*

**12 Interrupter.** Talk over Mia while she's speaking, as if you already know what she'll say.

## Ideas for routes and cars

| From | To | Car |
| --- | --- | --- |
| Miami, FL | Boston, MA | 2020 Toyota Camry |
| Chicago, IL | Seattle, WA | 2021 Tesla Model 3 |
| Denver, CO | Austin, TX | 2018 Subaru Outback |
| Atlanta, GA | Portland, OR | 2022 Kia Telluride |
| Dallas, TX | San Diego, CA | 2019 Chevrolet Silverado |
| New York, NY | Orlando, FL | 2015 Honda Civic |
| Phoenix, AZ | Minneapolis, MN | 2023 Ford Explorer |

## If something breaks

- **"Mia couldn't join the call"** or no voice after 10 seconds: hang up, wait a minute and
  call again. If it happens twice, tell Sergio the time it happened.
- **No sound from Mia:** tap the yellow "Tap to hear Mia" button if you see it, and check the
  volume.
- **The page asks for the microphone again:** allow it; with ngrok links that's normal.
