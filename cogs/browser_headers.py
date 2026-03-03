"""
Browser-like headers for Century APIs.
"""
import random


BROWSER_PROFILES = [
    {
        "versions": [132, 133, 134, 135, 136],
        "platforms": [
            {"os": "Windows NT 10.0; Win64; x64", "sec_platform": '"Windows"'},
            {"os": "Windows NT 11.0; Win64; x64", "sec_platform": '"Windows"'},
            {"os": "Macintosh; Intel Mac OS X 10_15_7", "sec_platform": '"macOS"'},
            {"os": "X11; Linux x86_64", "sec_platform": '"Linux"'},
        ],
    }
]


def get_headers(origin: str | None = None) -> dict:
    """Build randomized browser-like request headers."""
    profile = random.choice(BROWSER_PROFILES)
    version = random.choice(profile["versions"])
    platform = random.choice(profile["platforms"])

    user_agent = (
        f"Mozilla/5.0 ({platform['os']}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36"
    )
    sec_ua = (
        f'"Not:A-Brand";v="99", "Google Chrome";v="{version}", "Chromium";v="{version}"'
    )

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": user_agent,
        "sec-ch-ua": sec_ua,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": platform["sec_platform"],
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }

    if origin:
        headers["origin"] = origin
        headers["referer"] = f"{origin}/"

    return headers
