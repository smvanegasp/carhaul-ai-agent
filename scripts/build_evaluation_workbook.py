"""Build the Mia evaluation workbook for the team (docs/evaluation/Mia_evaluation.xlsx).

    uv run --no-project --with openpyxl python scripts/build_evaluation_workbook.py
        docs/evaluation/Mia_evaluation.xlsx

Then open it in Excel once and save, so the Summary numbers are stored. Rebuilding replaces
the file: never run it over a filled-in copy.
"""

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

OUT = Path(sys.argv[1])

INK = "051C2C"  # the app's deep blue
ACCENT = "2251FF"
FILL_IN = PatternFill("solid", fgColor="FFF2CC")  # light yellow: cells to fill in
HEADER = PatternFill("solid", fgColor=INK)
AREA_FILL = PatternFill("solid", fgColor="EEF2F7")
PHONE_FILL = PatternFill("solid", fgColor="FDE2E1")
THIN = Side(style="thin", color="C9D1DC")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
F = "Arial"


def font(**kw):
    return Font(name=F, size=kw.pop("size", 10), **kw)


WRAP = Alignment(wrap_text=True, vertical="top")

# --- the tests -------------------------------------------------------------------------------
# (area, id, test, persona card, what to say/do, what Mia should do, rings Sergio's phone)
TESTS = [
    ("Happy path", "T01", "Simple quote, one detail at a time", "1 Quiet & complete",
     "Answer only what she asks: \"From Miami, Florida.\" / \"To Boston, Massachusetts.\" / "
     "\"A 2020 Toyota Camry.\" Say yes to the read-back, then no to the representative.",
     "Asks route, then car; reads everything back; gives a price; offers a representative; "
     "on \"no\" says goodbye and hangs up.", "No"),
    ("Happy path", "T02", "Everything in one sentence", "5 Rushed & complete",
     "Right after the greeting: \"Hi, I need a quote from Chicago to Seattle for a 2021 Ford "
     "F-150.\"",
     "Doesn't ask again for anything you said; goes straight to the read-back.", "No"),
    ("Happy path", "T03", "Half the details", "2 Quiet & unsure",
     "\"From LA to New York, it's my Jeep.\" Give the rest only when asked.",
     "Asks only for what's missing (which states, the Jeep's year and model); never makes "
     "you repeat what you already said.", "No"),
    ("Happy path", "T04", "Route and half the car together", "6 Rushed & unsure",
     "\"I need to send my twenty twenty Honda from Miami to Chicago.\"",
     "Saves the route and asks only \"What model is the 2020 Honda?\"", "No"),
    ("Happy path", "T05", "Chatty caller", "3 Chatty & complete",
     "Tell a small story around each answer (moving, a daughter in college...).",
     "Picks the details out of the story; stays friendly and short; no repeated questions.",
     "No"),
    ("Vehicles", "T06", "Two cars in one sentence", "7 Rushed & chatty & complete",
     "\"We're moving from Atlanta to Portland, Oregon with a 2022 Toyota RAV4 and a 2017 Honda "
     "Civic.\"",
     "Saves both cars; reads both back; prices each one and gives the total.", "No"),
    ("Vehicles", "T07", "Correcting the year", "Any",
     "\"It's a twenty ten... no sorry, twenty twenty Toyota Corolla.\"",
     "Uses 2020 (the corrected year) in the read-back.", "No"),
    ("Vehicles", "T08", "Model number said out loud", "Any",
     "\"It's a twenty twenty four Ford F one fifty.\"",
     "Understands F-150 the first time; doesn't ask for the model again.", "No"),
    ("Vehicles", "T09", "Don't know the model", "2 Quiet & unsure",
     "\"It's a Toyota.\" Then: \"It's a 2022, but I don't know the model.\" Then: \"It's an "
     "SUV.\"",
     "Asks year and model first; after \"don't know\" asks sedan, SUV or pickup; says the "
     "price is an estimate.", "No"),
    ("Changes", "T10", "Change the car after the price", "9 Changes mind",
     "After the price: \"Actually it's a 2020 Toyota 4Runner, not the Camry.\"",
     "Changes the car, reads back again, gives a new price after you confirm.", "No"),
    ("Changes", "T11", "Change the destination after the price", "9 Changes mind",
     "After the price: \"Actually, make that Orlando, not Tampa.\"",
     "Changes the route, reads back, gives a new price after you confirm.", "No"),
    ("Changes", "T12", "Remove one of two cars", "9 Changes mind",
     "With two cars on file: \"Can you eliminate the Toyota?\"",
     "Removes it (or asks \"Do you want me to remove the ...?\" and removes it on yes); reads "
     "back the car that's left.", "No"),
    ("Changes", "T13", "Change, then change your mind back", "9 Changes mind",
     "Change the car, then: \"Never mind, keep the original one.\"",
     "Puts the original car back and reads back again.", "No"),
    ("Changes", "T14", "Add a car after the read-back", "Any",
     "When she reads back: \"Yes, and I also have a 2025 Jeep Wrangler going the same way.\"",
     "Adds it and reads both back before quoting.", "No"),
    ("Questions", "T15", "Enclosed shipping", "11 Questions",
     "\"Do you do enclosed shipping?\"",
     "Only open car shipping is quoted; then goes back to what's missing.", "No"),
    ("Questions", "T16", "Things in the trunk", "11 Questions",
     "\"Can I leave some boxes in the trunk?\"",
     "Up to 100 pounds in the trunk, below the windows; more costs extra.", "No"),
    ("Questions", "T17", "Paying by card", "11 Questions",
     "\"Can I pay with a credit card?\"",
     "The price is for cash on delivery; a card may add about 3 percent.", "No"),
    ("Questions", "T18", "How long it takes", "11 Questions",
     "Before the price: \"How long does it take?\" After the price, ask again.",
     "Before: the driving time plus 0 to 3 days. After: the days from the quote. Never a "
     "made-up date.", "No"),
    ("Questions", "T19", "Something she can't know", "11 Questions",
     "\"Do you ship to Hawaii?\" or \"Is my car insured on the way?\"",
     "Doesn't invent an answer; says she's not sure and offers a representative.", "No"),
    ("Off-topic and silence", "T20", "Two off-topic questions", "Any",
     "Ask a joke and the capital of France at different points, then finish normally.",
     "Short reply, back to the quote; the call still ends with a price.", "No"),
    ("Off-topic and silence", "T21", "Three off-topic questions in a row", "Any",
     "Right after the greeting, three unrelated questions in a row.",
     "After the third: says she can only help with car shipping quotes and ends the call "
     "politely. Never transfers.", "No"),
    ("Off-topic and silence", "T22", "Going quiet", "Any",
     "In the middle of the call, stay silent for about 30 seconds.",
     "Asks \"Are you still there?\"; after more silence says goodbye and hangs up.", "No"),
    ("Off-topic and silence", "T23", "Talking over her", "12 Interrupter",
     "Start talking while she's still speaking.",
     "Stops and listens; picks up what you said; doesn't repeat herself.", "No"),
    ("Transfer", "T24", "Ask for a person mid-call", "10 Wants a person",
     "Before the price: \"Can I talk to a real person?\" Sergio answers and presses 1.",
     "\"I'll connect you...\"; ringing; Sergio hears who's calling and \"Press 1\"; after 1 "
     "you're connected and Mia leaves.", "Yes"),
    ("Transfer", "T25", "Nobody answers (voicemail)", "10 Wants a person",
     "Ask for a person; Sergio does NOT answer (it goes to voicemail).",
     "You never hear the voicemail. Mia says she couldn't reach a representative and asks if "
     "there's anything else.", "Yes"),
    ("Transfer", "T26", "Yes to the representative after the price", "Any",
     "Get a price, say yes to the representative; Sergio answers and presses 1.",
     "Sergio hears the car, route and price before you're connected.", "Yes"),
    ("Experience", "T27", "Voices", "Any",
     "Pick a different voice before calling (try at least 2).",
     "Clear and natural; numbers and prices sound right; note which voice you liked.", "No"),
    ("Experience", "T28", "Calling from a phone", "Any",
     "Open the site on your phone's browser and do a simple quote.",
     "Mic works; the page fits the screen; the call is as good as on a computer.", "No"),
    ("Experience", "T29", "Past calls, Stats and Copy JSON", "Any",
     "After a call, open Past calls, find it, press Copy JSON, and look at Stats.",
     "Your call is listed with the right details; Copy JSON copies it; Stats includes it.",
     "No"),
]

