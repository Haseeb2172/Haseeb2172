from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape


USERNAME = os.environ.get("PROFILE_USERNAME", "Haseeb2172")
DISPLAY_NAME = os.environ.get("PROFILE_NAME", "Abdul Haseeb")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUTPUT = Path("assets/contribution-graph.svg")
NUMBER_OF_DAYS = 31


def date_window() -> tuple[date, date]:
    end = datetime.now(timezone.utc).date()
    return end - timedelta(days=NUMBER_OF_DAYS - 1), end


def fetch_with_graphql(start: date, end: date) -> dict[str, int]:
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """

    body = json.dumps(
        {
            "query": query,
            "variables": {
                "login": USERNAME,
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{end.isoformat()}T23:59:59Z",
            },
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "Haseeb2172-profile-readme",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    if payload.get("errors"):
        raise RuntimeError(payload["errors"][0]["message"])

    weeks = payload["data"]["user"]["contributionsCollection"][
        "contributionCalendar"
    ]["weeks"]

    return {
        day["date"]: int(day["contributionCount"])
        for week in weeks
        for day in week["contributionDays"]
    }


def fetch_from_public_profile(start: date, end: date) -> dict[str, int]:
    url = f"https://github.com/users/{USERNAME}/contributions"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 Haseeb2172-profile-readme"},
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")

    cell_pattern = re.compile(
        r'<td[^>]*data-date="(?P<date>\d{4}-\d{2}-\d{2})"[^>]*>'
        r'.*?</td>\s*<tool-tip[^>]*>(?P<label>.*?)</tool-tip>',
        re.DOTALL,
    )

    counts: dict[str, int] = {}

    for match in cell_pattern.finditer(html):
        day = date.fromisoformat(match.group("date"))

        if not start <= day <= end:
            continue

        label = re.sub(r"<[^>]+>", "", match.group("label"))
        number = re.search(r"([\d,]+) contribution", label)

        counts[day.isoformat()] = (
            int(number.group(1).replace(",", "")) if number else 0
        )

    if not counts:
        raise RuntimeError("GitHub returned no contribution data")

    return counts


def contribution_counts(start: date, end: date) -> list[int]:
    if TOKEN:
        try:
            values = fetch_with_graphql(start, end)
        except Exception as error:
            print(f"GraphQL request failed, using public profile: {error}")
            values = fetch_from_public_profile(start, end)
    else:
        values = fetch_from_public_profile(start, end)

    return [
        values.get((start + timedelta(days=index)).isoformat(), 0)
        for index in range(NUMBER_OF_DAYS)
    ]


def rounded_maximum(value: int) -> int:
    if value <= 3:
        return 3

    if value <= 6:
        return 6

    if value <= 10:
        return 10

    return ((value + 4) // 5) * 5


def build_svg(start: date, counts: list[int]) -> str:
    width = 900
    height = 280

    left = 62
    right = 26
    top = 58
    bottom = 42

    plot_width = width - left - right
    plot_height = height - top - bottom

    maximum = rounded_maximum(max(counts, default=0))

    x_values = [
        left + (index * plot_width / (NUMBER_OF_DAYS - 1))
        for index in range(NUMBER_OF_DAYS)
    ]

    y_values = [
        top + plot_height - (count / maximum * plot_height)
        for count in counts
    ]

    points = " ".join(
        f"{x:.2f},{y:.2f}"
        for x, y in zip(x_values, y_values, strict=True)
    )

    horizontal_grid = []

    for step in range(4):
        value = maximum * step / 3
        y = top + plot_height - (step * plot_height / 3)

        horizontal_grid.append(
            f'<line x1="{left}" y1="{y:.2f}" '
            f'x2="{width - right}" y2="{y:.2f}" '
            'stroke="#17304A" stroke-width="1" opacity="0.62"/>'
        )

        horizontal_grid.append(
            f'<text x="{left - 13}" y="{y + 3:.2f}" '
            f'text-anchor="end" class="axis">{round(value)}</text>'
        )

    vertical_grid = []
    day_labels = []

    for index, x in enumerate(x_values):
        current = start + timedelta(days=index)

        if index % 5 == 0 or index == NUMBER_OF_DAYS - 1:
            vertical_grid.append(
                f'<line x1="{x:.2f}" y1="{top}" '
                f'x2="{x:.2f}" y2="{top + plot_height}" '
                'stroke="#17304A" stroke-width="1" opacity="0.35"/>'
            )

        day_labels.append(
            f'<text x="{x:.2f}" y="{height - 20}" '
            f'text-anchor="middle" class="day">{current.day}</text>'
        )

    circles = "".join(
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" '
        'fill="#E0F2FE" stroke="#38BDF8" stroke-width="1.4"/>'
        for x, y in zip(x_values, y_values, strict=True)
    )

    title = escape(f"{DISPLAY_NAME}'s Contribution Graph")

    return f'''<svg xmlns="http://www.w3.org/2000/svg"
  width="{width}"
  height="{height}"
  viewBox="0 0 {width} {height}"
  role="img"
  aria-labelledby="title desc">

  <title id="title">{title}</title>

  <desc id="desc">
    Daily public GitHub contributions during the last {NUMBER_OF_DAYS} days.
  </desc>

  <style>
    .title {{
      fill: #E0F2FE;
      font: 600 15px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}

    .axis {{
      fill: #94A3B8;
      font: 9px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}

    .day {{
      fill: #64748B;
      font: 8px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
  </style>

  <rect
    x="0.5"
    y="0.5"
    width="{width - 1}"
    height="{height - 1}"
    fill="#080C14"
    stroke="#0C4A6E"
  />

  <text
    x="{width / 2}"
    y="30"
    text-anchor="middle"
    class="title">{title}</text>

  {''.join(horizontal_grid)}
  {''.join(vertical_grid)}

  <text
    x="18"
    y="{top + plot_height / 2}"
    text-anchor="middle"
    class="axis"
    transform="rotate(-90 18 {top + plot_height / 2})">
    Contributions
  </text>

  <text
    x="{width / 2}"
    y="{height - 5}"
    text-anchor="middle"
    class="axis">
    Days
  </text>

  <polyline
    points="{points}"
    fill="none"
    stroke="#38BDF8"
    stroke-width="2.2"
    stroke-linejoin="round"
    stroke-linecap="round"
  />

  {circles}
  {''.join(day_labels)}

</svg>
'''


def main() -> None:
    start, end = date_window()
    counts = contribution_counts(start, end)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build_svg(start, counts), encoding="utf-8")

    print(
        f"Updated {OUTPUT} for {USERNAME}: "
        f"{sum(counts)} contributions"
    )


if __name__ == "__main__":
    main()
