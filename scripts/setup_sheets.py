#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/setup_sheets.py
"""
One-time setup: formats Sheet1, Dashboard, Review, and Waitlist tabs.
Run after any sheet restructure. Safe to re-run — idempotent.

Sheet1 layout (A–N):
  A: fingerprint  (hidden — used by poll_flags.py)
  B: APPLY_FLAG   (checkbox)
  C: relevance_score
  D: title
  E: company
  F: location
  G: remote_status
  H: stage
  I: known_contacts
  J: comp_estimate
  K: ai_notes
  L: date_found
  M: source
  N: url

Dashboard layout (A–N):
  A: STATUS          (dropdown: Flag for Prep / Applied / Interviewing / Offer / Withdrew)
  B: REJECT_REASON   (dropdown: 11 options)
  C: fingerprint     (hidden — used by poll_flags.py)
  D: fit_score       (0-100%, conditional color)
  E: probability_score (0-100%, conditional color)
  F: relevance_score
  G: title           (HYPERLINK formula — clickable)
  H: company
  I: location
  J: remote_status   (color-coded: Remote=red, Hybrid=yellow, Onsite=green)
  K: known_contacts  (amber when non-empty)
  L: comp_estimate
  M: ai_notes
  N: date_found

Review layout (A–H):
  A: STATUS          (dropdown: Promote)
  B: REJECT_REASON   (dropdown: same as Dashboard)
  C: fingerprint     (hidden — used by poll_flags.py)
  D: title           (HYPERLINK formula — clickable)
  E: company
  F: score_flag_reason
  G: source
  H: date_found

Waitlist layout (A–K):
  A: STATUS          (dropdown: Reactivate)
  B: REJECT_REASON   (dropdown: same as Dashboard)
  C: fingerprint     (hidden — used by poll_flags.py)
  D: title           (HYPERLINK formula — clickable)
  E: company
  F: score
  G: location
  H: remote_status
  I: ai_notes
  J: date_found
  K: blocking_app
"""

from google.oauth2 import service_account
from googleapiclient.discovery import build

from findajob.paths import BASE

SA_FILE = f"{BASE}/config/gsheets_creds.json"
with open(f"{BASE}/config/sheet_id.txt") as f:
    SHEET_ID = f.read().strip()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

STATUS_OPTIONS = [
    "Flag for Prep",
    "Ready to Apply",
    "Waitlist",
    "Applied",
    "Interviewing",
    "Offer",
    "Withdrew",
]

REJECT_OPTIONS = [
    "Too Senior",
    "Too Junior",
    "Skills Mismatch",
    "Too TPM-Heavy",
    "Geography/Onsite",
    "Company Not a Fit",
    "Comp Too Low",
    "Low Fit Score",
    "Stale/Closed",
    "Already Applied",
    "Other",
]


def rgb(r, g, b):
    return {"red": r / 255, "green": g / 255, "blue": b / 255}


# STATUS color map (col A, index 0 on Dashboard)
STATUS_COLORS = {
    "Flag for Prep": rgb(208, 228, 250),  # light blue
    "Ready to Apply": rgb(147, 220, 195),  # teal — distinct from Applied
    "Waitlist": rgb(255, 230, 178),  # warm amber — "on hold" signal
    "Applied": rgb(198, 239, 206),  # light green
    "Interviewing": rgb(226, 208, 245),  # soft purple
    "Offer": rgb(255, 217, 102),  # gold
    "Withdrew": rgb(217, 217, 217),  # light grey
}

