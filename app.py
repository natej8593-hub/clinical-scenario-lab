import hashlib
import json
import re

import anthropic
import fitz
import streamlit as st

AI_SOURCE_MAP_CHARACTER_LIMIT = 300_000
CHUNK_TARGET_SIZE = 12_000
CHUNK_MAX_TOKENS = 8000

CHUNK_SOURCE_MAP_INSTRUCTIONS = """You are organizing one section of nursing study material for an educational simulation program.

Use only the supplied source section.

Do not add medical facts that are absent from the source.

Do not invent medication doses, laboratory ranges, page numbers, professor statements, nursing actions, or patient teaching.

Page markers such as [Page 1], [Page 2], and [Page 3] came from the uploaded PDF.

Never invent a page reference.

Only cite a page when the supporting information appears after that page marker in this source section.

For TXT files, do not invent page numbers.

Prioritize:

- Disease processes
- Pathophysiology
- Important assessment findings
- Emergency findings
- Nursing assessments
- Nursing priorities and interventions
- Medications and treatments
- Laboratory or diagnostic monitoring
- Patient teaching
- Safety precautions
- Delegation or escalation
- Professor emphasis
- Information the source says not to focus on

Place unclear, conflicting, or unsupported information under uncertainties.

Keep the response concise but complete:

- Combine duplicate or nearly identical findings instead of listing them more than once.
- Use concise phrases rather than long paragraphs.
- Disease-process explanations should normally be no more than 100 words per topic.
- Each list item should normally be one short sentence.
- Do not repeat the same fact under several fields unless it serves a different nursing purpose.
- Include only information supported by this source section.
- Preserve important nursing details, emergency findings, medications, diagnostics, teaching, professor emphasis, and page references — do not omit unique clinically important information merely to shorten the response.

Return valid JSON only, with no markdown fences and no introductory text.

Use exactly this structure:

{
  "source_file": "filename",
  "chunk_number": 1,
  "source_range": "pages or text section",
  "main_topics": [
    {
      "topic": "topic name",
      "disease_process": "brief explanation supported by the source",
      "important_findings": ["finding"],
      "nursing_assessments": ["assessment"],
      "nursing_actions": ["action"],
      "emergency_findings": ["finding"],
      "patient_teaching": ["teaching point"],
      "medications_or_treatments": ["item"],
      "diagnostics_or_labs": ["item"],
      "delegation_or_escalation": ["item"],
      "source_evidence": ["short supporting statement with source page when available"]
    }
  ],
  "professor_emphasis": [],
  "excluded_or_not_emphasized": [],
  "uncertainties": []
}

Keep the output concise and grounded in the supplied section."""

def _string_array_schema():
    return {"type": "array", "items": {"type": "string"}}


def _main_topic_schema():
    string_fields = [
        "topic",
        "disease_process",
    ]
    array_fields = [
        "important_findings",
        "nursing_assessments",
        "nursing_actions",
        "emergency_findings",
        "patient_teaching",
        "medications_or_treatments",
        "diagnostics_or_labs",
        "delegation_or_escalation",
        "source_evidence",
    ]
    properties = {field: {"type": "string"} for field in string_fields}
    properties.update({field: _string_array_schema() for field in array_fields})
    return {
        "type": "object",
        "properties": properties,
        "required": string_fields + array_fields,
        "additionalProperties": False,
    }


# Structured-output schema for a single chunk analysis response. Every
# property is required and every object forbids additional properties so
# the API can guarantee a parseable, complete result (see output_config
# in call_claude).
CHUNK_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "source_file": {"type": "string"},
        "chunk_number": {"type": "integer"},
        "source_range": {"type": "string"},
        "main_topics": {"type": "array", "items": _main_topic_schema()},
        "professor_emphasis": _string_array_schema(),
        "excluded_or_not_emphasized": _string_array_schema(),
        "uncertainties": _string_array_schema(),
    },
    "required": [
        "source_file",
        "chunk_number",
        "source_range",
        "main_topics",
        "professor_emphasis",
        "excluded_or_not_emphasized",
        "uncertainties",
    ],
    "additionalProperties": False,
}

# Structured-output schema for the combined master source map.
MASTER_SOURCE_MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "source_files": _string_array_schema(),
        "main_topics": {"type": "array", "items": _main_topic_schema()},
        "professor_emphasis": _string_array_schema(),
        "excluded_or_not_emphasized": _string_array_schema(),
        "uncertainties": _string_array_schema(),
    },
    "required": [
        "source_files",
        "main_topics",
        "professor_emphasis",
        "excluded_or_not_emphasized",
        "uncertainties",
    ],
    "additionalProperties": False,
}

CHUNK_REQUIRED_KEYS = tuple(CHUNK_RESULT_SCHEMA["required"])
MASTER_REQUIRED_KEYS = tuple(MASTER_SOURCE_MAP_SCHEMA["required"])


TOPIC_KEYWORDS = {
    "Hypertension": [
        "hypertension",
        "high blood pressure",
        "antihypertensive",
        "blood pressure",
    ],
    "Hypertensive Emergency": [
        "hypertensive emergency",
        "hypertensive crisis",
        "target-organ damage",
        "target organ damage",
        "blood pressure above 180/120",
        "180/120",
    ],
    "Stroke": [
        "stroke",
        "cerebrovascular accident",
        "CVA",
        "TIA",
        "facial droop",
        "unilateral weakness",
        "slurred speech",
        "last known well",
    ],
    "Peripheral Arterial Disease": [
        "peripheral arterial disease",
        "PAD",
        "arterial insufficiency",
        "intermittent claudication",
        "rest pain",
        "dependent rubor",
        "six Ps",
        "6 Ps",
    ],
    "Deep Vein Thrombosis": [
        "deep vein thrombosis",
        "DVT",
        "venous thrombosis",
        "Virchow",
        "unilateral edema",
        "calf tenderness",
    ],
    "Anticoagulation": [
        "heparin",
        "enoxaparin",
        "Lovenox",
        "warfarin",
        "Coumadin",
        "anticoagulant",
        "INR",
        "aPTT",
        "anti-Xa",
        "protamine",
    ],
    "Atherosclerosis and Coronary Artery Disease": [
        "atherosclerosis",
        "arteriosclerosis",
        "coronary artery disease",
        "CAD",
        "plaque",
        "atheroma",
        "HDL",
        "LDL",
        "cholesterol",
    ],
}

# These short abbreviations are also ordinary words or letter sequences
# (e.g. "pad", "cadence"), so they only count as a match when they appear
# in the original text as an uppercase, standalone token.
UPPERCASE_TOKEN_KEYWORDS = {"PAD", "CAD", "DVT", "TIA", "CVA", "INR", "HDL", "LDL"}


