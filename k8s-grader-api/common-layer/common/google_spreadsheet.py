import csv
import os
import random
from io import StringIO

import requests
from common.status import TestResult


def get_npc_background_google_spreadsheet(spreadsheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        csv_str = response.content.decode("utf-8")
        f = StringIO(csv_str)
        spreadsheet_data = []
        reader = csv.reader(f, delimiter=",")
        next(reader, None)  # Skip the header row
        for row in reader:
            if len(row) < 4:
                continue
            name, age, gender, background = row[:4]
            if not name:
                continue
            spreadsheet_data.append(
                {"name": name, "age": age, "gender": gender, "background": background}
            )
        return spreadsheet_data
    return None


def get_easter_egg_link(current_test_result: TestResult) -> str:
    spreadsheet_id = os.environ.get("EasterEggSheetId")
    file = "/tmp/easter_egg.csv"
    csv_str = None
    
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            csv_str = f.read()
    else:
        url = (
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv"
        )
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                csv_str = response.content.decode("utf-8")
                with open("/tmp/easter_egg.csv", "w", encoding="utf-8") as file:
                    file.write(csv_str)
        except Exception:
            # If we can't fetch easter eggs, just return None
            return None
    
    if not csv_str:
        return None
    
    f = StringIO(csv_str)
    spreadsheet_data = []
    reader = csv.reader(f, delimiter=",")
    next(reader, None)  # Skip the header row
    for row in reader:
        if len(row) < 2:
            continue
        test_result, link = row[:2]
        if not test_result:
            continue
        spreadsheet_data.append({"test_result": test_result, "link": link})
    spreadsheet_data = [
        item
        for item in spreadsheet_data
        if item["test_result"] == current_test_result.name
    ]

    if spreadsheet_data:
        return random.choice(spreadsheet_data)["link"]
    return None
