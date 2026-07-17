"""Shared text-rule constants for CaseOps message gates and evals.

Single source of truth for rules that both `pipeline_gates` (enforcement)
and `output_evals` (measurement) apply to the same artifacts. The
human-readable versions of the voice rules live in
`skills/jira-response-drafting/SKILL.md` and the Step 10 prompt in
`skills/caseops-pipeline/references/sub-agent-prompts.md`; when editing the
rules there, update the machine copies here in the same change.
"""

from __future__ import annotations

import re


# Voice: banned corporate vocabulary for customer-facing Jira messages.
# Mirrors skills/jira-response-drafting/SKILL.md "Words to avoid".
BANNED_CORPORATE_WORDS = (
    "seamless",
    "robust",
    "leverage",
    "optimize",
    "utilize",
    "stakeholder",
    "unlock",
    "game-changing",
    "transformation",
    "scalable solution",
    "end-to-end",
    "strategic alignment",
    "operational excellence",
)
BANNED_CORPORATE_PATTERNS = tuple(
    re.compile(rf"(?i)\b{re.escape(word)}\b") for word in BANNED_CORPORATE_WORDS
)

# Voice: first-person plural is not allowed in customer-facing messages.
# The bare "we" alternative also matches contractions (we've, we'll, ...)
# because the apostrophe forms a word boundary.
FIRST_PERSON_PLURAL_RE = re.compile(r"(?i)\b(?:we|us|let\s+us)\b")

# Greeting words that are not a reporter's name; "Hi team," must not make
# later mentions of "the team" count as reporter-name repetition.
GENERIC_GREETING_WORDS = frozenset(
    {"team", "there", "all", "everyone", "everybody", "folks", "both", "y'all"}
)

# Salesforce record Ids.
# ANY: any 15/18-char token shaped like an Id (used to keep raw Ids out of
# customer messages — deliberately broad).
# PREFIXED: Id with a known key prefix (used to prove an escalation names a
# concrete record — deliberately narrow). Covers standard-object prefixes
# (00x), Case (500), Flow definition/version (300/301), permission sets
# (0PS), and custom-object prefixes (aXX).
SALESFORCE_ID_ANY_RE = re.compile(r"\b[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?\b")
# The digit lookahead keeps 15-18 char English words starting with "a"
# (administratively, authoritatively, ...) from matching via the aXX
# custom-object alternative; every real Salesforce Id contains digits.
SALESFORCE_ID_PREFIXED_RE = re.compile(
    r"\b(?=[A-Za-z0-9]*\d)(?:00[0-9A-Za-z]|301|300|500|0PS|a[0-9A-Za-z]{2})[A-Za-z0-9]{12,15}\b"
)

# Escalation quality: discovery-task language that must not reach
# Engineering outside an explicit "Open Questions" section.
ASK_TO_DISCOVER_PHRASES = (
    "TBD",
    "search the codebase",
    "search codebase",
    "which specific",
)
ASK_TO_DISCOVER_PATTERNS = tuple(
    re.compile(re.escape(phrase), re.IGNORECASE) for phrase in ASK_TO_DISCOVER_PHRASES
)
