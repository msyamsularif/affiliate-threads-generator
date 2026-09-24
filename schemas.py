"""Tool schemas — what the model reads when deciding to call a tool.

The descriptions are load-bearing. They are the only place that tells the model
*when* a tool is allowed to be used, and they must be blunt about the fact that
``threads_publish`` is irreversible.
"""

from __future__ import annotations

THREADS_PUBLISH: dict = {
    "name": "threads_publish",
    "description": (
        "PUBLISH an approved thread to Meta Threads. THIS IS IRREVERSIBLE: the posts go "
        "live on a public profile and cannot be edited or deleted by this tool.\n\n"
        "Call it only when ALL of the following are true:\n"
        "  1. The human explicitly approved THIS product in THIS conversation, in their own "
        "message, after seeing the preview. Words like 'approve', 'setuju', 'publish', "
        "'post aja', 'gas' count. Silence, an earlier approval of a different product, or "
        "your own judgement do NOT count.\n"
        "  2. The preview you showed included the Product ID, and it matches the product_id "
        "you pass here.\n"
        "  3. You already ran the evidence, anti-slop and affiliate review steps on this copy.\n\n"
        "The tool independently re-reads the Google Sheet and refuses to publish unless the "
        "row's Status is still the eligible status. It also refuses copy that breaks the hard "
        "guardrails (character limits, link limits, missing disclosure, missing affiliate URL, "
        "or fabricated first-hand experience). On success it writes Status=Done and the "
        "Threads URL back into the Sheet; on any failure it leaves the Sheet untouched.\n\n"
        "If the Sheet write fails after a successful publish, re-calling this tool with the "
        "same product_id repairs the Sheet instead of publishing a duplicate.\n\n"
        "Under publish_mode \"two_stage\" the affiliate link is deferred: the thread publishes "
        "first, the row moves to the plugin's link-pending status instead of Done, and the link "
        "goes out later as a reply — call this tool again with stage \"link\" and the single "
        "reply post once the human decides the thread has been seen."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": (
                    "The ID column value of the Sheet row being published. Must be the exact "
                    "Product ID shown in the preview the human approved."
                ),
            },
            "posts": {
                "type": "array",
                "minItems": 1,
                "maxItems": 30,
                "description": (
                    "The thread, in order. Post 1 is the root; each later post is published as "
                    "a reply to the previous one. 3-10 posts is the target range — the "
                    "configured max_posts is the hard bound, and the tool refuses a longer "
                    "thread. The final post carries the affiliate link and the disclosure, "
                    "unless the link is deferred to a later reply (see stage)."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": (
                                "The exact post text. Max 500 characters (emoji count as their "
                                "UTF-8 byte length). No personal-experience claims."
                            ),
                        },
                        "image_url": {
                            "type": "string",
                            "description": (
                                "Optional public HTTPS URL of an image for this post. Omit for "
                                "text-only. Threads fetches the image itself, so it must be "
                                "publicly reachable."
                            ),
                        },
                    },
                    "required": ["text"],
                },
            },
            "confirm_publish": {
                "type": "boolean",
                "description": (
                    "Must be true. Set it only after the human's explicit approval in this "
                    "conversation. Setting it while guessing is a failure of the process."
                ),
            },
            "stage": {
                "type": "string",
                "enum": ["auto", "thread", "link"],
                "description": (
                    "Which half of a publish this call is. 'auto' (the default) follows the "
                    "Sheet's own state: an eligible row starts the thread, and a row left in "
                    "the link-pending status gets its deferred link reply. 'thread' insists on "
                    "publishing the thread, and 'link' insists on the deferred link reply — a "
                    "single post in `posts` carrying the affiliate URL and the disclosure, "
                    "appended to the thread that is already live. Publishing the whole thread "
                    "and its link in one call is the default configuration (publish_mode "
                    "'single'), in which case only 'thread' applies."
                ),
            },
            "approval_note": {
                "type": "string",
                "description": (
                    "Optional short quote of the human's approving words, for the audit log."
                ),
            },
            "topic_tag": {
                "type": "string",
                "description": (
                    "The topic tag for the root post — how the post reaches that topic's feed "
                    "and, when the topic has a Threads community, the community too. Pass the "
                    "bare topic (1-50 characters, no '.' or '&', no leading '#'): a reader-checks "
                    "topic like 'fotografi', never the product name. It is metadata, so it never "
                    "appears in the copy and no hashtag belongs there either. Required unless "
                    "require_topic_tag is off. Only the root post takes one."
                ),
            },
            "spreadsheet_id": {
                "type": "string",
                "description": "Optional override of the configured spreadsheet id.",
            },
            "sheet_tab": {
                "type": "string",
                "description": "Optional override of the configured sheet tab name.",
            },
        },
        "required": ["product_id", "posts", "confirm_publish"],
    },
}


THREADS_CHECK: dict = {
    "name": "threads_check",
    "description": (
        "Read-only preflight for the affiliate Threads pipeline. Publishes nothing and writes "
        "nothing.\n\n"
        "Use it to answer questions like 'is my setup working?', 'when does the Threads token "
        "expire?', 'which candidate is next?', or 'is the Sheet reachable?'. It reports:\n"
        "  - whether THREADS_ACCESS_TOKEN / THREADS_USER_ID resolve, and the token's validity "
        "and expiry from the Threads API\n"
        "  - whether the configured Google Sheet can be read through the bundled "
        "google-workspace skill\n"
        "  - the next eligible candidate row (lowest ID with the eligible Status), if any\n\n"
        "Run this before telling the human that something is broken."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "include_candidate": {
                "type": "boolean",
                "description": "Include the next eligible candidate row in the result. Default true.",
            },
            "include_sheet": {
                "type": "boolean",
                "description": "Probe Google Sheets reachability. Default true.",
            },
            "include_token": {
                "type": "boolean",
                "description": "Probe the Threads API for identity and token expiry. Default true.",
            },
            "spreadsheet_id": {
                "type": "string",
                "description": "Optional override of the configured spreadsheet id.",
            },
            "sheet_tab": {
                "type": "string",
                "description": "Optional override of the configured sheet tab name.",
            },
        },
        "required": [],
    },
}
