import os
from pathlib import Path
from typing import List

import pandas as pd
import pytest
from estimate_start_times.config import Configuration, ConcurrencyOracleType, ResourceAvailabilityType, \
    HeuristicsThresholds, EventLogIDs
from process_waste.core import core


@pytest.fixture(scope='module')
def assets_path():
    if os.path.basename(os.getcwd()) == 'tests':
        return Path('assets')
    else:
        return Path('tests/assets')


@pytest.fixture
def bimp_example_path(assets_path) -> Path:
    return assets_path / 'BIMP_example.csv'


@pytest.fixture
def cases(assets_path) -> List[pd.DataFrame]:
    cases = [
        pd.read_csv(assets_path / 'bimp-example_case_21.csv'),
        pd.read_csv(assets_path / 'bimp-example_case_272.csv'),
        pd.read_csv(assets_path / 'bimp-example_case_293.csv'),
        pd.read_csv(assets_path / 'bimp-example_case_409.csv'),
        pd.read_csv(assets_path / 'bimp-example_case_444.csv'),
    ]

    def _preprocess(case):
        case['start_timestamp'] = pd.to_datetime(case['start_timestamp'])
        case['time:timestamp'] = pd.to_datetime(case['time:timestamp'])
        return case.sort_values(by='time:timestamp')

    return list(map(_preprocess, cases))


@pytest.fixture
def xes_paths(assets_path) -> List[Path]:
    return [
        assets_path / 'BIMP_example.csv',
        assets_path / 'PurchasingExample.csv',
    ]


@pytest.fixture
def config() -> Configuration:
    config = Configuration(
        log_ids=EventLogIDs(
            case='case:concept:name',
            activity='concept:name',
            start_time='start_timestamp',
            end_time='time:timestamp',
            enabled_time='enabled_timestamp',
            available_time='available_timestamp',
            resource='org:resource',
            lifecycle='lifecycle:transition',
        ),
        concurrency_oracle_type=ConcurrencyOracleType.HEURISTICS,
        resource_availability_type=ResourceAvailabilityType.SIMPLE,
        heuristics_thresholds=HeuristicsThresholds(df=0.9, l2l=0.9)
    )
    return config


@pytest.fixture
def event_log(request, assets_path) -> pd.DataFrame:
    log_path = assets_path / request.node.get_closest_marker('log_path').args[0]
    log = core.read_csv(log_path)

    return log


@pytest.fixture(params=['PurchasingExample.csv', 'Production.csv'])
def event_log_parametrized(request, assets_path) -> pd.DataFrame:
    log_path = assets_path / request.param
    log = pd.read_csv(log_path)

    time_columns = ['start_timestamp', 'time:timestamp']
    for column in time_columns:
        log[column] = pd.to_datetime(log[column], utc=True)

    return log