# REJECT_REASON color map (col B, index 1 on Dashboard)
REJECT_COLORS = {
    "Too Senior": rgb(220, 198, 240),  # soft purple
    "Too Junior": rgb(198, 220, 240),  # soft blue
    "Skills Mismatch": rgb(255, 213, 178),  # soft orange
    "Too TPM-Heavy": rgb(255, 198, 220),  # soft pink
    "Geography/Onsite": rgb(255, 198, 198),  # soft red
    "Company Not a Fit": rgb(220, 220, 220),  # light grey
    "Comp Too Low": rgb(255, 245, 178),  # soft yellow
    "Low Fit Score": rgb(255, 230, 198),  # soft peach
    "Stale/Closed": rgb(200, 200, 200),  # medium grey
    "Already Applied": rgb(198, 240, 215),  # soft green
    "Other": rgb(235, 235, 235),  # near-white grey
}

# remote_status color map — Remote=red (caution), Hybrid=yellow, Onsite=green (ideal)
REMOTE_COLORS = {
    "Remote": rgb(255, 198, 198),  # red
    "Hybrid": rgb(255, 245, 178),  # yellow
    "On-site": rgb(198, 240, 198),  # green
    "Onsite": rgb(198, 240, 198),  # green (alt spelling)
    "Unknown": rgb(220, 220, 220),  # grey
}


def status_cf_rules(sheet_id):
    """Color-code STATUS dropdown (col A, index 0). 'Flag for Prep' highlights entire row."""
    rules = []
    # 'Flag for Prep' highlights the full row
    rules.append(
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 14}],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$A2="Flag for Prep"'}],
                        },
                        "format": {"backgroundColor": STATUS_COLORS["Flag for Prep"]},
                    },
                },
            }
        }
    )
    # Other statuses color just the cell
    for i, (status, color) in enumerate(STATUS_COLORS.items()):
        if status == "Flag for Prep":
            continue
        rules.append(
            {
                "addConditionalFormatRule": {
                    "index": i + 1,
                    "rule": {
                        "ranges": [
                            {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 1}
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": f'=$A2="{status}"'}],
                            },
                            "format": {"backgroundColor": color},
                        },
                    },
                }
            }
        )
    return rules


def reject_cf_rules(sheet_id):
    """Color-code each REJECT_REASON option (Dashboard col B, index 1)."""
    rules = []
    for i, (reason, color) in enumerate(REJECT_COLORS.items()):
        rules.append(
            {
                "addConditionalFormatRule": {
                    "index": i,
                    "rule": {
                        "ranges": [
                            {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 2}
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": f'=$B2="{reason}"'}],
                            },
                            "format": {"backgroundColor": color},
                        },
                    },
                }
            }
        )
    return rules


def remote_cf_rules(sheet_id, col_index):
    """Color-code remote_status values."""
    col_letter = chr(ord("A") + col_index)
    rules = []
    for i, (val, color) in enumerate(REMOTE_COLORS.items()):
        rules.append(
            {
                "addConditionalFormatRule": {
                    "index": i,
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "startColumnIndex": col_index,
                                "endColumnIndex": col_index + 1,
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": f'=${col_letter}2="{val}"'}],
                            },
                            "format": {"backgroundColor": color},
                        },
                    },
                }
            }
        )
    return rules


def pct_score_cf_rules(sheet_id, col_index):
    """Red/yellow/green conditional formatting for 0-100% score columns."""
    col_letter = chr(ord("A") + col_index)
    rules = []
    # Red: < 40%
    rules.append(
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        }
                    ],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": f'=AND(${col_letter}2<40,${col_letter}2<>"")'}],
                        },
                        "format": {"backgroundColor": rgb(255, 198, 198)},  # soft red
                    },
                },
            }
        }
    )
    # Yellow: 40-69%
    rules.append(
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        }
                    ],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": f"=AND(${col_letter}2>=40,${col_letter}2<70)"}],
                        },
                        "format": {"backgroundColor": rgb(255, 245, 178)},  # soft yellow
                    },
                },
            }
        }
    )
    # Green: >= 70%
    rules.append(
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        }
                    ],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": f'=AND(${col_letter}2>=70,${col_letter}2<>"")'}],
                        },
                        "format": {"backgroundColor": rgb(198, 240, 198)},  # soft green
                    },
                },
            }
        }
    )
    return rules