def normalize_response_text(text):
    """Lowercase, strip hyphens/punctuation, and collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def has_phrase(padded_text, phrase):
    return f" {phrase} " in padded_text


def has_any_phrase(padded_text, phrases):
    return any(has_phrase(padded_text, phrase) for phrase in phrases)


def detect_study_topics(text):
    """Scan text for whole-word keyword matches and group results by topic.

    Full medical words and phrases match case-insensitively. Short
    abbreviations that double as ordinary words (see
    UPPERCASE_TOKEN_KEYWORDS) only match when they appear as an
    uppercase, standalone token in the original text.
    """
    results = []

    for topic_name, keywords in TOPIC_KEYWORDS.items():
        matched_keywords = []
        total_matches = 0
        matched_spans = []

        for keyword in keywords:
            case_sensitive = keyword in UPPERCASE_TOKEN_KEYWORDS
            pattern = r"\b" + re.escape(keyword) + r"\b"
            flags = 0 if case_sensitive else re.IGNORECASE

            keyword_match_count = 0
            for match in re.finditer(pattern, text, flags=flags):
                start, end = match.span()
                overlaps_existing = any(
                    start < existing_end and end > existing_start
                    for existing_start, existing_end in matched_spans
                )
                if overlaps_existing:
                    continue
                matched_spans.append((start, end))
                keyword_match_count += 1

            if keyword_match_count > 0:
                total_matches += keyword_match_count
                matched_keywords.append(keyword)

        if total_matches > 0:
            results.append((topic_name, total_matches, matched_keywords))

    results.sort(key=lambda result: result[1], reverse=True)
    return results


def compute_stage1_categories(padded_response):
    """Return the four initial Hypertensive Emergency priority categories."""

    # Category 1: verify the blood pressure needs a BP term AND a
    # recheck-style action word, in any order and with any words
    # between them (e.g. "repeat the blood pressure manually").
    bp_term_present = has_any_phrase(padded_response, ["blood pressure", "bp"])
    bp_action_words = ["repeat", "recheck", "retake", "verify", "confirm"]
    bp_action_present = has_any_phrase(padded_response, bp_action_words)
    check_again_present = has_phrase(padded_response, "check") and has_phrase(
        padded_response, "again"
    )
    take_again_present = has_phrase(padded_response, "take") and has_phrase(
        padded_response, "again"
    )
    bp_recognized = bp_term_present and (
        bp_action_present or check_again_present or take_again_present
    )

    # Category 2: focused neurological assessment.
    neuro_phrases = [
        "neurological assessment",
        "neurologic assessment",
        "neuro assessment",
        "neurological check",
        "neurologic check",
        "neurological checks",
        "neurologic checks",
        "neurological status",
        "neurologic status",
        "level of consciousness",
        "mental status",
        "check pupils",
        "assess pupils",
        "pupils",
        "assess for stroke",
        "stroke symptoms",
    ]
    neuro_recognized = has_any_phrase(padded_response, neuro_phrases)

    # Category 3: continuous monitoring.
    monitor_phrases = [
        "continuous monitoring",
        "cardiac monitoring",
        "telemetry",
        "monitor vital signs",
        "frequent vital signs",
        "place on monitor",
        "on the monitor",
        "cycle blood pressure",
        "cycle blood pressures",
    ]
    monitor_recognized = has_any_phrase(padded_response, monitor_phrases)

    # Category 4: escalate care, either via "notify/call ... provider"
    # (any words allowed between them) or any rapid response mention.
    communication_words = ["notify", "call", "contact", "page", "inform"]
    recipient_words = ["provider", "physician", "doctor"]
    communication_present = has_any_phrase(padded_response, communication_words)
    recipient_present = has_any_phrase(padded_response, recipient_words)
    escalate_via_provider = communication_present and recipient_present
    escalate_via_rapid_response = has_any_phrase(
        padded_response, ["rapid response", "rrt"]
    )
    escalate_recognized = escalate_via_provider or escalate_via_rapid_response

    return [
        ("Verify the blood pressure", bp_recognized),
        ("Perform a focused neurological assessment", neuro_recognized),
        ("Begin continuous monitoring", monitor_recognized),
        ("Escalate care", escalate_recognized),
    ]


def compute_stage2_categories(padded_second_response):
    """Return the six second-stage Hypertensive Emergency priority categories."""

    # Category 1: activate the stroke response / escalate care,
    # either via a direct phrase or a communication word paired
    # with a provider/team word anywhere in the response.
    stroke_phrases = [
        "stroke alert",
        "stroke code",
        "code stroke",
        "activate stroke team",
        "notify stroke team",
        "rapid response",
        "rrt",
        "call rapid response",
        "activate rrt",
        "notify provider",
        "call provider",
        "notify physician",
        "call physician",
        "escalate care",
    ]
    stroke_direct = has_any_phrase(padded_second_response, stroke_phrases)
    escalate_communication_words = [
        "notify",
        "call",
        "contact",
        "page",
        "inform",
        "activate",
    ]
    escalate_target_words = [
        "provider",
        "physician",
        "doctor",
        "stroke team",
        "rapid response",
        "rrt",
    ]
    escalate_communication_present = has_any_phrase(
        padded_second_response, escalate_communication_words
    )
    escalate_target_present = has_any_phrase(
        padded_second_response, escalate_target_words
    )
    stroke_recognized = stroke_direct or (
        escalate_communication_present and escalate_target_present
    )

    # Category 2: immediate focused neurological assessment.
    neuro_stage2_phrases = [
        "focused neurological assessment",
        "focused neurologic assessment",
        "focused neuro assessment",
        "neurological assessment",
        "neurologic assessment",
        "neuro assessment",
        "neurological checks",
        "neurologic checks",
        "neuro checks",
        "nihss",
        "stroke scale",
        "assess pupils",
        "assess mental status",
        "assess level of consciousness",
        "check level of consciousness",
        "assess strength",
        "assess speech",
        "assess facial droop",
        "assess for stroke symptoms",
    ]
    neuro_stage2_recognized = has_any_phrase(padded_second_response, neuro_stage2_phrases)

    # Category 3: confirm and document the last-known-well time.
    last_known_well_phrases = [
        "last known well",
        "last known normal",
        "time last known well",
        "document last known well",
        "note last known well",
        "determine symptom onset",
        "time symptoms began",
        "establish onset time",
        "document onset time",
    ]
    last_known_well_recognized = has_any_phrase(
        padded_second_response, last_known_well_phrases
    )

    # Category 4: check bedside blood glucose, either via a direct
    # phrase or a glucose-related word paired with an action word.
    glucose_phrases = [
        "blood glucose",
        "bedside glucose",
        "glucose level",
        "fingerstick glucose",
        "finger stick glucose",
        "point of care glucose",
        "poc glucose",
        "check glucose",
        "check blood sugar",
        "bedside blood sugar",
        "bg",
    ]
    glucose_direct = has_any_phrase(padded_second_response, glucose_phrases)
    glucose_words = ["glucose", "blood sugar", "bg"]
    glucose_action_words = ["check", "obtain", "measure", "assess", "perform"]
    glucose_word_present = has_any_phrase(padded_second_response, glucose_words)
    glucose_action_present = has_any_phrase(padded_second_response, glucose_action_words)
    glucose_recognized = glucose_direct or (
        glucose_word_present and glucose_action_present
    )

    # Category 5: prepare for urgent brain imaging.
    imaging_phrases = [
        "head ct",
        "ct head",
        "ct scan",
        "noncontrast ct",
        "non contrast ct",
        "brain ct",
        "urgent ct",
        "stat ct",
        "prepare for ct",
        "transport to ct",
        "prepare for brain imaging",
        "urgent brain imaging",
        "stroke imaging",
    ]
    imaging_recognized = has_any_phrase(padded_second_response, imaging_phrases)

    # Category 6: protect airway and swallowing safety.
    airway_phrases = [
        "maintain airway",
        "assess airway",
        "monitor airway",
        "protect airway",
        "suction available",
        "aspiration precautions",
        "keep npo",
        "npo",
        "nothing by mouth",
        "no food or fluids",
        "swallow screen",
        "swallowing screen",
        "dysphagia screen",
        "assess swallowing",
        "safety precautions",
        "elevate head of bed",
        "position safely",
    ]
    airway_recognized = has_any_phrase(padded_second_response, airway_phrases)

    return [
        ("Activate the stroke response and escalate care", stroke_recognized),
        ("Perform an immediate focused neurological assessment", neuro_stage2_recognized),
        ("Confirm and document the last-known-well time", last_known_well_recognized),
        ("Check bedside blood glucose", glucose_recognized),
        ("Prepare for urgent brain imaging", imaging_recognized),
        ("Protect airway and swallowing safety", airway_recognized),
    ]


def extract_response_text(response):
    """Return the first text block's text from a Claude response, or None.

    Structured-output responses are expected to hold their JSON directly in
    a text content block. This does not rely on markdown-fence stripping.
    """
    if not response.content:
        return None
    for block in response.content:
        if block.type == "text":
            return block.text
    return None


def parse_structured_json(response_text, required_keys):
    """Parse structured-output JSON and confirm the expected keys exist.

    Raises json.JSONDecodeError or ValueError if the response cannot be
    treated as a complete result for the given schema.
    """
    parsed = json.loads(response_text)
    if not isinstance(parsed, dict) or any(key not in parsed for key in required_keys):
        raise ValueError("Structured response is missing expected top-level keys.")
    return parsed


def split_long_text(text, target_size):
    """Split text into pieces near target_size without dropping characters.

    Prefers a paragraph break, then a sentence break, and only falls back
    to a hard cut when no good break point is found in the second half of
    the target window.
    """
    if len(text) <= target_size:
        return [text]

    pieces = []
    remaining = text
    while len(remaining) > target_size:
        window = remaining[:target_size]
        split_at = window.rfind("\n\n")
        if split_at <= target_size // 2:
            sentence_split = max(window.rfind(". "), window.rfind(".\n"))
            split_at = sentence_split + 1 if sentence_split > target_size // 2 else -1
        else:
            split_at += 2
        if split_at <= 0:
            split_at = target_size
        pieces.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        pieces.append(remaining)
    return pieces


def chunk_pdf_document(text, target_size):
    """Divide extracted PDF text into chunks, splitting at page boundaries."""
    page_pattern = re.compile(r"\[Page (\d+)\]\n")
    matches = list(page_pattern.finditer(text))

    pages = []
    for match_index, match in enumerate(matches):
        page_number = int(match.group(1))
        start = match.start()
        end = (
            matches[match_index + 1].start()
            if match_index + 1 < len(matches)
            else len(text)
        )
        pages.append((page_number, text[start:end]))

    chunks = []
    current_pages = []
    current_length = 0

    def flush():
        if not current_pages:
            return
        page_numbers = [page_number for page_number, _ in current_pages]
        if len(page_numbers) == 1:
            range_label = f"Page {page_numbers[0]}"
        else:
            range_label = f"Pages {page_numbers[0]}-{page_numbers[-1]}"
        chunks.append(
            {
                "range": range_label,
                "text": "".join(page_text for _, page_text in current_pages),
            }
        )

    for page_number, page_text in pages:
        if len(page_text) > target_size:
            flush()
            current_pages = []
            current_length = 0
            pieces = split_long_text(page_text, target_size)
            for piece_index, piece in enumerate(pieces, start=1):
                chunks.append(
                    {
                        "range": f"Page {page_number} (part {piece_index} of {len(pieces)})",
                        "text": piece,
                    }
                )
            continue

        if current_length + len(page_text) > target_size and current_pages:
            flush()
            current_pages = []
            current_length = 0

        current_pages.append((page_number, page_text))
        current_length += len(page_text)

    flush()
    return chunks


def chunk_txt_document(text, target_size):
    """Divide plain text into chunks, splitting primarily at paragraph breaks."""
    paragraphs = [
        paragraph for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()
    ]

    chunks = []
    current_parts = []
    current_length = 0
    section_number = 0

    def flush():
        nonlocal section_number
        if not current_parts:
            return
        section_number += 1
        chunks.append(
            {
                "range": f"Text section {section_number}",
                "text": "\n\n".join(current_parts),
            }
        )

    for paragraph in paragraphs:
        if len(paragraph) > target_size:
            flush()
            current_parts.clear()
            current_length = 0
            for piece in split_long_text(paragraph, target_size):
                section_number += 1
                chunks.append(
                    {"range": f"Text section {section_number}", "text": piece}
                )
            continue

        if current_length + len(paragraph) > target_size and current_parts:
            flush()
            current_parts.clear()
            current_length = 0

        current_parts.append(paragraph)
        current_length += len(paragraph)

    flush()
    return chunks


def chunk_study_text(text, file_extension, target_size=CHUNK_TARGET_SIZE):
    if file_extension == "pdf":
        return chunk_pdf_document(text, target_size)
    return chunk_txt_document(text, target_size)


def build_chunk_prompt(filename, chunk_number, source_range, chunk_text):
    return (
        f"{CHUNK_SOURCE_MAP_INSTRUCTIONS}\n\n"
        f"Uploaded filename: {filename}\n"
        f"Chunk number: {chunk_number}\n"
        f"Source range: {source_range}\n\n"
        f"Source section text:\n{chunk_text}"
    )


MASTER_LIST_FIELDS = (
    "important_findings",
    "nursing_assessments",
    "nursing_actions",
    "emergency_findings",
    "patient_teaching",
    "medications_or_treatments",
    "diagnostics_or_labs",
    "delegation_or_escalation",
    "source_evidence",
)

# A small set of medical abbreviation/full-name pairs that should always
# group into a single topic. Keys and values are already normalized
# (lowercase, punctuation-stripped) forms.
TOPIC_SYNONYMS = {
    "pad": "peripheral arterial disease",
    "peripheral arterial disease": "peripheral arterial disease",
    "dvt": "deep vein thrombosis",
    "deep vein thrombosis": "deep vein thrombosis",
    "cad": "coronary artery disease",
    "coronary artery disease": "coronary artery disease",
}


def normalize_topic_key(topic_name):
    """Normalize a topic name into a stable grouping key for local merging."""
    key = (topic_name or "").lower()
    key = re.sub(r"[^\w\s]", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    return TOPIC_SYNONYMS.get(key, key)


def dedupe_preserve_order(items):
    """Remove exact and capitalization-only duplicates, keeping first-seen order."""
    seen = set()
    deduped = []
    for item in items:
        marker = item.strip().lower()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def merge_chunk_source_maps(chunk_results, source_filename):
    """Deterministically combine completed chunk source maps in Python.

    This replaces the removed final Claude "combining" request: every
    completed chunk map is already source-grounded structured JSON, so no
    additional model call is needed to merge them.
    """
    source_files = []
    for chunk_result in chunk_results:
        chunk_filename = chunk_result.get("source_file") or source_filename
        if chunk_filename not in source_files:
            source_files.append(chunk_filename)
    if not source_files:
        source_files = [source_filename]

    topic_order = []
    topics_by_key = {}

    for chunk_result in chunk_results:
        for topic in chunk_result.get("main_topics", []) or []:
            key = normalize_topic_key(topic.get("topic", ""))
            if key not in topics_by_key:
                topics_by_key[key] = {
                    "topic": topic.get("topic", ""),
                    "disease_process": [],
                    **{field: [] for field in MASTER_LIST_FIELDS},
                }
                topic_order.append(key)
            merged_topic = topics_by_key[key]

            disease_process = (topic.get("disease_process") or "").strip()
            if disease_process:
                merged_topic["disease_process"].append(disease_process)

            for field in MASTER_LIST_FIELDS:
                merged_topic[field].extend(topic.get(field) or [])

    main_topics = []
    for key in topic_order:
        merged_topic = topics_by_key[key]
        combined_topic = {
            "topic": merged_topic["topic"],
            "disease_process": " ".join(
                dedupe_preserve_order(merged_topic["disease_process"])
            ),
        }
        for field in MASTER_LIST_FIELDS:
            combined_topic[field] = dedupe_preserve_order(merged_topic[field])
        main_topics.append(combined_topic)

    def merge_global_field(field_name):
        items = [
            item
            for chunk_result in chunk_results
            for item in (chunk_result.get(field_name) or [])
        ]
        return dedupe_preserve_order(items)

    return {
        "source_files": source_files,
        "main_topics": main_topics,
        "professor_emphasis": merge_global_field("professor_emphasis"),
        "excluded_or_not_emphasized": merge_global_field("excluded_or_not_emphasized"),
        "uncertainties": merge_global_field("uncertainties"),
    }


def build_completed_sections_payload(chunk_results, num_chunks, source_filename):
    """Build the downloadable JSON payload for completed (paid) chunk results.

    Lets a user preserve completed sections before a refresh or restart
    without contacting Claude.
    """
    completed_chunk_numbers = [
        index + 1 for index, result in enumerate(chunk_results) if result is not None
    ]
    return {
        "source_filename": source_filename,
        "total_planned_chunks": num_chunks,
        "completed_chunk_numbers": completed_chunk_numbers,
        "completed_chunk_results": [
            result for result in chunk_results if result is not None
        ],
    }


def call_claude(prompt, max_tokens, schema):
    # Structured extraction doesn't need adaptive thinking, and thinking
    # tokens count against max_tokens — disabling it keeps the full budget
    # available for the JSON response itself.
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    return client.messages.create(
        model="claude-sonnet-5",
        max_tokens=max_tokens,
        thinking={"type": "disabled"},
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )


def run_chunk_analysis(chunk_plan, filename, start_index):
    num_chunks = len(chunk_plan)
    chunk_results = st.session_state.ai_chunk_results

    progress_bar = st.progress(start_index / num_chunks if num_chunks else 0)
    status_placeholder = st.empty()

    for index in range(start_index, num_chunks):
        status_placeholder.write(f"Analyzing section {index + 1} of {num_chunks}...")
        chunk = chunk_plan[index]
        prompt = build_chunk_prompt(filename, index + 1, chunk["range"], chunk["text"])

        try:
            response = call_claude(prompt, CHUNK_MAX_TOKENS, CHUNK_RESULT_SCHEMA)
        except anthropic.AuthenticationError:
            st.session_state.ai_source_map_error = "invalid_key"
            st.session_state.ai_error_phase = "chunk"
            return
        except anthropic.PermissionDeniedError:
            st.session_state.ai_source_map_error = "billing"
            st.session_state.ai_error_phase = "chunk"
            return
        except anthropic.RateLimitError:
            st.session_state.ai_source_map_error = "rate_limited"
            st.session_state.ai_error_phase = "chunk"
            return
        except Exception:
            st.session_state.ai_source_map_error = "chunk_other"
            st.session_state.ai_error_phase = "chunk"
            return

        if response.stop_reason == "max_tokens":
            st.session_state.ai_source_map_error = "chunk_max_tokens"
            st.session_state.ai_error_phase = "chunk"
            return
        if response.stop_reason == "refusal":
            st.session_state.ai_source_map_error = "chunk_refusal"
            st.session_state.ai_error_phase = "chunk"
            return
        if response.stop_reason != "end_turn":
            st.session_state.ai_source_map_error = "chunk_other"
            st.session_state.ai_error_phase = "chunk"
            return

        response_text = extract_response_text(response)
        if response_text is None:
            st.session_state.ai_source_map_error = "chunk_unreadable"
            st.session_state.ai_error_phase = "chunk"
            return

        try:
            chunk_results[index] = parse_structured_json(response_text, CHUNK_REQUIRED_KEYS)
        except (json.JSONDecodeError, ValueError):
            st.session_state.ai_source_map_error = "chunk_unreadable"
            st.session_state.ai_error_phase = "chunk"
            return

        progress_bar.progress((index + 1) / num_chunks)

    st.session_state.ai_source_map_error = None
    st.session_state.ai_error_phase = None

    status_placeholder.write("Combining the section results locally...")
    st.session_state.ai_source_map = merge_chunk_source_maps(chunk_results, filename)


AI_SOURCE_MAP_ERROR_MESSAGES = {
    "invalid_key": "The API key was rejected. Check Streamlit Secrets.",
    "billing": (
        "The Claude API account may not have enough usage credits. Check "
        "Anthropic Billing."
    ),
    "rate_limited": (
        "The Claude API is temporarily rate limited. Please wait and "
        "resume the analysis."
    ),
    "chunk_max_tokens": (
        "Claude reached the output limit while analyzing this section. "
        "No automatic retry was made. Completed sections were preserved."
    ),
    "chunk_refusal": (
        "Claude could not analyze this section. The completed sections "
        "were preserved."
    ),
    "chunk_unreadable": (
        "Claude returned an incomplete or unreadable section result. No "
        "additional request was made. Completed sections were preserved."
    ),
    "chunk_other": (
        "The AI analysis could not continue. Completed sections were "
        "preserved when possible."
    ),
}

# Legacy error codes from a previous architecture that made a paid Claude
# request to combine completed chunk results. Combining is now done
# locally in Python and can no longer fail this way, but a session left
# running across the deploy of this change could still hold one of these
# values in st.session_state; kept only so old state can be recognized
# and cleared automatically (see the backward-compatible cleanup below).
LEGACY_COMBINE_ERROR_CODES = frozenset(
    {"combine_max_tokens", "combine_refusal", "combine_unreadable", "combine_other"}
)


st.title("Clinical Scenario Lab")

st.warning("Educational simulation only. Do not use during actual patient care.")

st.header("AI Connection")

st.write(
    "Claude AI is not contacted automatically. API credits are used only "
    "when an AI button is deliberately clicked."
)

if st.button("Test AI Connection"):
    if "ANTHROPIC_API_KEY" not in st.secrets:
        st.session_state.ai_connection_status = "missing_key"
    else:
        try:
            with st.spinner("Testing the Claude connection..."):
                client = anthropic.Anthropic(
                    api_key=st.secrets["ANTHROPIC_API_KEY"]
                )
                client.messages.create(
                    model="claude-sonnet-5",
                    max_tokens=30,
                    messages=[
                        {
                            "role": "user",
                            "content": "Reply with exactly: AI connection successful.",
                        }
                    ],
                )
            st.session_state.ai_connection_status = "success"
        except anthropic.AuthenticationError:
            st.session_state.ai_connection_status = "invalid_key"
        except anthropic.PermissionDeniedError:
            st.session_state.ai_connection_status = "billing"
        except anthropic.RateLimitError:
            st.session_state.ai_connection_status = "rate_limited"
        except anthropic.APIError:
            st.session_state.ai_connection_status = "connection_error"
        except Exception:
            st.session_state.ai_connection_status = "connection_error"

ai_connection_status = st.session_state.get("ai_connection_status")

if ai_connection_status == "missing_key":
    st.error("The Anthropic API key was not found in Streamlit Secrets.")
elif ai_connection_status == "invalid_key":
    st.error("The API key was rejected. Check the key stored in Streamlit Secrets.")
elif ai_connection_status == "billing":
    st.error(
        "The Claude API account may not have enough usage credits. Check "
        "Billing in the Anthropic Console."
    )
elif ai_connection_status == "rate_limited":
    st.error("The Claude API is temporarily rate limited. Please wait and try again.")
elif ai_connection_status == "connection_error":
    st.error("The AI connection could not be completed. Please try again later.")
elif ai_connection_status == "success":
    st.success("AI connection successful.")
    st.write("No study material was sent during this test.")

st.write("This program will eventually create interactive nursing patient scenarios.")

st.header("Upload Study Material")

st.write(
    "Upload a TXT nursing note, transcript, or text-based PDF. The program "
    "will read the material during this session. Scanned PDFs are not "
    "supported yet."
)

study_file = st.file_uploader(
    "Choose a TXT or PDF study file", type=["txt", "pdf"]
)

if study_file is None:
    st.session_state.pop("study_analysis_results", None)
    st.session_state.pop("study_analysis_file_id", None)
    st.session_state.pop("ai_source_map", None)
    st.session_state.pop("ai_source_map_error", None)
    st.session_state.pop("ai_error_phase", None)
    st.session_state.pop("ai_chunk_results", None)
    st.write("No study file uploaded yet.")
else:
    study_file_bytes = study_file.getvalue()

    current_study_file_id = (
        f"{study_file.name}:{len(study_file_bytes)}:"
        f"{hashlib.md5(study_file_bytes).hexdigest()}"
    )
    if st.session_state.get("study_analysis_file_id") != current_study_file_id:
        st.session_state.study_analysis_results = None
        st.session_state.study_analysis_file_id = current_study_file_id
        st.session_state.pop("ai_source_map", None)
        st.session_state.pop("ai_source_map_error", None)
        st.session_state.pop("ai_error_phase", None)
        st.session_state.pop("ai_chunk_results", None)

    study_file_text = None
    file_extension = study_file.name.rsplit(".", 1)[-1].lower() if "." in study_file.name else ""

    if file_extension == "pdf":
        if len(study_file_bytes) == 0:
            st.write("The PDF could not be opened. Please try a valid PDF file.")
        else:
            try:
                pdf_document = fitz.open(stream=study_file_bytes, filetype="pdf")
            except Exception:
                pdf_document = None
                st.write("The PDF could not be opened. Please try a valid PDF file.")

            if pdf_document is not None:
                try:
                    page_count = pdf_document.page_count
                    raw_page_texts = [
                        pdf_document.load_page(page_index).get_text()
                        for page_index in range(page_count)
                    ]
                finally:
                    pdf_document.close()

                has_any_text = any(text.strip() for text in raw_page_texts)

                if not has_any_text:
                    st.write(
                        "No readable text was found in this PDF. It may be a "
                        "scanned or image-only document. OCR support will be "
                        "added later."
                    )
                else:
                    some_pages_missing_text = any(
                        not text.strip() for text in raw_page_texts
                    )
                    study_file_text = "\n\n".join(
                        f"[Page {page_index + 1}]\n{text.strip()}"
                        for page_index, text in enumerate(raw_page_texts)
                    )

                    st.write("File uploaded successfully.")
                    st.write(f"File name: {study_file.name}")
                    st.write("File type: PDF")
                    st.write(f"Pages read: {page_count}")
                    st.write(f"Characters read: {len(study_file_text)}")
                    st.write(f"Words read: {len(study_file_text.split())}")

                    if some_pages_missing_text:
                        st.write("Some PDF pages did not contain readable text.")

                    with st.expander("Preview uploaded text"):
                        st.write(study_file_text[:2000])
                        if len(study_file_text) > 2000:
                            st.write(
                                "Preview shortened. The complete extracted text "
                                "remains available during this session."
                            )
    elif file_extension == "txt":
        if len(study_file_bytes) == 0:
            st.write("This TXT file is empty. Please upload a file containing study material.")
        else:
            try:
                study_file_text = study_file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                study_file_text = None
                st.write(
                    "The file could not be read as plain text. Please upload a "
                    "standard TXT file."
                )

            if study_file_text is not None:
                st.write("File uploaded successfully.")
                st.write(f"File name: {study_file.name}")
                st.write(f"Characters read: {len(study_file_text)}")
                st.write(f"Words read: {len(study_file_text.split())}")

                with st.expander("Preview uploaded text"):
                    st.write(study_file_text[:2000])
                    if len(study_file_text) > 2000:
                        st.write(
                            "Preview shortened. The complete text remains available "
                            "during this session."
                        )

    if study_file_text is not None:
        st.subheader("Study Topic Detection")

        if st.button("Analyze Uploaded Notes"):
            st.session_state.study_analysis_results = detect_study_topics(
                study_file_text
            )

        if st.session_state.get("study_analysis_results") is not None:
            detected_topics = st.session_state.study_analysis_results

            if detected_topics:
                for topic_name, match_count, _ in detected_topics:
                    st.write(f"✅ {topic_name} — {match_count} matches")
                st.write(
                    "Detected topics are based on simple keyword matching. "
                    "AI-based understanding will be added later."
                )
                with st.expander("View matched terms"):
                    for topic_name, _, matched_keywords in detected_topics:
                        st.write(f"**{topic_name}**")
                        for keyword in matched_keywords:
                            st.write(f"- {keyword}")

                detected_topic_names = [name for name, _, _ in detected_topics]

                if "Hypertensive Emergency" in detected_topic_names:
                    st.subheader("Scenario Available From Uploaded Notes")
                    st.write(
                        "A built-in Hypertensive Emergency scenario is "
                        "available because this topic was detected in the "
                        "uploaded study material."
                    )
                    st.write(
                        "This scenario is selected from the detected topic. "
                        "It is not yet generated directly from the contents "
                        "of the uploaded notes. AI-based scenario "
                        "generation will be added later."
                    )
                    if st.button("Load Detected Scenario"):
                        st.session_state.topic_select = "Hypertensive Emergency"
                        st.session_state.scenario_started = True
                        st.session_state.he_submitted_action = None
                        st.session_state.he_stage2_active = False
                        st.session_state.he_submitted_second_action = None
                        st.session_state.he_show_debrief = False
                        st.session_state.pop("he_first_action_box", None)
                        st.session_state.pop("he_second_action_box", None)
                        st.session_state.he_loaded_from_detection = True
                        st.session_state.he_detected_source_file = study_file.name
                else:
                    st.write(
                        "A matching topic was detected, but a complete "
                        "built-in scenario for that topic has not been "
                        "added yet."
                    )
            else:
                st.write(
                    "No supported nursing topics were detected in this file yet."
                )

        if "ANTHROPIC_API_KEY" in st.secrets:
            st.subheader("AI Study Analysis")

            st.write(
                "Claude can build a complete AI source map from this "
                "document by dividing it into sections and analyzing each "
                "section. The completed sections are then combined into "
                "one master source map locally in Python, with no "
                "additional Claude request. Nothing is sent to Claude "
                "until you confirm and click the button below."
            )

            st.info(
                "App updates or server restarts may clear unfinished "
                "analysis progress. Complete and download the source map "
                "when possible."
            )

            if len(study_file_text) > AI_SOURCE_MAP_CHARACTER_LIMIT:
                st.write(
                    "This file is larger than the current analysis limit. "
                    "Divide it into smaller study files before creating "
                    "the AI source map."
                )
            else:
                chunk_plan = chunk_study_text(study_file_text, file_extension)
                num_chunks = len(chunk_plan)
                planned_requests = num_chunks
                word_count = len(study_file_text.split())
                safe_stem = re.sub(
                    r"[^A-Za-z0-9_-]+", "_", study_file.name.rsplit(".", 1)[0]
                )

                st.write(
                    f"Extracted material size: {len(study_file_text)} "
                    f"characters and {word_count} words."
                )
                st.write(f"Planned document sections: {num_chunks}")
                st.write(f"Planned Claude API requests: {planned_requests}")
                st.write(
                    "The completed section maps will be combined locally "
                    "without an additional Claude API request."
                )
                st.write(
                    "Creating a complete source map will use API credit. "
                    "No request will be made until you confirm and click "
                    "the button."
                )
                st.write(
                    "Uploading uses no API credit. Keyword detection uses "
                    "no API credit. Checking the confirmation box uses no "
                    "API credit. Each document section requires one "
                    "deliberate Claude request. Local combining, viewing, "
                    "expanding, and downloading use no API credit."
                )

                confirm_checked = st.checkbox(
                    "I understand that this analysis will use API credit.",
                    key="ai_source_map_confirm",
                )

                if st.session_state.get("ai_chunk_results") is None:
                    st.session_state.ai_chunk_results = [None] * num_chunks

                if st.button(
                    "Build Complete AI Source Map", disabled=not confirm_checked
                ):
                    st.session_state.ai_chunk_results = [None] * num_chunks
                    st.session_state.ai_source_map = None
                    st.session_state.ai_source_map_error = None
                    st.session_state.ai_error_phase = None
                    run_chunk_analysis(chunk_plan, study_file.name, 0)

                chunk_results = st.session_state.get("ai_chunk_results") or []
                completed_count = sum(1 for r in chunk_results if r is not None)
                ai_source_map_error = st.session_state.get("ai_source_map_error")
                ai_error_phase = st.session_state.get("ai_error_phase")

                # Backward-compatible support for a session that completed
                # every chunk under the previous architecture and then hit
                # the now-removed paid combining request. Those six (or
                # more) completed chunk results are still fully usable, so
                # assemble the master source map locally instead of
                # requiring a "Retry Combining Step" that no longer exists.
                has_legacy_combine_error = (
                    ai_error_phase == "combine"
                    or ai_source_map_error in LEGACY_COMBINE_ERROR_CODES
                )
                if (
                    st.session_state.get("ai_source_map") is None
                    and num_chunks > 0
                    and completed_count == num_chunks
                    and has_legacy_combine_error
                ):
                    st.session_state.ai_source_map = merge_chunk_source_maps(
                        chunk_results, study_file.name
                    )
                    st.session_state.ai_source_map_error = None
                    st.session_state.ai_error_phase = None
                    ai_source_map_error = None
                    ai_error_phase = None

                if ai_source_map_error:
                    st.error(AI_SOURCE_MAP_ERROR_MESSAGES[ai_source_map_error])

                if ai_error_phase == "chunk":
                    st.write(
                        f"{completed_count} of {num_chunks} sections completed."
                    )
                    retry_label = (
                        "Try Section Again"
                        if completed_count == 0
                        else "Resume AI Analysis"
                    )
                    if st.button(retry_label):
                        run_chunk_analysis(
                            chunk_plan, study_file.name, completed_count
                        )

                if completed_count > 0:
                    completed_sections_payload = build_completed_sections_payload(
                        chunk_results, num_chunks, study_file.name
                    )
                    st.download_button(
                        "Download Completed Section Maps JSON",
                        data=json.dumps(completed_sections_payload, indent=2),
                        file_name=f"{safe_stem}_completed_sections.json",
                        mime="application/json",
                        key="download_completed_sections",
                    )

                source_map = st.session_state.get("ai_source_map")

                if source_map is not None:
                    st.success("Complete AI source map created successfully.")
                    st.write(
                        "The document sections were combined locally. No "
                        "additional Claude API request was used for the "
                        "final source map."
                    )
                    st.write(f"Source file: {study_file.name}")
                    st.write(f"Sections analyzed: {num_chunks}")
                    st.write(
                        "This source map was generated from the complete "
                        "extracted study material."
                    )

                    for map_topic in source_map.get("main_topics", []) or []:
                        with st.expander(map_topic.get("topic") or "Untitled topic"):
                            if map_topic.get("disease_process"):
                                st.write("**Disease process**")
                                st.write(map_topic["disease_process"])

                            list_fields = [
                                ("important_findings", "Important findings"),
                                ("nursing_assessments", "Nursing assessments"),
                                ("nursing_actions", "Nursing actions"),
                                ("emergency_findings", "Emergency findings"),
                                ("patient_teaching", "Patient teaching"),
                                (
                                    "medications_or_treatments",
                                    "Medications or treatments",
                                ),
                                ("diagnostics_or_labs", "Diagnostics or labs"),
                                (
                                    "delegation_or_escalation",
                                    "Delegation or escalation",
                                ),
                                ("source_evidence", "Source evidence"),
                            ]
                            for field_key, field_label in list_fields:
                                field_items = map_topic.get(field_key)
                                if field_items:
                                    st.write(f"**{field_label}**")
                                    for item in field_items:
                                        st.write(f"- {item}")

                    for field_key, field_label in [
                        ("professor_emphasis", "Professor emphasis"),
                        (
                            "excluded_or_not_emphasized",
                            "Excluded or not emphasized",
                        ),
                        ("uncertainties", "Uncertainties"),
                    ]:
                        with st.expander(field_label):
                            field_items = source_map.get(field_key)
                            if field_items:
                                for item in field_items:
                                    st.write(f"- {item}")
                            else:
                                st.write("None identified from this study material.")

                    st.write(
                        "Claude analyzed the uploaded material in sections. "
                        "The section results were combined locally without "
                        "an additional Claude request. Review the source "
                        "map before using it to generate patient scenarios."
                    )
                    st.write(
                        "Viewing, expanding, downloading, or using a "
                        "completed source map during this session does not "
                        "use additional API credit."
                    )

                    st.download_button(
                        "Download Source Map JSON",
                        data=json.dumps(source_map, indent=2),
                        file_name=f"{safe_stem}_source_map.json",
                        mime="application/json",
                    )

st.write(
    "Privacy reminder: Do not upload real patient names, medical record numbers, "
    "dates of birth, addresses, or other protected health information."
)

if "topic_select" not in st.session_state:
    st.session_state.topic_select = "Hypertensive Emergency"

topic = st.selectbox(
    "Choose a nursing topic",
    ["Hypertensive Emergency", "Peripheral Arterial Disease", "Deep Vein Thrombosis"],
    key="topic_select",
)

if "scenario_started" not in st.session_state:
    st.session_state.scenario_started = False

if st.button("Start Scenario"):
    st.session_state.scenario_started = True
    st.session_state.he_submitted_action = None
    st.session_state.he_stage2_active = False
    st.session_state.he_submitted_second_action = None
    st.session_state.he_show_debrief = False
    st.session_state.pop("he_first_action_box", None)
    st.session_state.pop("he_second_action_box", None)
    st.session_state.he_loaded_from_detection = False
    st.session_state.pop("he_detected_source_file", None)

if st.session_state.scenario_started:
    if topic == "Hypertensive Emergency":
        if st.session_state.get("he_loaded_from_detection") and st.session_state.get(
            "he_detected_source_file"
        ):
            st.write("Source connection:")
            st.write(
                "This built-in practice scenario was selected because "
                "Hypertensive Emergency was detected in "
                f"{st.session_state.he_detected_source_file}."
            )

        st.header("Patient Handoff")

        st.write(
            "Mr. Jones is a 68-year-old patient admitted for uncontrolled "
            "hypertension. He suddenly reports a severe headache and blurred vision."
        )

        st.subheader("Vital signs")
        st.write("- Blood pressure: 214/122 mm Hg")
        st.write("- Heart rate: 94 beats/min")
        st.write("- Respiratory rate: 22 breaths/min")
        st.write("- Oxygen saturation: 96% on room air")

        st.write("What would you assess or do first?")

        nursing_action = st.text_area("Type your nursing action", key="he_first_action_box")

        if "he_submitted_action" not in st.session_state:
            st.session_state.he_submitted_action = None

        if "he_stage2_active" not in st.session_state:
            st.session_state.he_stage2_active = False

        if "he_submitted_second_action" not in st.session_state:
            st.session_state.he_submitted_second_action = None

        if "he_show_debrief" not in st.session_state:
            st.session_state.he_show_debrief = False

        if st.button("Submit Action"):
            if nursing_action.strip() == "":
                st.session_state.he_submitted_action = None
                st.write("Please enter an action before submitting.")
            else:
                st.session_state.he_submitted_action = nursing_action

        if st.session_state.he_submitted_action:
            submitted_action = st.session_state.he_submitted_action

            normalized_response = normalize_response_text(submitted_action)
            padded_response = f" {normalized_response} "

            st.write("Your action was recorded.")
            st.write(f"You entered: {submitted_action}")

            st.header("Initial Nursing Priorities")

            priority_categories = compute_stage1_categories(padded_response)

            recognized_count = 0

            for category_name, recognized in priority_categories:
                if recognized:
                    recognized_count += 1
                    st.write(f"✅ {category_name}")
                else:
                    st.write(f"⚠️ Consider: {category_name}")

            if recognized_count >= 3:
                st.write("Strong initial response. You recognized several immediate priorities.")
            else:
                st.write("Review the missing priorities before continuing.")

            st.write(
                "Blood pressure above 180/120 mm Hg with new neurological symptoms "
                "suggests a hypertensive emergency with possible target-organ damage."
            )

            if recognized_count >= 3:
                if st.button("Continue Scenario"):
                    st.session_state.he_stage2_active = True

        if st.session_state.he_stage2_active:
            st.header("Patient Update — 3 Minutes Later")

            st.write(
                "The repeat manual blood pressure is 218/124 mm Hg. Mr. Jones is now "
                "confused and has developed slurred speech, left-sided facial "
                "drooping, and weakness in his left arm. His oxygen saturation "
                "remains 96% on room air. His airway is currently open, and he is "
                "breathing without assistance."
            )

            st.subheader("Last known well")
            st.write(
                "Mr. Jones was speaking normally and moving all extremities "
                "approximately 10 minutes ago."
            )

            st.write("What would you assess or do next?")

            second_action = st.text_area(
                "Type your next nursing action", key="he_second_action_box"
            )

            if st.button("Submit Next Action"):
                if second_action.strip() == "":
                    st.session_state.he_submitted_second_action = None
                    st.write("Please enter an action before submitting.")
                else:
                    st.session_state.he_submitted_second_action = second_action

            if st.session_state.he_submitted_second_action:
                submitted_second_action = st.session_state.he_submitted_second_action

                normalized_second_response = normalize_response_text(submitted_second_action)
                padded_second_response = f" {normalized_second_response} "

                st.write("Your second action was recorded.")
                st.write("You entered:")
                st.write(submitted_second_action)

                st.header("Second-Stage Nursing Priorities")

                second_stage_categories = compute_stage2_categories(padded_second_response)

                second_stage_recognized_count = 0

                for category_name, recognized in second_stage_categories:
                    if recognized:
                        second_stage_recognized_count += 1
                        st.write(f"✅ {category_name}")
                    else:
                        st.write(f"⚠️ Consider: {category_name}")

                if second_stage_recognized_count >= 5:
                    st.write(
                        "Strong next response. You recognized the major "
                        "time-sensitive stroke priorities."
                    )
                elif second_stage_recognized_count >= 3:
                    st.write(
                        "You recognized several priorities, but review the "
                        "missing time-sensitive actions."
                    )
                else:
                    st.write("Review the missing priorities before the scenario continues.")

                st.write(
                    "Sudden facial drooping, unilateral weakness, slurred speech, "
                    "and confusion require an immediate stroke response. The "
                    "last-known-well time helps guide time-sensitive treatment "
                    "decisions. Bedside glucose checks for a possible stroke "
                    "mimic, and urgent brain imaging helps determine whether "
                    "bleeding is present. Keep the patient NPO until swallowing "
                    "safety is evaluated."
                )

                st.write(
                    "The nurse should continue monitoring airway, breathing, "
                    "circulation, vital signs, and neurological status while "
                    "following the facility's stroke protocol."
                )

                if st.button("View Final Debrief"):
                    st.session_state.he_show_debrief = True

                if st.session_state.he_show_debrief:
                    stage1_padded_response = (
                        f" {normalize_response_text(st.session_state.he_submitted_action)} "
                    )
                    stage1_categories = compute_stage1_categories(stage1_padded_response)

                    stage1_recognized = [
                        name for name, recognized in stage1_categories if recognized
                    ]
                    stage1_missing = [
                        name for name, recognized in stage1_categories if not recognized
                    ]
                    stage2_recognized = [
                        name for name, recognized in second_stage_categories if recognized
                    ]
                    stage2_missing = [
                        name for name, recognized in second_stage_categories if not recognized
                    ]

                    st.header("Scenario Debrief")

                    st.subheader("Patient Outcome")
                    st.write(
                        "The stroke response was activated, Mr. Jones remained NPO, "
                        "bedside glucose was checked, and he was transported for "
                        "urgent brain imaging while neurological status and vital "
                        "signs were continuously monitored. The scenario ends here "
                        "because further treatment depends on imaging results, "
                        "provider orders, facility protocols, and the patient's "
                        "eligibility for specific therapies."
                    )

                    st.subheader("What You Recognized")
                    st.write("Initial response")
                    for name in stage1_recognized:
                        st.write(f"✅ {name}")
                    st.write("Second response")
                    for name in stage2_recognized:
                        st.write(f"✅ {name}")

                    st.subheader("Priorities to Review")
                    if stage1_missing or stage2_missing:
                        if stage1_missing:
                            st.write("Initial response")
                            for name in stage1_missing:
                                st.write(f"⚠️ {name}")
                        if stage2_missing:
                            st.write("Second response")
                            for name in stage2_missing:
                                st.write(f"⚠️ {name}")
                    else:
                        st.write("You recognized every priority included in this scenario.")

                    st.subheader("Ideal Nursing Sequence")
                    st.markdown(
                        "1. Verify the severely elevated blood pressure and perform "
                        "an immediate focused assessment.\n"
                        "2. Begin continuous monitoring and rapidly escalate care "
                        "because neurological symptoms suggest target-organ damage.\n"
                        "3. Recognize the new facial drooping, unilateral weakness, "
                        "slurred speech, and confusion as an acute stroke warning.\n"
                        "4. Activate the facility's stroke response and communicate "
                        "the last-known-well time.\n"
                        "5. Perform focused neurological checks and obtain bedside "
                        "blood glucose.\n"
                        "6. Keep the patient NPO and protect airway, swallowing, and "
                        "general safety.\n"
                        "7. Prepare for urgent brain imaging while continuing airway, "
                        "breathing, circulation, vital-sign, and neurological "
                        "monitoring.\n"
                        "8. Follow provider orders and the facility's stroke "
                        "protocol after imaging results are available."
                    )

                    st.subheader("Why This Situation Was Dangerous")
                    st.write(
                        "A blood pressure above 180/120 mm Hg with new neurological "
                        "findings represents a hypertensive emergency because acute "
                        "target-organ damage may be occurring. Sudden facial "
                        "drooping, arm weakness, slurred speech, and confusion are "
                        "time-sensitive stroke warning signs. Delayed recognition or "
                        "escalation can delay imaging and treatment and may worsen "
                        "neurological injury."
                    )

                    st.subheader("Example SBAR")
                    st.markdown("**Situation:**")
                    st.write(
                        "Mr. Jones is a 68-year-old patient admitted with "
                        "uncontrolled hypertension. His repeat manual blood "
                        "pressure is 218/124 mm Hg, and he has developed sudden "
                        "confusion, slurred speech, left facial drooping, and left "
                        "arm weakness."
                    )
                    st.markdown("**Background:**")
                    st.write(
                        "He was speaking normally and moving all extremities "
                        "approximately 10 minutes ago. His oxygen saturation is 96% "
                        "on room air, and his airway is currently open."
                    )
                    st.markdown("**Assessment:**")
                    st.write(
                        "This is an acute neurological change concerning for "
                        "stroke during a hypertensive emergency. A focused "
                        "neurological assessment is being completed, bedside "
                        "glucose is being obtained, and he is being kept NPO with "
                        "continuous monitoring."
                    )
                    st.markdown("**Recommendation:**")
                    st.write(
                        "Activate the facility's stroke protocol immediately, "
                        "evaluate him urgently, and prepare for emergency brain "
                        "imaging and additional provider-directed treatment."
                    )

                    st.write(
                        "This debrief is for education only. Actual nursing "
                        "actions must follow the patient's condition, provider "
                        "orders, facility policy, emergency protocols, "
                        "supervision, and legal scope of practice."
                    )

                    if st.button("Restart Scenario"):
                        st.session_state.scenario_started = False
                        st.session_state.he_submitted_action = None
                        st.session_state.he_stage2_active = False
                        st.session_state.he_submitted_second_action = None
                        st.session_state.he_show_debrief = False
                        st.session_state.pop("he_first_action_box", None)
                        st.session_state.pop("he_second_action_box", None)
                        st.session_state.he_loaded_from_detection = False
                        st.session_state.pop("he_detected_source_file", None)
                        st.rerun()
    else:
        st.write(f"You selected: {topic}")
        st.write("The interactive patient scenario for this topic will be added later.")
