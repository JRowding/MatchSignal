"""Publisher-ranked current tables. Never infer a table from historical scores."""
import re
from html import unescape
import requests
from .fixtures import TheSportsDBProvider
from .normalization import canonical_team, team_key


def clean(value):
    return ' '.join(unescape(re.sub('<[^>]+>', ' ', value)).split())


def validate_table(rows):
    if not 8 <= len(rows) <= 32:
        raise ValueError(f'Incomplete/unexpected table size: {len(rows)}')
    if sorted(r['position'] for r in rows) != list(range(1, len(rows) + 1)):
        raise ValueError('Table ranks missing or duplicated')
    keys = [team_key(canonical_team(r['team'])) for r in rows]
    if any(not key for key in keys) or len(set(keys)) != len(keys):
        raise ValueError('Empty or ambiguous team identity in table')
    return sorted(rows, key=lambda r: r['position'])


def parse_sky_table(content, league):
    title = clean(re.search(r'<title>(.*?)</title>', content, re.S).group(1))
    expected = league.name.replace('One', '1').replace('Two', '2')
    title_normal = title.replace('One', '1').replace('Two', '2')
    if expected not in title_normal:
        raise ValueError(f'Wrong competition page: {title}')
    rows = []
    # Main table only: avoid sidebar league previews; combine Scottish split
    # sections only when their published positions remain globally contiguous.
    for table in re.findall(r'<table\b.*?</table>', content, re.S):
        if 'data-live-key="pos"' not in table:
            continue
        for row in re.findall(r'<tr\b.*?</tr>', table, re.S):
            cells = dict(re.findall(r'<td\b[^>]*data-live-key="([^"]+)"[^>]*>(.*?)</td>', row, re.S))
            if 'pos' not in cells or 'team' not in cells:
                continue
            rows.append({'position': int(clean(cells['pos'])),
                         'team': canonical_team(clean(cells['team'])),
                         'played': int(clean(cells['pld']))})
    return validate_table(rows)


class StandingsProvider(TheSportsDBProvider):
    def table(self, league):
        errors = []
        # Sky's accessible full table is preferred. A failed download never
        # replaces a previously validated table with an empty list.
        url = f'https://www.skysports.com/{league.sky}-table'
        try:
            response, health = self._get('sky-table', league.name, url, timeout=10)
            rows = parse_sky_table(response.text, league)
            self._parsed(health, len(rows))
            updated = re.search(r'Last updated:\s*<strong>(.*?)</strong>', response.text, re.S)
            return {'rows': rows, 'source': url, 'publisher_updated': clean(updated.group(1)) if updated else None,
                    'fallback': False, 'errors': errors}
        except (requests.RequestException, ValueError, AttributeError, KeyError) as exc:
            errors.append(f'{url}: {exc}')
        # No invented alternate parser. Last-good cache is the safe fallback
        # until a second table integration has been verified against its HTML.
        raise ValueError('; '.join(errors))