def contacts_highlight(sheet_id, col_index):
    """Amber cell highlight when known_contacts is non-empty."""
    col_letter = chr(ord("A") + col_index)
    return [
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        }
                    ],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": f"=LEN(TRIM(${col_letter}2))>0"}],
                        },
                        "format": {"backgroundColor": rgb(255, 224, 153)},  # amber
                    },
                },
            }
        }
    ]


def score_cf_rules(sheet_id, col_index):
    """Return conditional format rules for the score column."""
    score_range = [
        {
            "sheetId": sheet_id,
            "startRowIndex": 1,
            "startColumnIndex": col_index,
            "endColumnIndex": col_index + 1,
        }
    ]
    return [
        # 8–10: green
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": score_range,
                    "booleanRule": {
                        "condition": {"type": "NUMBER_GREATER_THAN_EQ", "values": [{"userEnteredValue": "8"}]},
                        "format": {"backgroundColor": {"red": 0.714, "green": 0.843, "blue": 0.659}},
                    },
                },
            }
        },
        # 6–7: yellow
        {
            "addConditionalFormatRule": {
                "index": 1,
                "rule": {
                    "ranges": score_range,
                    "booleanRule": {
                        "condition": {
                            "type": "NUMBER_BETWEEN",
                            "values": [{"userEnteredValue": "6"}, {"userEnteredValue": "7"}],
                        },
                        "format": {"backgroundColor": {"red": 1.0, "green": 0.949, "blue": 0.8}},
                    },
                },
            }
        },
        # 1–5: light red
        {
            "addConditionalFormatRule": {
                "index": 2,
                "rule": {
                    "ranges": score_range,
                    "booleanRule": {
                        "condition": {"type": "NUMBER_LESS_THAN_EQ", "values": [{"userEnteredValue": "5"}]},
                        "format": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
                    },
                },
            }
        },
    ]


def rejected_row_cf(sheet_id, total_cols):
    """Grey out entire rows on Sheet1 where stage = 'rejected'."""
    return [
        {
            "addConditionalFormatRule": {
                "index": 3,
                "rule": {
                    "ranges": [
                        {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": total_cols}
                    ],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$H2="rejected"'}],
                        },
                        "format": {
                            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                            "textFormat": {"foregroundColor": {"red": 0.6, "green": 0.6, "blue": 0.6}},
                        },
                    },
                },
            }
        }
    ]


def col_width(sheet_id, col_index, px):
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": col_index, "endIndex": col_index + 1},
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


