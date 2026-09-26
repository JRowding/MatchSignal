"""Free fixture providers for the English football pyramid."""
from dataclasses import dataclass
from datetime import datetime, time as datetime_time, timedelta
from html import unescape
import json
import logging
import re
from zoneinfo import ZoneInfo
from time import sleep

import requests

from .normalization import canonical_team
from .config import CONFIG
from .timeutils import utc_text, football_day

LOG = logging.getLogger(__name__)


def fixture_window(now):
    return (
        datetime.combine(now.date(), datetime_time.min),
        datetime.combine(
            now.date() + timedelta(days=CONFIG.fixture_lookahead_days), datetime_time.max
        ),
    )


@dataclass(frozen=True)
class Fixture:
    external_fixture_id: str
    competition: str
    kickoff: str
    home_team: str
    away_team: str
    status: str = "scheduled"


class FixtureProvider:
    def upcoming(self) -> list[Fixture]:
        raise NotImplementedError


class TheSportsDBProvider(FixtureProvider):
    """Multi-source fixture provider covering all five supported tiers."""

    BASE = "https://www.thesportsdb.com/api/v1/json/123/eventsseason.php"
    LEAGUES = {
        "4328": "Premier League",
        "4329": "Championship",
        "4396": "League One",
        "4397": "League Two",
    }
    SKY_COMPETITIONS = {
        "Premier League": "Premier League",
        "EFL Championship": "Championship", "EFL League One": "League One",
        "EFL League Two": "League Two", "National League": "National League",
        "Sky Bet Championship": "Championship",
        "Sky Bet League One": "League One",
        "Sky Bet League Two": "League Two",
    }
    SKY_DAILY_URL = "https://www.skysports.com/football-scores-fixtures/{date}"
    FWP_COMPETITIONS = {
        "Premier League": "premier-league",
        "Championship": "championship",
        "League One": "league-one",
        "League Two": "league-two",
        "National League": "national-league",
    }
    FWP_URL = "https://www.footballwebpages.co.uk/{slug}/fixtures-results"
    REQUIRED_COMPETITIONS = tuple(FWP_COMPETITIONS)

    def __init__(self, session=requests):
        self.session = session
        self.diagnostics = []

    def _get(self, source, scope, url, **kwargs):
        health = {'source': source, 'scope': scope, 'status': 'failed', 'rows': 0}
        self.diagnostics.append(health)
        for attempt in range(CONFIG.source_retries + 1):
            try:
                response = self.session.get(url, **kwargs)
                response.raise_for_status()
                return response, health
            except requests.RequestException as exc:
                health['error'] = str(exc)
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                if attempt == CONFIG.source_retries or (status is not None and status != 429 and status < 500):
                    raise
                sleep(1)

    @staticmethod
    def _parsed(health, rows):
        health.update(status='success' if rows else 'invalid', rows=rows)
        if rows and 'error' in health:
            health['recovered_error'] = health.pop('error')
        if not rows:
            health['error'] = 'No recognizable fixture rows; empty schedule not verified'
            LOG.error('%s %s: %s', health['source'], health['scope'], health['error'])

    def covered_competitions(self):
        # TheSportsDB free season responses can be truncated to five events.
        # A few returned fixtures are not evidence of complete league coverage.
        sky = [d for d in self.diagnostics if d['source'] == 'sky']
        covered = set(self.SKY_COMPETITIONS.values()) if sky and all(d['status'] == 'success' for d in sky) else set()
        for competition in self.REQUIRED_COMPETITIONS:
            rows = [d for d in self.diagnostics if d['source'] == 'fwp' and d['scope'] == competition]
            if rows and all(d['status'] == 'success' for d in rows):
                covered.add(competition)
        return covered

    @staticmethod
    def _dedupe(fixtures: list[Fixture]) -> list[Fixture]:
        seen = set()
        result = []
        for fixture in sorted(fixtures, key=lambda f: f.status == 'scheduled'):
            key = (
                fixture.competition,
                fixture.kickoff,
                fixture.home_team,
                fixture.away_team,
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(fixture)
        return result

    def upcoming(self) -> list[Fixture]:
        now = datetime.now(ZoneInfo('Europe/London')).replace(tzinfo=None)
        window_start, window_end = fixture_window(now)

        # Football Web Pages publishes all five supported English leagues and is
        # the primary source. Sky supplements it, then TheSportsDB is used only
        # for any top-four competition still missing from the requested window.
        fixtures = self._football_web_pages_fixtures(window_start, window_end)
        fixtures.extend(self._sky_fixtures(window_start, window_end))
        fixtures = self._dedupe(fixtures)

        present_competitions = {fixture.competition for fixture in fixtures}
        missing_leagues = {
            league_id: competition
            for league_id, competition in self.LEAGUES.items()
            if competition not in present_competitions and competition not in self.covered_competitions()
        }
        if missing_leagues:
            LOG.warning(
                "Primary fixture sources returned no rows for: %s. Trying TheSportsDB fallback.",
                ", ".join(missing_leagues.values()),
            )
            fixtures.extend(
                self._thesportsdb_fixtures(
                    window_start,
                    window_end,
                    league_ids=missing_leagues,
                )
            )
            fixtures = self._dedupe(fixtures)

        final_competitions = {fixture.competition for fixture in fixtures}
        missing_after_fallback = [
            competition
            for competition in self.REQUIRED_COMPETITIONS
            if competition not in final_competitions
        ]
        if missing_after_fallback:
            LOG.warning(
                "No fixtures found in the current five-day window for: %s",
                ", ".join(missing_after_fallback),
            )

        return fixtures

    def _football_web_pages_fixtures(self, window_start, window_end):
        fixtures = []
        months = {(window_start.year, window_start.month), (window_end.year, window_end.month)}

        for competition, slug in self.FWP_COMPETITIONS.items():
            for year, month in sorted(months):
                try:
                    response, health = self._get(
                        'fwp', competition, self.FWP_URL.format(slug=slug),
                        params={"month": month},
                        timeout=CONFIG.source_timeout_seconds,
                        headers={"User-Agent": "MatchSignal/2.6"},
                    )
                    response.raise_for_status()
                except requests.RequestException as exc:
                    LOG.warning(
                        "Football Web Pages fixtures unavailable for %s %s/%s: %s",
                        competition,
                        month,
                        year,
                        exc,
                    )
                    continue

                rows = []
                # Restrict every extraction to one HTML row. A missing date or
                # status must never borrow fields from the following fixture.
                for row_html in re.findall(r'<tr\b[^>]*>.*?</tr>', response.text, flags=re.DOTALL):
                    match = re.search(
                        r'<tr[^>]+data-href="match/([^\"]+)"[^>]*>.*?'
                        r'<td class="d-none export-only">([^<]+)</td>.*?'
                        r'<td class="status"[^>]*>([^<]+)</td>.*?'
                        r'<td class="team home-team"[^>]*data-export="([^\"]+)".*?'
                        r'<td class="team away-team"[^>]*data-export="([^\"]+)"',
                        row_html, flags=re.DOTALL,
                    )
                    if match:
                        rows.append(match.groups())
                self._parsed(health, len(rows))
                for path, date_text, time_text, home, away in rows:
                    try:
                        kickoff = self._football_web_pages_kickoff(date_text, time_text)
                    except ValueError:
                        continue
                    if not window_start <= kickoff <= window_end:
                        continue
                    fixtures.append(
                        Fixture(
                            f"fwp-{slug}-{path}",
                            competition,
                            utc_text(kickoff, 'Europe/London'),
                            canonical_team(unescape(home)),
                            canonical_team(unescape(away)),
                        )
                    )

        return fixtures

    def _football_web_pages_national_league(self, now, cutoff):
        """Backward-compatible wrapper retained for existing tests/callers."""
        return [
            fixture
            for fixture in self._football_web_pages_fixtures(now, cutoff)
            if fixture.competition == "National League"
        ]

    def _thesportsdb_fixtures(self, window_start, window_end, league_ids=None):
        fixtures = []
        now = datetime.now(ZoneInfo('Europe/London')).replace(tzinfo=None)
        season_start = now.year if now.month >= 7 else now.year - 1
        season = f"{season_start}-{season_start + 1}"
        leagues = league_ids or self.LEAGUES

        for league_id, competition in leagues.items():
            try:
                response, health = self._get(
                    'thesportsdb', competition, self.BASE,
                    params={"id": league_id, "s": season},
                    timeout=CONFIG.source_timeout_seconds,
                    headers={"User-Agent": "MatchSignal/2.6"},
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                LOG.warning("Fixture provider unavailable for %s: %s", competition, exc)
                continue

            try:
                events = response.json()['events']
                if not isinstance(events, list):
                    raise ValueError('Missing events array')
            except (ValueError, KeyError, TypeError) as exc:
                health.update(status='invalid', error=str(exc))
                LOG.error('Invalid TheSportsDB response for %s: %s', competition, exc)
                continue
            self._parsed(health, len(events))
            if len(events) <= 5:
                health.update(status='partial', error='Free season response may be truncated')
            for event in events:
                home = event.get("strHomeTeam")
                away = event.get("strAwayTeam")
                date = event.get("dateEvent")
                time = event.get("strTime")
                if not time or event.get('strStatus') in ('Match Finished', 'Postponed', 'Cancelled', 'Abandoned'):
                    continue
                if not event.get("idEvent") or not home or not away or not date:
                    continue
                try:
                    kickoff_at = datetime.fromisoformat(f"{date}T{time[:8]}")
                except ValueError:
                    continue
                if not window_start <= kickoff_at <= window_end:
                    continue
                fixtures.append(
                    Fixture(
                        str(event["idEvent"]),
                        competition,
                        utc_text(kickoff_at),
                        canonical_team(home),
                        canonical_team(away),
                    )
                )
        return fixtures

    @staticmethod
    def _football_web_pages_kickoff(date_text, time_text):
        match_date = datetime.strptime(date_text.strip(), "%d/%m/%Y")
        text = time_text.strip().lower().replace(".", ":")
        match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", text)
        if not match:
            raise ValueError(f"Unsupported fixture time: {time_text}")
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if match.group(3) == "pm" and hour != 12:
            hour += 12
        if match.group(3) == "am" and hour == 12:
            hour = 0
        return match_date.replace(hour=hour, minute=minute)

    def _sky_fixtures(self, now, cutoff):
        """Sky's dated pages supplement the primary fixture source."""
        fixtures = []
        current = now.date()
        while current <= cutoff.date():
            try:
                response, health = self._get(
                    'sky', current.isoformat(), self.SKY_DAILY_URL.format(date=current.isoformat()),
                    timeout=CONFIG.source_timeout_seconds,
                    headers={"User-Agent": "MatchSignal/2.6"},
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                LOG.warning("Sky fixture page unavailable for %s: %s", current, exc)
                current += timedelta(days=1)
                continue
            parsed_events = 0
            for raw in re.findall(r'data-state="([^"]+)"', response.text):
                try:
                    event = json.loads(unescape(raw))
                    source_competition = event["competition"]["name"]["full"]
                    parsed_events += 1
                    competition = self.SKY_COMPETITIONS.get(source_competition)
                    status = next((state for flag, state in (
                        ('isPostponed', 'postponed'), ('isCancelled', 'cancelled'),
                        ('isAbandoned', 'abandoned'), ('isResult', 'completed')) if event.get(flag)), 'scheduled')
                    if not competition or (status == 'scheduled' and not event.get('isFixture')):
                        continue
                    time = event["start"].get("time")
                    if not time:
                        continue
                    kickoff = datetime.fromisoformat(f"{current.isoformat()}T{time}:00")
                    if not now <= kickoff <= cutoff:
                        continue
                    home = event["teams"]["home"]["name"]["full"]
                    away = event["teams"]["away"]["name"]["full"]
                    fixtures.append(
                        Fixture(
                            f"sky-{event['id']}",
                            competition,
                            utc_text(kickoff, 'Europe/London'),
                            canonical_team(home),
                            canonical_team(away),
                            status,
                        )
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
            self._parsed(health, parsed_events)
            current += timedelta(days=1)
        return fixtures


def upsert_fixtures(connection, fixtures: list[Fixture]) -> int:
    with connection:
        connection.execute('UPDATE fixtures SET status=status WHERE id=-1')
        for fixture in fixtures:
            kickoff = utc_text(fixture.kickoff) if len(fixture.kickoff) > 10 else fixture.kickoff
            existing = connection.execute('''SELECT f.* FROM fixtures f LEFT JOIN fixture_aliases a ON a.fixture_id=f.id
                WHERE f.external_fixture_id=? OR a.external_id=? LIMIT 1''', (fixture.external_fixture_id, fixture.external_fixture_id)).fetchone()
            if existing:
                if (existing['competition'], existing['home_team'], existing['away_team']) != (fixture.competition, fixture.home_team, fixture.away_team):
                    connection.execute("UPDATE fixtures SET status='identity_conflict' WHERE id=?", (existing['id'],))
                    LOG.error('Provider identity changed: %s', fixture.external_fixture_id)
                    continue
                status = 'identity_conflict' if existing['status'] == 'identity_conflict' else fixture.status
                if existing['status'] == 'completed' and status == 'scheduled':
                    status = 'completed'
                connection.execute('UPDATE fixtures SET kickoff=?,status=? WHERE id=?', (kickoff, status, existing['id']))
                continue
            candidates = connection.execute('''SELECT * FROM fixtures WHERE competition=? AND home_team=? AND away_team=?''',
                (fixture.competition, fixture.home_team, fixture.away_team)).fetchall()
            same_day = [r for r in candidates if football_day(r['kickoff']) == football_day(kickoff)]
            if len(same_day) == 1:
                existing = same_day[0]
                connection.execute('INSERT INTO fixture_aliases VALUES(?,?)', (fixture.external_fixture_id, existing['id']))
                if fixture.status in ('postponed', 'cancelled', 'abandoned', 'completed') and existing['status'] != 'identity_conflict':
                    connection.execute('UPDATE fixtures SET status=? WHERE id=?', (fixture.status, existing['id']))
                if existing['kickoff'] != kickoff:
                    # Conflicting sources require review; do not silently move a prediction.
                    connection.execute("UPDATE fixtures SET status='identity_conflict' WHERE id=?", (existing['id'],))
                continue
            if same_day:
                LOG.error('Ambiguous duplicate fixture: %s', fixture.external_fixture_id)
                continue
            connection.execute('''INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status)
                VALUES(?,?,?,?,?,?)''', (fixture.external_fixture_id, fixture.competition, kickoff, fixture.home_team, fixture.away_team, fixture.status))
    return len(fixtures)
