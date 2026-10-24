"""First-time setup, run by Setup.cmd: OurGroceries login, then Superstore (PC ID) login.
Safe to run again: a working OurGroceries login is kept, and the Superstore login is redone."""

import asyncio
import getpass
import json
import os
import subprocess
import sys
import winreg
from pathlib import Path

from ourgroceries import OurGroceries

HERE = Path(__file__).parent
SETTINGS = HERE / "settings.json"
LIST_NAME = json.loads(SETTINGS.read_text(encoding="utf-8")).get("list", "Superstore") if SETTINGS.exists() else "Superstore"


def get_env(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return ""


def save_env(name, value):
    """Windows user environment, where groceries.py looks. No setx: it mangles & and ^."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


async def list_names(user, password):
    og = OurGroceries(user, password)
    await og.login()
    return [lst["name"] for lst in (await og.get_my_lists())["shoppingLists"]]


def ourgroceries():
    user, password = get_env("OURGROCERIES_USER"), get_env("OURGROCERIES_PASSWORD")
    if not (user and password):
        answer = input("\nDo you use OurGroceries for your grocery list? Type y for yes, or press Enter to skip: ")
        if answer.strip().lower() != "y":
            print("Skipped. The picker works without it. Run Setup again any time to connect it.")
            return
    while True:
        if user and password:
            try:
                names = asyncio.run(list_names(user, password))
                break
            except Exception:
                print("\nThat OurGroceries email or password didn't work. Try again.")
        user = input("\nOurGroceries email: ").strip()
        password = getpass.getpass("OurGroceries password (it won't show as you type): ")
    save_env("OURGROCERIES_USER", user)
    save_env("OURGROCERIES_PASSWORD", password)
    print("OurGroceries login works.")
    while LIST_NAME.lower() not in (n.lower() for n in names):
        print(f'\nYou don\'t have a list called "{LIST_NAME}" yet. Your lists: {", ".join(names) or "none"}')
        input(f'Make a list called "{LIST_NAME}" in the OurGroceries app, then press Enter here.')
        names = asyncio.run(list_names(user, password))
    print(f'Found your "{LIST_NAME}" list.')


def superstore():
    print("\nNow the Superstore login. A browser window opens. Sign in with your PC Optimum")
    print("account. The page ends on an error or a blank page; that's expected.")
    print("Copy the whole address from the address bar and paste it here.")
    if subprocess.run([sys.executable, str(HERE / "login.py")]).returncode:
        raise SystemExit("The Superstore login didn't finish. Run Setup again.")
    sys.path.insert(0, str(HERE))
    os.chdir(HERE)
    import groceries  # needs the token login.py just saved

    orders = groceries.api.get_historical_orders()["orderHistory"]
    print(f"Superstore login works. Found {len(orders)} past orders.")


if __name__ == "__main__":
    ourgroceries()
    superstore()