def main():
    creds = service_account.Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    svc = build("sheets", "v4", credentials=creds)

    # ── Get existing sheet IDs ──────────────────────────────────────────────
    spreadsheet = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sheets_meta = spreadsheet.get("sheets", [])
    sheets = {s["properties"]["title"]: s["properties"]["sheetId"] for s in sheets_meta}

    sheet1_id = sheets.get("Sheet1")
    dash_id = sheets.get("Dashboard")
    review_id = sheets.get("Review")
    waitlist_id = sheets.get("Waitlist")

    # ── Create missing tabs ────────────────────────────────────────────────
    init_requests = []
    create_dash = dash_id is None
    create_review = review_id is None
    create_waitlist = waitlist_id is None

    if create_dash:
        init_requests.append(
            {
                "addSheet": {
                    "properties": {
                        "title": "Dashboard",
                        "index": 1,
                        "gridProperties": {"rowCount": 3000, "columnCount": 14},
                    }
                }
            }
        )
    if create_review:
        init_requests.append(
            {
                "addSheet": {
                    "properties": {
                        "title": "Review",
                        "index": 2,
                        "gridProperties": {"rowCount": 3000, "columnCount": 8},
                    }
                }
            }
        )
    if create_waitlist:
        init_requests.append(
            {
                "addSheet": {
                    "properties": {
                        "title": "Waitlist",
                        "index": 3,
                        "gridProperties": {"rowCount": 3000, "columnCount": 11},
                    }
                }
            }
        )

    if init_requests:
        resp = svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": init_requests}).execute()
        reply_idx = 0
        if create_dash:
            dash_id = resp["replies"][reply_idx]["addSheet"]["properties"]["sheetId"]
            print("Created Dashboard tab.")
            reply_idx += 1
        if create_review:
            review_id = resp["replies"][reply_idx]["addSheet"]["properties"]["sheetId"]
            print("Created Review tab.")
            reply_idx += 1
        if create_waitlist:
            waitlist_id = resp["replies"][reply_idx]["addSheet"]["properties"]["sheetId"]
            print("Created Waitlist tab.")
            reply_idx += 1
    else:
        print("Dashboard, Review, and Waitlist tabs already exist — re-applying formatting.")

    # ── Sheet1 formatting ──────────────────────────────────────────────────
    s1_requests = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet1_id, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1}},
                "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
            }
        },
        # Hide col A (fingerprint)
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet1_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        },
        # Bold + dark header row
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet1_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 14,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        },
                        "backgroundColor": {"red": 0.18, "green": 0.18, "blue": 0.18},
                    }
                },
                "fields": "userEnteredFormat(textFormat(bold,foregroundColor),backgroundColor)",
            }
        },
        # Checkbox on col B (APPLY_FLAG)
        {
            "setDataValidation": {
                "range": {"sheetId": sheet1_id, "startRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 2},
                "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True},
            }
        },
        col_width(sheet1_id, 1, 90),
        col_width(sheet1_id, 2, 55),
        col_width(sheet1_id, 3, 240),
        col_width(sheet1_id, 4, 150),
        col_width(sheet1_id, 5, 130),
        col_width(sheet1_id, 6, 80),
        col_width(sheet1_id, 7, 110),
        col_width(sheet1_id, 8, 140),
        col_width(sheet1_id, 9, 90),
        col_width(sheet1_id, 10, 280),
        col_width(sheet1_id, 11, 100),
        col_width(sheet1_id, 12, 90),
        col_width(sheet1_id, 13, 180),
    ]
    s1_requests += score_cf_rules(sheet1_id, col_index=2)
    s1_requests += rejected_row_cf(sheet1_id, total_cols=14)

    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": s1_requests}).execute()
    print("Sheet1 formatted.")

    # ── Dashboard formatting ───────────────────────────────────────────────
    dash_requests = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": dash_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Bold + dark header row
        {
            "repeatCell": {
                "range": {
                    "sheetId": dash_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 12,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        },
                        "backgroundColor": {"red": 0.18, "green": 0.18, "blue": 0.18},
                    }
                },
                "fields": "userEnteredFormat(textFormat(bold,foregroundColor),backgroundColor)",
            }
        },
        # STATUS dropdown on col A (replaces checkbox)
        {
            "setDataValidation": {
                "range": {"sheetId": dash_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 1},
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": opt} for opt in STATUS_OPTIONS],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        # REJECT_REASON dropdown on col B
        {
            "setDataValidation": {
                "range": {"sheetId": dash_id, "startRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 2},
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": opt} for opt in REJECT_OPTIONS],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        # Explicitly unhide col B (may have been hidden from prior layout)
        {
            "updateDimensionProperties": {
                "range": {"sheetId": dash_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
                "properties": {"hiddenByUser": False},
                "fields": "hiddenByUser",
            }
        },
        # Hide col C (fingerprint)
        {
            "updateDimensionProperties": {
                "range": {"sheetId": dash_id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3},
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        },
        # Column widths
        col_width(dash_id, 0, 120),  # A: STATUS
        col_width(dash_id, 1, 140),  # B: REJECT_REASON
        col_width(dash_id, 3, 50),  # D: fit_score
        col_width(dash_id, 4, 50),  # E: probability_score
        col_width(dash_id, 5, 55),  # F: relevance_score
        col_width(dash_id, 6, 280),  # G: title (hyperlink)
        col_width(dash_id, 7, 150),  # H: company
        col_width(dash_id, 8, 130),  # I: location
        col_width(dash_id, 9, 80),  # J: remote_status
        col_width(dash_id, 10, 140),  # K: known_contacts
        col_width(dash_id, 11, 90),  # L: comp_estimate
        col_width(dash_id, 12, 300),  # M: ai_notes
        col_width(dash_id, 13, 100),  # N: date_found
    ]

    # Conditional formatting
    dash_requests += status_cf_rules(dash_id)  # col A + row highlight for Flag for Prep
    dash_requests += reject_cf_rules(dash_id)  # col B
    dash_requests += pct_score_cf_rules(dash_id, col_index=3)  # col D: fit_score
    dash_requests += pct_score_cf_rules(dash_id, col_index=4)  # col E: probability_score
    dash_requests += remote_cf_rules(dash_id, col_index=9)  # col J: remote_status
    dash_requests += contacts_highlight(dash_id, col_index=10)  # col K: known_contacts

    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": dash_requests}).execute()
    print("Dashboard formatted.")

    # ── Row banding (separate call — idempotent via delete+add) ───────────
    # Find and delete any existing banding on Dashboard, then re-add
    # Re-fetch sheet metadata since we may have created new tabs
    spreadsheet = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sheets_meta = spreadsheet.get("sheets", [])

    dash_sheet = next((s for s in sheets_meta if s["properties"]["sheetId"] == dash_id), None)
    existing_banding = dash_sheet.get("bandedRanges", []) if dash_sheet else []
    banding_requests = [{"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}} for b in existing_banding]
    banding_requests.append(
        {
            "addBanding": {
                "bandedRange": {
                    "range": {"sheetId": dash_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 14},
                    "rowProperties": {
                        "firstBandColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "secondBandColor": rgb(245, 245, 248),
                    },
                },
            }
        }
    )
    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": banding_requests}).execute()
    print("Dashboard row banding applied.")

    # ── Review tab formatting ─────────────────────────────────────────────
    REVIEW_STATUS_OPTIONS = ["Promote"]

    review_requests = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": review_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Bold + dark header row
        {
            "repeatCell": {
                "range": {
                    "sheetId": review_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 8,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        },
                        "backgroundColor": {"red": 0.18, "green": 0.18, "blue": 0.18},
                    }
                },
                "fields": "userEnteredFormat(textFormat(bold,foregroundColor),backgroundColor)",
            }
        },
        # STATUS dropdown on col A (Promote only)
        {
            "setDataValidation": {
                "range": {"sheetId": review_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 1},
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": opt} for opt in REVIEW_STATUS_OPTIONS],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        # REJECT_REASON dropdown on col B (same options as Dashboard)
        {
            "setDataValidation": {
                "range": {"sheetId": review_id, "startRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 2},
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": opt} for opt in REJECT_OPTIONS],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        # Hide col C (fingerprint)
        {
            "updateDimensionProperties": {
                "range": {"sheetId": review_id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3},
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        },
        # Column widths
        col_width(review_id, 0, 100),  # A: STATUS
        col_width(review_id, 1, 140),  # B: REJECT_REASON
        col_width(review_id, 3, 280),  # D: title (hyperlink)
        col_width(review_id, 4, 150),  # E: company
        col_width(review_id, 5, 400),  # F: score_flag_reason
        col_width(review_id, 6, 90),  # G: source
        col_width(review_id, 7, 100),  # H: date_found
    ]

    # Conditional formatting: "Promote" highlights row blue
    review_requests.append(
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [{"sheetId": review_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 8}],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$A2="Promote"'}],
                        },
                        "format": {"backgroundColor": rgb(208, 228, 250)},  # light blue
                    },
                },
            }
        }
    )

    # Reject reason color on col B
    review_requests += reject_cf_rules(review_id)

    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": review_requests}).execute()
    print("Review tab formatted.")

    # Review tab row banding
    review_sheet = next((s for s in sheets_meta if s["properties"]["sheetId"] == review_id), None)
    review_banding = review_sheet.get("bandedRanges", []) if review_sheet else []
    rb_requests = [{"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}} for b in review_banding]
    rb_requests.append(
        {
            "addBanding": {
                "bandedRange": {
                    "range": {"sheetId": review_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 8},
                    "rowProperties": {
                        "firstBandColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "secondBandColor": rgb(245, 245, 248),
                    },
                },
            }
        }
    )
    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": rb_requests}).execute()
    print("Review row banding applied.")

    # ── Waitlist tab formatting ───────────────────────────────────────────
    WAITLIST_STATUS_OPTIONS = ["Reactivate"]

    waitlist_requests = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": waitlist_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Bold + dark header row
        {
            "repeatCell": {
                "range": {
                    "sheetId": waitlist_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 11,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        },
                        "backgroundColor": {"red": 0.18, "green": 0.18, "blue": 0.18},
                    }
                },
                "fields": "userEnteredFormat(textFormat(bold,foregroundColor),backgroundColor)",
            }
        },
        # STATUS dropdown on col A (Reactivate only)
        {
            "setDataValidation": {
                "range": {"sheetId": waitlist_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 1},
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": opt} for opt in WAITLIST_STATUS_OPTIONS],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        # REJECT_REASON dropdown on col B (same options as Dashboard)
        {
            "setDataValidation": {
                "range": {"sheetId": waitlist_id, "startRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 2},
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": opt} for opt in REJECT_OPTIONS],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        # Hide col C (fingerprint)
        {
            "updateDimensionProperties": {
                "range": {"sheetId": waitlist_id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3},
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        },
        # Column widths
        col_width(waitlist_id, 0, 110),   # A: STATUS
        col_width(waitlist_id, 1, 140),   # B: REJECT_REASON
        col_width(waitlist_id, 3, 280),   # D: title (hyperlink)
        col_width(waitlist_id, 4, 150),   # E: company
        col_width(waitlist_id, 5, 55),    # F: score
        col_width(waitlist_id, 6, 130),   # G: location
        col_width(waitlist_id, 7, 80),    # H: remote
        col_width(waitlist_id, 8, 300),   # I: ai_notes
        col_width(waitlist_id, 9, 100),   # J: date
        col_width(waitlist_id, 10, 250),  # K: blocking_app
    ]

    # Conditional formatting: "Reactivate" highlights entire row teal
    waitlist_requests.append(
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [
                        {"sheetId": waitlist_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 11}
                    ],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$A2="Reactivate"'}],
                        },
                        "format": {"backgroundColor": rgb(147, 220, 195)},  # teal
                    },
                },
            }
        }
    )

    # Reject reason colors on col B
    waitlist_requests += reject_cf_rules(waitlist_id)

    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": waitlist_requests}).execute()
    print("Waitlist tab formatted.")

    # Waitlist tab row banding — re-fetch metadata if tab was newly created
    if create_waitlist:
        spreadsheet = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheets_meta = spreadsheet.get("sheets", [])

    waitlist_sheet = next((s for s in sheets_meta if s["properties"]["sheetId"] == waitlist_id), None)
    waitlist_banding = waitlist_sheet.get("bandedRanges", []) if waitlist_sheet else []
    wb_requests = [{"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}} for b in waitlist_banding]
    wb_requests.append(
        {
            "addBanding": {
                "bandedRange": {
                    "range": {"sheetId": waitlist_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 11},
                    "rowProperties": {
                        "firstBandColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "secondBandColor": rgb(245, 245, 248),
                    },
                },
            }
        }
    )
    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": wb_requests}).execute()
    print("Waitlist row banding applied.")

    print()
    print("Done. Run sync_sheet.py to populate.")


if __name__ == "__main__":
    main()
