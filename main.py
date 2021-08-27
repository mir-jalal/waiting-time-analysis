import pandas as pd
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.util import interval_lifecycle
from pm4py.statistics.concurrent_activities.pandas import get as concurrent_activities_get

log = xes_importer.apply('data/PurchasingExampleModified.xes')
log_interval = interval_lifecycle.to_interval(log)
event_log_interval = log_converter.apply(log_interval, variant=log_converter.Variants.TO_DATA_FRAME)


# Transportation: Hand-off
# Metrics:
# - frequency
# - duration
# - score = frequency * duration
def calculate_handoff_per_case(case: pd.DataFrame) -> pd.DataFrame:
    case = case.sort_values(by='time:timestamp')

    # Processing concurrent activities
    params = {
        concurrent_activities_get.Parameters.TIMESTAMP_KEY: "time:timestamp",
        concurrent_activities_get.Parameters.START_TIMESTAMP_KEY: "start_timestamp"
    }
    concurrent_activities = concurrent_activities_get.apply(case, parameters=params)
    case_without_concurrent_activities = case.copy()
    for activities_pair in concurrent_activities:
        concurrent = case[(case['Activity'] == activities_pair[0]) | (case['Activity'] == activities_pair[1])]
        case_without_concurrent_activities.drop(concurrent.index, inplace=True)
        if concurrent.iloc[0]['time:timestamp'] >= concurrent.iloc[1]['time:timestamp']:
            print(f"Adding \"{concurrent.iloc[0]['Activity']}\", dropping \"{concurrent.iloc[1]['Activity']}\"")
            case_without_concurrent_activities = case_without_concurrent_activities.append(concurrent.iloc[0])
        else:
            print(f"Adding \"{concurrent.iloc[1]['Activity']}\", dropping \"{concurrent.iloc[0]['Activity']}\"")
            case_without_concurrent_activities = case_without_concurrent_activities.append(concurrent.iloc[1])
    case_without_concurrent_activities.sort_values(by='start_timestamp', inplace=True)
    case_without_concurrent_activities.reset_index(drop=True, inplace=True)

    # Handoff Identification
    case_processed = case_without_concurrent_activities
    resource_changed = case_processed['Resource'] != case_processed.shift(-1)['Resource']
    activity_changed = case_processed['Activity'] != case_processed.shift(-1)['Activity']
    handoff_occurred = resource_changed & activity_changed  # both conditions must be satisfied
    handoff = pd.DataFrame(
        columns=['source_activity', 'source_resource', 'destination_activity', 'destination_resource', 'duration'])
    handoff.loc[:, 'source_activity'] = case_processed[handoff_occurred]['Activity']
    handoff.loc[:, 'source_resource'] = case_processed[handoff_occurred]['Resource']
    handoff.loc[:, 'destination_activity'] = case_processed[handoff_occurred].shift(-1)['Activity']
    handoff.loc[:, 'destination_resource'] = case_processed[handoff_occurred].shift(-1)['Resource']
    handoff['duration'] = case_processed[handoff_occurred].shift(-1)['start_timestamp'] - \
                          case_processed[handoff_occurred]['time:timestamp']
    # dropping an event at the end which is always 'True'
    handoff.drop(handoff.tail(1).index, inplace=True)

    # Frequency
    handoff_per_case = pd.DataFrame(
        columns=['source_activity', 'source_resource', 'destination_activity', 'destination_resource', 'duration'])
    grouped = handoff.groupby(by=['source_activity', 'source_resource', 'destination_activity', 'destination_resource'])
    for group in grouped:
        pair, records = group
        handoff_per_case = handoff_per_case.append(pd.Series({
            'source_activity': pair[0],
            'source_resource': pair[1],
            'destination_activity': pair[2],
            'destination_resource': pair[3],
            'duration': records['duration'].sum(),
            'frequency': len(records)
        }), ignore_index=True)

    return handoff_per_case


event_log_interval_by_case = event_log_interval.groupby(by='case:concept:name')
for (case_id, case) in event_log_interval_by_case:
    if case_id not in ['10']:
        continue
    print(case_id)
    result = calculate_handoff_per_case(case)
    print(result)

# DONE: Sequential events
#   - identical dates
#   - parallel gateways (enabled timestamp)
#   - modify event log to create a parallel or overlapping activity by time

# DONE: Handoff types, can we discover resources, calendars (identify human, system, internal or external resource)?
# We can't discover, but we can label it manually.

# DONE: Separate dataframe for metrics

# NOTE: Requirements:
#   - only interval event logs, i.e., event logs where each event has a start timestamp and a completion timestamp

# TODO: Ping-pong handoff is not identified yet

# TODO: CTE, processing time / full time
#   - Do we count only business hours? Yes. Using 24 hours for PurchasingExample.xes
# TODO: Add total handoff frequency, frequency per case using unique pairs source+resource
# TODO: Mark manually some events with resource_type label "system" to add handoff type identification
