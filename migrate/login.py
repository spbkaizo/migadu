"""Interactive Microsoft sign-in. Run this alone, then run report.py.

Kept separate from the survey so the device code is on screen only while it is
live, and so the long-running survey never blocks on a login prompt.
"""

import oauth

if __name__ == "__main__":
    tok = oauth.get_token()
    print(f"Token cached to {oauth.TOKEN_FILE}")
    print("Now run:  python3 report.py <your-address>@example.com")
