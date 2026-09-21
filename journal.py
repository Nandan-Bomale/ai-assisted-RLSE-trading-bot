import csv
import os
from datetime import datetime

JOURNAL_FILE = os.path.join(os.path.dirname(__file__), "journal.csv")

def init_journal():
    """Creates the journal CSV file if it doesn't exist."""
    if not os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Symbol", "Action", "Volume", "Entry_Price", "Stop_Loss", "Take_Profit", "Comment"])
        print(f"Created new trading journal at {JOURNAL_FILE}")

def log_trade(symbol, action, volume, entry, sl, tp, comment):
    """Appends a trade record to the journal."""
    with open(JOURNAL_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([timestamp, symbol, action, volume, entry, sl, tp, comment])
