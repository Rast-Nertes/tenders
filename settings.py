import os

from dotenv import load_dotenv

load_dotenv()

ZAKUP_KONTUR_LOGIN = os.getenv("ZAKUP_KONTUR_LOGIN")
ZAKUP_KONTUR_PASS = os.getenv("ZAKUP_KONTUR_PASS")
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH")
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")