COLS = [
    # (header, width, input?)
    ("Area", 16, False),
    ("ID", 6, False),
    ("Test", 26, False),
    ("Persona card", 18, False),
    ("What to say or do", 46, False),
    ("What Mia should do", 46, False),
    ("Rings Sergio's phone?", 11, False),
    ("Tester", 12, True),
    ("Date", 12, True),
    ("Result", 11, True),
    ("Rating (1-5)", 9, True),
    ("What happened (your feedback)", 46, True),
    ("Call ID", 22, True),
]
RESULTS = ["Pass", "Partly", "Fail", "Not run"]

wb = Workbook()

# --- How to use ---------------------------------------------------------------------------
how = wb.active
how.title = "How to use"
how.sheet_view.showGridLines = False
how.column_dimensions["A"].width = 3
how.column_dimensions["B"].width = 110
r = 2
how.cell(r, 2, "Mia evaluation: how to use this workbook").font = font(size=16, bold=True,
                                                                         color=INK)
r += 1
how.cell(r, 2, "Site: https://dj7jlcxkdszj1.cloudfront.net  ·  each test is one call to Mia"
         ).font = font(color="5B6B7F")
r += 2
steps = [
    ("For each test", None),
    ("1. Open the Tests sheet and pick a row. Read \"What to say or do\" and the persona card "
     "(the cards are in docs/TESTING_GUIDE.md). You don't have to follow the words exactly.",
     None),
    ("2. Call Mia from the site and play the test. Note anything odd while it happens.", None),
    ("3. When the call ends, copy its call ID (\"Call ID call-...\" with a Copy button, on the "
     "call page right after the call and in Past calls) and paste it into \"Call ID\". That's "
     "all: the full call (transcript, what Mia did) is saved on the site under that ID.", None),
    ("4. Fill in Tester, Date, Result (pick from the list), Rating 1-5 and \"What happened\": "
     "what was good, what was wrong, what you expected instead.", None),
    ("5. Calls outside the plan go in the Extra calls sheet. Summary updates by itself.", None),
    ("", None),
    ("Cells to fill in", None),
    ("Only the light yellow cells: Tester, Date, Result, Rating, What happened and Call ID. "
     "The other columns describe the test; leave them as they are.", "fill"),
    ("", None),
    ("Good to know", None),
    ("· The call ID is the most important cell: without it the call can't be found.", None),
    ("· Transfer tests (pink in the Tests sheet) ring Sergio's real phone: agree a time with "
     "him first. There are 10 transfers a day at most.", None),
    ("· Result: Pass = Mia did what the test expects. Partly = she got there with a problem "
     "(repeated a question, a long pause). Fail = wrong details, wrong price, or the call broke."
     , None),
    ("· Rating is how the call felt as a caller, 1 (bad) to 5 (great), whatever the result.",
     None),
    ("· When you're done, send the workbook back: the feedback and call IDs are what's used to "
     "improve Mia.", None),
]
for text, kind in steps:
    c = how.cell(r, 2, text)
    if text and kind is None and not text[0].isdigit() and not text.startswith("·"):
        c.font = font(size=12, bold=True, color=INK)
    else:
        c.font = font()
    if kind == "fill":
        c.fill = FILL_IN
    c.alignment = WRAP
    r += 1
