#!/usr/bin/env python3
# scripts/init_sheet.py
"""Write column headers to Sheet1 row 1. Run once on initial setup or after restructure."""

from google.oauth2 import service_account
from googleapiclient.discovery import build

from findajob.paths import BASE

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SA_FILE = f"{BASE}/config/gsheets_creds.json"
with open(f"{BASE}/config/sheet_id.txt") as f:
    SHEET_ID = f.read().strip()

HEADERS = [
    "fingerprint",
    "APPLY_FLAG",
    "relevance_score",
    "title",
    "company",
    "location",
    "remote_status",
    "stage",
    "known_contacts",
    "comp_estimate",
    "ai_notes",
    "date_found",
    "source",
    "url",
]

creds = service_account.Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
svc = build("sheets", "v4", credentials=creds)
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="Sheet1!A1", valueInputOption="RAW", body={"values": [HEADERS]}
).execute()
print("Headers written.")
