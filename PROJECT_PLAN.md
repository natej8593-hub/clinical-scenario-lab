# Project Plan (Written in Simple Language)

This document explains what we want this project to become, using plain
words instead of technical terms. It is a plan only — nothing has been
built yet.

## What Is This Project?

This project will become a computer program that helps nursing students
practice thinking like a nurse. It uses YOUR OWN study materials (like
PowerPoints, textbook chapters, class notes, or transcripts) to build
realistic practice situations, called "patient scenarios."

Think of it like a flashcard app, but instead of flashcards, it creates a
short story about a patient, and you have to decide what a nurse would do.

## What The Finished Program Will Do

Here is the full goal, explained one step at a time:

1. **Upload your materials**
   You will be able to give the program your nursing PowerPoints, textbook
   chapters, class transcripts, or notes.

2. **Find the important topics**
   The program will read through what you uploaded and figure out which
   diseases, conditions, and nursing topics are being taught.

3. **Build a patient scenario**
   Using only the material you uploaded (not outside information), the
   program will create a made-up patient situation for you to practice on.

4. **Let you play the nurse**
   You will type in what you would check on the patient (like vital signs)
   or what you would do next (like give a medication or call a doctor).

5. **Change the patient based on your choices**
   If you make a good decision, the patient may improve. If you miss
   something important or make a mistake, the patient's condition may get
   worse, just like in real life.

6. **Give you a debrief afterward**
   When the scenario ends, the program will explain:
   - What you did correctly
   - What you missed
   - What could have harmed the patient

7. **Show where each lesson came from**
   For every teaching point in the debrief, the program will point back to
   the exact uploaded document (slide, page, or note) that taught it, so
   you can go back and review it.

## Small Building Steps

Building this all at once would be too big and too confusing. Instead, we
will build it in small, simple stages. Each stage adds one small piece,
and each stage should work on its own before we move to the next one.

1. **Stage 1: Just upload and store a file**
   Get a simple way to upload one document and confirm the program
   received it. No reading or thinking yet — just "did the file arrive."

2. **Stage 2: Read the text out of a file**
   Teach the program to pull the plain text out of an uploaded file
   (for example, pulling text out of a PowerPoint slide).

3. **Stage 3: Find topics in the text**
   Teach the program to look at that text and list out possible disease
   processes or nursing topics it noticed, so you can check its work.

4. **Stage 4: Write one simple, fixed practice scenario**
   Before making the program invent scenarios, hand-write one very simple
   example scenario to make sure the "story format" makes sense and feels
   useful.

5. **Stage 5: Generate a scenario from one uploaded document**
   Combine Stages 2-4: take one uploaded document, pull out a topic, and
   have the program create a short scenario about it.

6. **Stage 6: Let the user type one response**
   Add a simple text box where you type one nursing action or assessment,
   and the program just repeats it back to confirm it was received.

7. **Stage 7: React to that one response**
   Teach the program to change the patient's condition based on whether
   your one response was appropriate or not.

8. **Stage 8: Support a back-and-forth conversation**
   Expand Stage 6 and 7 so you can take multiple actions in a row, with
   the patient's condition updating after each one.

9. **Stage 9: Add the debrief**
   After a scenario ends, generate a summary of what was done right, what
   was missed, and what could have harmed the patient.

10. **Stage 10: Link debrief points back to your source material**
    Add references in the debrief that point back to the specific
    uploaded file (and slide/page, if possible) that taught each point.

11. **Stage 11: Support multiple uploaded documents at once**
    Expand the upload step so more than one document can be combined into
    a single richer scenario.

12. **Stage 12: Polish and refine**
    Improve wording, formatting, and overall experience once all the core
    pieces above are working.

## What This Plan Does NOT Cover Yet

- No actual program code has been written.
- Nothing has been installed.
- We have not yet chosen the specific tools or technology used to build
  this (that will be a separate decision, made before Stage 1 begins).