r += 1
how.cell(r, 2, "Example of a filled-in row (in the Tests sheet each test has its own row)"
         ).font = font(size=12, bold=True, color=INK)
r += 1
example = [
    ("Tester", "Belinda"),
    ("Date", "2026-11-12"),
    ("Result", "Partly"),
    ("Rating (1-5)", "4"),
    ("What happened (your feedback)",
     "Got the right price, but she asked for the model twice after I said \"F one fifty\". "
     "Otherwise fast and friendly."),
    ("Call ID", "call-803e7edb7473"),
]
for label, value in example:
    c = how.cell(r, 2, f"{label}:  {value}")
    c.font = font(italic=True, color="5B6B7F")
    c.alignment = WRAP
    r += 1


# --- Tests and Extra calls ----------------------------------------------------------------
def table(ws, rows, *, extra=False):
    ws.sheet_view.showGridLines = False
    cols = COLS if not extra else [
        ("#", 5, False), ("What you tried", 46, True), ("Tester", 12, True), ("Date", 12, True),
        ("Result", 11, True), ("Rating (1-5)", 9, True),
        ("What happened (your feedback)", 46, True), ("Call ID", 22, True),
    ]
    for j, (head, width, _is_input) in enumerate(cols, 1):
        c = ws.cell(1, j, head)
        c.font = font(bold=True, color="FFFFFF")
        c.fill = HEADER
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = BOX
        ws.column_dimensions[get_column_letter(j)].width = width
    ws.row_dimensions[1].height = 46
    ws.freeze_panes = "C2" if not extra else "B2"
    result_col = [h for h, _, _ in cols].index("Result") + 1
    rating_col = [h for h, _, _ in cols].index("Rating (1-5)") + 1
    date_col = [h for h, _, _ in cols].index("Date") + 1
    for i, values in enumerate(rows, 2):
        for j, (head, _, is_input) in enumerate(cols, 1):
            v = values[j - 1] if j - 1 < len(values) else None
            c = ws.cell(i, j, v)
            c.font = font(bold=(head in ("ID", "Test")))
            c.alignment = WRAP
            c.border = BOX
            if is_input:
                c.fill = FILL_IN
            elif not extra and values[6] == "Yes":
                c.fill = PHONE_FILL
            elif head in ("Area", "ID"):
                c.fill = AREA_FILL
        ws.row_dimensions[i].height = 62
        ws.cell(i, date_col).number_format = "yyyy-mm-dd"
    last = len(rows) + 1
    dv = DataValidation(type="list", formula1='"' + ",".join(RESULTS) + '"', allow_blank=True,
                        showErrorMessage=True, errorTitle="Result",
                        error="Pick Pass, Partly, Fail or Not run.")
    dv.add(f"{get_column_letter(result_col)}2:{get_column_letter(result_col)}{last}")
    rv = DataValidation(type="whole", operator="between", formula1="1", formula2="5",
                        allow_blank=True, showErrorMessage=True, errorTitle="Rating",
                        error="A whole number from 1 (bad) to 5 (great).")
    rv.add(f"{get_column_letter(rating_col)}2:{get_column_letter(rating_col)}{last}")
    ws.add_data_validation(dv)
    ws.add_data_validation(rv)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{last}"
    return cols


