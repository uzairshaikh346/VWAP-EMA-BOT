"""
Automated Economic News Filter for Institutional MT5 Scalper (XAUUSD).
Fetches high-impact economic news events (ForexFactory economic calendar)
and shields the trading bot from high-slippage spikes and spread widening.

Rules:
1. High-Impact USD Events (NFP, CPI, FOMC, Fed Speeches, Core PCE, PPI).
2. Freezes trading 15 minutes before the event and 15 minutes after.
3. Automatically caches weekly events so trading continues even if offline.
"""

import time
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, Optional


class EconomicNewsFilter:
    def __init__(
        self,
        target_currencies: Optional[List[str]] = None,
        freeze_before_mins: int = 15,
        freeze_after_mins: int = 15,
        cache_refresh_hours: int = 4
    ):
        self.target_currencies = [c.upper() for c in (target_currencies or ["USD"])]
        self.freeze_before_mins = freeze_before_mins
        self.freeze_after_mins = freeze_after_mins
        self.cache_refresh_hours = cache_refresh_hours

        self.last_fetch_time: float = 0.0
        self.cached_high_impact_events: List[Dict] = []
        self.calendar_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def fetch_calendar_events(self) -> bool:
        """
        Fetches the current week's economic calendar from ForexFactory's JSON feed.
        Parses high-impact USD events.
        """
        now = time.time()
        # Avoid refetching if fetched recently (within cache_refresh_hours)
        if self.cached_high_impact_events and (now - self.last_fetch_time) < (self.cache_refresh_hours * 3600):
            return True

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Institutional-Trading-Bot/1.0"
        }

        try:
            req = urllib.request.Request(self.calendar_url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status == 200:
                    raw_data = response.read().decode('utf-8')
                    events = json.loads(raw_data)

                    high_impact = []
                    for ev in events:
                        currency = ev.get("country", "").upper()
                        impact = ev.get("impact", "").strip().title()

                        if currency in self.target_currencies and impact in ["High", "Holiday"]:
                            # Parse event date: e.g. "2026-09-04T08:30:00-04:00"
                            dt_str = ev.get("date", "")
                            try:
                                # Parse ISO format
                                event_dt = datetime.fromisoformat(dt_str)
                                # Convert to UTC
                                event_utc = event_dt.astimezone(timezone.utc)
                                high_impact.append({
                                    "title": ev.get("title", "High Impact Event"),
                                    "country": currency,
                                    "impact": impact,
                                    "time_utc": event_utc,
                                    "timestamp": int(event_utc.timestamp())
                                })
                            except Exception:
                                continue

                    self.cached_high_impact_events = high_impact
                    self.last_fetch_time = now
                    return True
        except Exception as e:
            # If network error, preserve existing cache gracefully
            return len(self.cached_high_impact_events) > 0

        return False

    def is_news_freeze_active(self, current_dt_utc: Optional[datetime] = None) -> Tuple[bool, str, Optional[Dict]]:
        """
        Checks if the current UTC time falls within the freeze window of any high-impact event.
        Returns: (is_frozen, reason_string, event_info_dict_or_None)
        """
        now_dt = current_dt_utc or datetime.now(timezone.utc)
        now_ts = int(now_dt.timestamp())

        # Ensure calendar data is populated
        if not self.cached_high_impact_events and (time.time() - self.last_fetch_time) > 60:
            self.fetch_calendar_events()
        elif (time.time() - self.last_fetch_time) > (self.cache_refresh_hours * 3600):
            self.fetch_calendar_events()

        if not self.cached_high_impact_events:
            return False, "No active high-impact events loaded", None

        freeze_before_secs = self.freeze_before_mins * 60
        freeze_after_secs = self.freeze_after_mins * 60

        for ev in self.cached_high_impact_events:
            ev_ts = ev["timestamp"]
            diff_secs = ev_ts - now_ts

            # Case 1: News is upcoming within freeze_before_mins (e.g. 15 mins before)
            if 0 <= diff_secs <= freeze_before_secs:
                mins_left = int(diff_secs / 60)
                reason = (
                    f"🚨 [HIGH IMPACT NEWS] Upcoming '{ev['title']}' ({ev['country']}) in {mins_left}m! "
                    f"Trading FROZEN to avoid volatility spikes."
                )
                return True, reason, ev

            # Case 2: News just occurred within freeze_after_mins (e.g. 15 mins after)
            if 0 < (now_ts - ev_ts) <= freeze_after_secs:
                mins_passed = int((now_ts - ev_ts) / 60)
                reason = (
                    f"⚠️ [HIGH IMPACT NEWS] '{ev['title']}' occurred {mins_passed}m ago. "
                    f"Cooldown active ({self.freeze_after_mins - mins_passed}m left) for spreads to normalize."
                )
                return True, reason, ev

        return False, "No upcoming high-impact news in freeze window", None

    def get_next_upcoming_event(self, current_dt_utc: Optional[datetime] = None) -> Optional[Dict]:
        """Returns the next upcoming high-impact event."""
        now_dt = current_dt_utc or datetime.now(timezone.utc)
        now_ts = int(now_dt.timestamp())

        future_events = [ev for ev in self.cached_high_impact_events if ev["timestamp"] > now_ts]
        if future_events:
            future_events.sort(key=lambda x: x["timestamp"])
            return future_events[0]
        return None
