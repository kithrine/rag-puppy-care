"""
make_vaccination_pdf.py - Authoring tool, NOT a runtime dependency.

Regenerates data/vaccination_schedule.pdf, a one-page puppy vaccination handout.
The content is a condensed summary of data/vaccinations.txt (no new claims), kept
as short self-contained paragraphs so that, when the app reads the PDF back with
pypdf, each paragraph becomes one chunk (the project's "one idea per paragraph"
chunking contract).

The app itself only ever READS this PDF (via pypdf, which is in requirements.txt).
This generator is the only thing that needs reportlab, so reportlab is deliberately
left out of requirements.txt:

    pip install reportlab
    python scripts/make_vaccination_pdf.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate

OUT = Path(__file__).resolve().parent.parent / "data" / "vaccination_schedule.pdf"

TITLE = "Puppy Vaccination Schedule"

# Each entry is one self-contained idea, so it survives extraction as its own
# chunk. Every fact here comes from data/vaccinations.txt.
PARAGRAPHS = [
    "A quick-reference handout. Your veterinarian sets the exact timeline based on "
    "your puppy's age, health, and lifestyle. The single most important dose is the "
    "final one, given at or after 16 weeks, because by then maternal antibody has "
    "usually faded enough for the vaccine to take.",

    "Core vaccines are recommended for essentially every dog. The main combination "
    "shot is labeled DHPP or DAPP and covers distemper, hepatitis (canine "
    "adenovirus), parainfluenza, and parvovirus. Rabies is also a core vaccine and "
    "is required by law. Under the 2022 AAHA guidelines, leptospirosis is now "
    "classified as a core vaccine recommended for all dogs.",

    "6 to 8 weeks of age: puppies get their first round of core vaccines.",

    "Every 2 to 4 weeks after that: boosters continue until the puppy is at least "
    "16 weeks old, usually three or four rounds in total. The final dose at or after "
    "16 weeks matters most.",

    "12 to 16 weeks: the rabies vaccine is given, with the exact timing set by state "
    "and local law. A booster is due one year later, then repeated every one to three "
    "years depending on the product and local law.",

    "Full protection comes about one to two weeks after the final core round, around "
    "16 to 18 weeks of age. Until then, socialize carefully and avoid high-risk "
    "public places like dog parks, pet stores, and busy sidewalks.",

    "Non-core vaccines are recommended for some dogs based on lifestyle and risk, "
    "including Bordetella, canine influenza, and Lyme disease. Many boarding and "
    "daycare facilities require the Bordetella vaccine.",

    "Keep a written or digital record of every vaccine, including the date and which "
    "product was given. You will need proof of rabies vaccination for licensing, "
    "travel, boarding, daycare, and grooming.",
]


def main():
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=TITLE,  # sets the PDF /Title so the loader uses it as the chunk title
    )

    styles = getSampleStyleSheet()
    head = ParagraphStyle(
        "Head", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=20, spaceAfter=10,
    )
    body = ParagraphStyle(
        "Body", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=11, leading=15, spaceAfter=10,
    )

    # pypdf reconstructs text from vertical positions and only puts a single
    # newline between lines, so vertical SPACING alone won't separate paragraphs
    # on extraction. To honor the "blank line between paragraphs" chunking
    # contract, we draw an actual empty line (a non-breaking space) between
    # blocks - that extracts as a blank line, which split_paragraphs treats as a
    # chunk boundary.
    blank = lambda: Paragraph("&nbsp;", body)
    story = [Paragraph(TITLE, head), blank()]
    for i, para in enumerate(PARAGRAPHS):
        story.append(Paragraph(para, body))
        if i != len(PARAGRAPHS) - 1:
            story.append(blank())

    doc.build(story)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