tests = wb.create_sheet("Tests")
table(tests, [list(t) for t in TESTS])
tests.cell(1, 13).comment = Comment(
    "Copy it with the Copy button next to \"Call ID\" (Past calls, or the call page right "
    "after the call). The full call is saved on the site, so the ID is all that's needed.",
    "Mia evaluation")
N = len(TESTS) + 1  # last test row

extra = wb.create_sheet("Extra calls")
table(extra, [[n] for n in range(1, 31)], extra=True)

# --- Summary (formulas over Tests) --------------------------------------------------------
summ = wb.create_sheet("Summary", 1)
summ.sheet_view.showGridLines = False
for col, width in zip("ABCDEFGH", (24, 10, 10, 10, 10, 11, 12, 13), strict=True):
    summ.column_dimensions[col].width = width
summ["A1"] = "Summary (fills in from the Tests sheet)"
summ["A1"].font = font(size=14, bold=True, color=INK)
heads = ["Area", "Tests", "Pass", "Partly", "Fail", "Not run", "Pass rate", "Avg rating"]
for j, h in enumerate(heads, 1):
    c = summ.cell(3, j, h)
    c.font = font(bold=True, color="FFFFFF")
    c.fill = HEADER
    c.border = BOX
    c.alignment = Alignment(horizontal="center", wrap_text=True)
areas = list(dict.fromkeys(t[0] for t in TESTS))
A, J, K = f"Tests!$A$2:$A${N}", f"Tests!$J$2:$J${N}", f"Tests!$K$2:$K${N}"
row = 4
for area in [*areas, "All tests"]:
    total = area == "All tests"
    summ.cell(row, 1, area).font = font(bold=total)
    crit = "" if total else f',{A},$A{row}'
    summ.cell(row, 2, f"=COUNTA(Tests!$B$2:$B${N})" if total else f"=COUNTIF({A},$A{row})")
    for j, res in zip((3, 4, 5), ("Pass", "Partly", "Fail"), strict=True):
        summ.cell(row, j, f'=COUNTIFS({J},"{res}"{crit})')
    # Not run: no result yet, or "Not run"
    summ.cell(row, 6, f"=B{row}-C{row}-D{row}-E{row}")
    summ.cell(row, 7, f"=IFERROR(C{row}/(C{row}+D{row}+E{row}),\"-\")")
    summ.cell(row, 8, (f"=IFERROR(AVERAGE({K}),\"-\")" if total
                       else f"=IFERROR(AVERAGEIFS({K},{A},$A{row}),\"-\")"))
    for j in range(1, 9):
        c = summ.cell(row, j)
        c.border = BOX
        if j > 1:
            c.alignment = Alignment(horizontal="center")
            c.font = font(bold=total)
        if total:
            c.fill = AREA_FILL
    summ.cell(row, 7).number_format = "0%"
    summ.cell(row, 8).number_format = "0.0"
    row += 1
row += 1
summ.cell(row, 1, "Extra calls logged").font = font(bold=True)
summ.cell(row, 2, "=COUNTA('Extra calls'!$B$2:$B$31)")
summ.cell(row + 1, 1, "Calls with a Call ID").font = font(bold=True)
summ.cell(row + 1, 2,
          f"=COUNTA(Tests!$M$2:$M${N})+COUNTA('Extra calls'!$H$2:$H$31)")
summ.cell(row + 3, 1, "Pass rate counts only tests with a result (Pass, Partly or Fail). "
          "\"Not run\" includes tests with no result yet.").font = font(italic=True,
                                                                     color="5B6B7F")

for ws in wb.worksheets:
    ws.sheet_properties.tabColor = {"How to use": ACCENT, "Summary": INK}.get(ws.title)
OUT.parent.mkdir(parents=True, exist_ok=True)
wb.save(OUT)
print("saved", OUT, "tests:", len(TESTS))
