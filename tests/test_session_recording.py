import json
from queue import Full

import numpy as np
import pytest

from scanner_app.camera.models import ImuSample, SynchronizedFramePacket
from scanner_app.recording.session import SessionRecorder, SessionRecordingError, SessionReplay


def _packet(
    *,
    sequence: int = 3,
    imu_samples: tuple[ImuSample, ...] = tuple(),
) -> SynchronizedFramePacket:
    return SynchronizedFramePacket(
        color_bgr=np.arange(12, dtype=np.uint8).reshape(2, 2, 3),
        depth_raw=np.array([[1, 2], [3, 4]], dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=100,
        color_timestamp_us=95,
        imu_samples=imu_samples,
        sequence=sequence,
    )


def test_recorded_packet_replays_without_numeric_loss(tmp_path) -> None:
    packet = _packet()
    recorder = SessionRecorder(tmp_path)
    recorder.submit(packet)
    recorder.close()

    replayed = list(SessionReplay(tmp_path).packets())

    assert len(replayed) == 1
    assert replayed[0].sequence == packet.sequence
    assert replayed[0].depth_scale_mm == packet.depth_scale_mm
    assert replayed[0].depth_timestamp_us == packet.depth_timestamp_us
    assert replayed[0].color_timestamp_us == packet.color_timestamp_us
    np.testing.assert_array_equal(replayed[0].depth_raw, packet.depth_raw)
    np.testing.assert_array_equal(replayed[0].color_bgr, packet.color_bgr)


def test_recorder_writes_metadata_file(tmp_path) -> None:
    metadata = {
        "device_name": "Orbbec Gemini 215",
        "serial_number": "ABC123",
        "capture_config": {"depth_width": 1280, "depth_height": 800},
    }

    recorder = SessionRecorder(tmp_path, metadata=metadata)
    recorder.close()

    assert json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8")) == metadata


def test_recorder_writes_empty_metadata_when_none(tmp_path) -> None:
    recorder = SessionRecorder(tmp_path)
    recorder.close()

    assert json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8")) == {}


def test_replay_restores_imu_samples(tmp_path) -> None:
    imu_samples = (
        ImuSample("gyro", 101, np.array([0.1, 0.2, 0.3], dtype=np.float64)),
        ImuSample("accel", 102, np.array([1.0, 2.0, 3.0], dtype=np.float64)),
    )
    packet = _packet(sequence=7, imu_samples=imu_samples)
    recorder = SessionRecorder(tmp_path)
    recorder.submit(packet)
    recorder.close()

    replayed = list(SessionReplay(tmp_path).packets())

    assert len(replayed) == 1
    assert [sample.sensor for sample in replayed[0].imu_samples] == ["gyro", "accel"]
    assert [sample.timestamp_us for sample in replayed[0].imu_samples] == [101, 102]
    np.testing.assert_array_equal(replayed[0].imu_samples[0].xyz, imu_samples[0].xyz)
    np.testing.assert_array_equal(replayed[0].imu_samples[1].xyz, imu_samples[1].xyz)


def test_submit_raises_recording_error_when_queue_is_full(tmp_path, monkeypatch) -> None:
    recorder = SessionRecorder(tmp_path, queue_size=1)

    def raise_full(_packet: SynchronizedFramePacket) -> None:
        raise Full

    monkeypatch.setattr(recorder._queue, "put_nowait", raise_full)

    with pytest.raises(SessionRecordingError, match="Recorder queue is full"):
        recorder.submit(_packet())

    recorder.close()
