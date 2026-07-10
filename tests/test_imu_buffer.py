from threading import Thread

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.camera.imu_buffer import ImuBuffer
from scanner_app.camera.models import ImuSample


def test_pop_through_returns_ordered_samples_and_retains_future_samples() -> None:
    buffer = ImuBuffer()
    buffer.push(ImuSample("gyro", 30, np.ones(3)))
    buffer.push(ImuSample("accel", 10, np.zeros(3)))
    buffer.push(ImuSample("gyro", 20, np.full(3, 2.0)))

    assert [sample.timestamp_us for sample in buffer.pop_through(20)] == [10, 20]
    assert [sample.timestamp_us for sample in buffer.pop_through(40)] == [30]


def test_push_and_pop_are_safe_under_concurrent_writers() -> None:
    buffer = ImuBuffer()

    def push_range(start: int) -> None:
        for timestamp_us in range(start, start + 50):
            buffer.push(ImuSample("gyro", timestamp_us, np.zeros(3)))

    threads = [Thread(target=push_range, args=(start,)) for start in (100, 0, 50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [sample.timestamp_us for sample in buffer.pop_through(149)] == list(range(150))
    assert buffer.pop_through(200) == ()
