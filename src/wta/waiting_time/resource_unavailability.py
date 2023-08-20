import datetime
from typing import List, Optional

import pandas as pd
from wta import log_ids_non_nil, EventLogIDs
from wta.calendars import calendars
from wta.calendars.calendars import UNDIFFERENTIATED_RESOURCE_POOL_KEY
from wta.calendars.intervals import pd_interval_to_interval, Interval, subtract_intervals


def other_processing_events_during_waiting_time_of_event(
        event_index: pd.Index,
        log: pd.DataFrame,
        log_ids: Optional[EventLogIDs] = None) -> pd.DataFrame:
    """
    Returns a dataframe with all other processing events that are in the waiting time of the given event, i.e.,
    activities that have been started before event_start_time but after event_enabled_time.

    :param event_index: Index of the event for which the waiting time is taken into account.
    :param log: Log dataframe.
    :param log_ids: Event log IDs.
    """
    log_ids = log_ids_non_nil(log_ids)

    event = log.loc[event_index]
    if isinstance(event, pd.Series):
        event = event.to_frame().T

    # current event variables
    event_start_time = event[log_ids.start_time].values[0]
    event_start_time = pd.to_datetime(event_start_time, utc=True)
    event_enabled_time = event[log_ids.enabled_time].values[0]
    event_enabled_time = pd.to_datetime(event_enabled_time, utc=True)
    resource = event[log_ids.resource].values[0]

    # resource events throughout the event log except the current event
    resource_events = log[log[log_ids.resource] == resource]
    resource_events = resource_events.loc[resource_events.index.difference(event_index)]

    # taking activities that resource started before event_start_time but after event_enabled_time
    other_processing_events = resource_events[
        (resource_events[log_ids.start_time] < event_start_time) &
        (resource_events[log_ids.end_time] > event_enabled_time)]

    return other_processing_events


def non_processing_intervals(
        event_index: pd.Index,
        log: pd.DataFrame,
        log_ids: Optional[EventLogIDs] = None) -> List[Interval]:
    """
    Returns a list of intervals during which no processing has taken place.

    :param event_index: Index of the event for which the waiting time is taken into account.
    :param log: Log dataframe.
    :param log_ids: Event log IDs.
    """
    log_ids = log_ids_non_nil(log_ids)

    event = log.loc[event_index]
    if isinstance(event, pd.Series):
        event = event.to_frame().T

    # current event variables
    event_start_time = event[log_ids.start_time].values[0]
    event_start_time = pd.to_datetime(event_start_time, utc=True)
    event_enabled_time = event[log_ids.enabled_time].values[0]
    event_enabled_time = pd.to_datetime(event_enabled_time, utc=True)
    wt_interval = pd.Interval(event_enabled_time, event_start_time)
    wt_interval = pd_interval_to_interval(wt_interval)

    other_processing_events = other_processing_events_during_waiting_time_of_event(event_index, log, log_ids=log_ids)
    if len(other_processing_events) == 0:
        return wt_interval

    other_processing_events_intervals = []
    for (_, event) in other_processing_events.iterrows():
        pd_interval = pd.Interval(event[log_ids.start_time], event[log_ids.end_time])
        interval = pd_interval_to_interval(pd_interval)
        other_processing_events_intervals.extend(interval)

    result = subtract_intervals(wt_interval, other_processing_events_intervals)

    return result


def detect_unavailability_intervals(
        event_index: pd.Index,
        log: pd.DataFrame,
        log_calendar: dict,
        differentiated=True,
        log_ids: Optional[EventLogIDs] = None) -> List[Interval]:

    log_ids = log_ids_non_nil(log_ids)
    event = log.loc[event_index]

    if isinstance(event, pd.Series):
        event = event.to_frame().T

    if differentiated:
        resource = event[log_ids.resource].values[0]
    else:
        resource = UNDIFFERENTIATED_RESOURCE_POOL_KEY

    start_time = pd.Timestamp(event[log_ids.start_time].values[0])
    enabled_time = pd.Timestamp(event[log_ids.enabled_time].values[0])
    start_time = __ensure_timestamp_tz(start_time, enabled_time.tz)
    enabled_time = __ensure_timestamp_tz(enabled_time, start_time.tz)

    non_working_intervals = []
    if enabled_time < start_time:
        overall_work_intervals = calendars.resource_working_hours_as_intervals(resource, log_calendar)
        current_instant = enabled_time
        while current_instant < start_time:
            daily_working_intervals = [
                interval
                for interval in overall_work_intervals
                if current_instant.weekday() == interval.left_day.value
            ]

            next_instant = None
            for working_interval in daily_working_intervals:
                start = working_interval._left_time
                end = working_interval._right_time
                if start <= current_instant.time() < end:
                    next_instant = pd.Timestamp.combine(current_instant.date(), end).tz_localize(current_instant.tz)
                    break

            if next_instant is None:
                starts_after = [
                    working_interval._left_time
                    for working_interval in daily_working_intervals
                    if working_interval._left_time > current_instant.time()
                ]
                if starts_after:
                    min_start_after = min(starts_after)
                    next_instant = pd.Timestamp.combine(current_instant.date(), min_start_after).tz_localize(current_instant.tz)
                    non_working_intervals.append(pd.Interval(current_instant, min(next_instant, start_time)))

            if next_instant is None:
                next_instant = pd.Timestamp.combine(
                    current_instant.date() + pd.Timedelta(days=1),
                    datetime.time.fromisoformat("00:00:00.000000")
                ).tz_localize(current_instant.tz)
                non_working_intervals.append(pd.Interval(current_instant, min(next_instant, start_time)))

            current_instant = next_instant

    return non_working_intervals



def __ensure_timestamp_tz(timestamp: pd.Timestamp, tz: Optional[str] = None):
    if not timestamp.tz:
        tz = tz if tz else 'UTC'
        timestamp = timestamp.tz_localize(tz)

    return timestamp
