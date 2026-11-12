# Noisy calls: first-grid

Run 2026-11-12T23:06:23+00:00. Script: "Hi, I need to ship my car from Miami, Florida to Boston, Massachusetts." / "It's a 2020 Toyota Camry." / "I'm just checking prices for now. I'll call back later, bye!"
How it works: [`agent/evals/noisy_calls.py`](../../../noisy_calls.py). Worker: Docker (Linux;
the filter crashes on Windows). Mia's voice: Cartesia Skylar for the first 13 calls (through
subway 5 dB baseline), Deepgram Thalia for the last 8 (the run was stopped and resumed with
`--resume` to stop spending Cartesia credits). Her voice doesn't change what she hears.

**Read:** with no noise handling, Mia didn't answer a single line within 20 s in a classroom or
cafe, even at 12 dB (a lively room): the room never goes quiet, so the caller's turn never
ends. The filter alone fixes the 12 dB rooms (stray words heard 112 -> 14 in the classroom). At
5 dB (loud) the filter isn't enough; there the 12 s turn limit is what gets her talking (2/3
lines), though slower (7-9 s) and the details aren't always saved. The babble is clean TTS at
the caller's own distance, harder for the filter than real people across a room.

This run had a 12 s turn limit from the start; it is now 25 s, and 12 s once the call is noisy
(real callers talk up to 24 s).

## By profile

| Profile | Noisy calls | Lines answered | Route + car saved | Mia cut off (total) |
| --- | ---: | ---: | ---: | ---: |
| baseline | 6 | 5/18 (28%) | 3/6 | 8 |
| filter | 6 | 12/18 (67%) | 4/6 | 1 |
| full | 6 | 16/18 (89%) | 4/6 | 4 |

## Every call

| Noise | Caller over noise | Profile | Lines answered | Response p50 | Route saved | Car saved | Mia cut off | Long turns ended | Noisy mode | Caller words heard | Other words heard | Ended cleanly |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| quiet | - | baseline | 3/3 | 1.2 s | yes | yes | 0 | 0 | - | 0.97 | 2 | **no** |
| quiet | - | filter | 3/3 | 1.5 s | yes | yes | 0 | 0 | - | 0.86 | 3 | **no** |
| quiet | - | full | 3/3 | 1.4 s | yes | yes | 0 | 0 | - | 0.97 | 2 | yes |
| classroom | 12 dB | baseline | **0/3** | - | yes | yes | 0 | 0 | - | 0.93 | 112 | yes |
| classroom | 12 dB | filter | 3/3 | 3.4 s | yes | yes | 1 | 0 | - | 0.93 | 14 | yes |
| classroom | 12 dB | full | 3/3 | 3.4 s | yes | yes | 1 | 0 | - | 0.86 | 18 | yes |
| classroom | 5 dB | baseline | **0/3** | - | yes | **no** | 0 | 0 | - | 0.69 | 111 | yes |
| classroom | 5 dB | filter | **0/3** | - | yes | yes | 0 | 0 | - | 0.72 | 88 | **no** |
| classroom | 5 dB | full | **2/3** | 6.7 s | **no** | yes | 0 | 6 | yes | 0.69 | 52 | yes |
| subway | 12 dB | baseline | **2/3** | 2.1 s | yes | yes | 3 | 0 | - | 0.97 | 41 | yes |
| subway | 12 dB | filter | 3/3 | 1.6 s | yes | yes | 0 | 0 | - | 0.97 | 6 | yes |
| subway | 12 dB | full | 3/3 | 1.5 s | yes | yes | 0 | 0 | - | 0.97 | 8 | yes |
| subway | 5 dB | baseline | 3/3 | 6.7 s | yes | **no** | 5 | 0 | - | 0.86 | 87 | **no** |
| subway | 5 dB | filter | 3/3 | 3.1 s | yes | yes | 0 | 0 | - | 0.83 | 9 | **no** |
| subway | 5 dB | full | 3/3 | 1.7 s | yes | **no** | 1 | 0 | - | 0.69 | 17 | yes |
| cafe | 12 dB | baseline | **0/3** | - | yes | yes | 0 | 0 | - | 0.97 | 137 | yes |
| cafe | 12 dB | filter | 3/3 | 1.5 s | yes | **no** | 0 | 0 | - | 0.83 | 7 | yes |
| cafe | 12 dB | full | 3/3 | 1.5 s | yes | yes | 0 | 0 | - | 0.93 | 2 | yes |
| cafe | 5 dB | baseline | **0/3** | - | **no** | **no** | 0 | 0 | - | 0.66 | 157 | **no** |
| cafe | 5 dB | filter | **0/3** | - | **no** | yes | 0 | 0 | - | 0.66 | 115 | yes |
| cafe | 5 dB | full | **2/3** | 8.8 s | yes | yes | 2 | 9 | yes | 0.66 | 140 | **no** |

"Caller words heard": share of the script's words Mia's speech-to-text got from the caller.
"Other words heard": words it attributed to the caller that weren't in the script (other
people's speech getting through). Transcripts and events: `calls.json`.
