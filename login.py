"""One-time PC ID login. Saves the token straight to ~/.pcexpress-mcp so it never
gets printed or pasted anywhere. Rerun only if a later call says the token is dead."""

import builtins
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pcexpress-mcp-server"))

from login_pcid import login_manual  # noqa: E402
from pcid_token import TokenManager  # noqa: E402

# The browser lands on accounts.pcid.ca/login/success?redirectURL=<encoded com.loblaw.pcx link>,
# which the repo's parser misreads. Dig the code out of either form and hand it over bare.
_input = builtins.input


def _input_code(prompt=""):
    pasted = urllib.parse.unquote(_input(prompt).strip())
    m = re.search(r"[?&]code=([^&\s]+)", pasted)
    return m.group(1) if m else pasted


builtins.input = _input_code

tokens = login_manual()
if not tokens.get("refresh_token"):
    raise SystemExit(f"No refresh token came back: {list(tokens)}")

os.environ["PCEXPRESS_REFRESH_TOKEN"] = tokens["refresh_token"]
tm = TokenManager()
tm._refresh_token = tokens["refresh_token"]
tm._access_token = tokens["access_token"]
tm._expires_at = time.time() + int(tokens.get("expires_in", 3600))
tm._save()
print("\nLogged in to Superstore. Token saved.")
