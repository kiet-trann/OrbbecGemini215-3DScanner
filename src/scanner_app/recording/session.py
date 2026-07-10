from __future__ import annotations

import json
from pathlib import Path
from queue import Full, Queue
from threading import Thread
from typing import Any

import numpy as np

from scanner_app.camera.models import ImuSample, SynchronizedFramePacket


_SENTINEL = object()


class SessionRecordingError(RuntimeError):
    """Raised when a scan session cannot be recorded without data loss."""


class SessionRecorder:
    def __init__(
        self,
        root: Path,
        *,
        metadata: dict[str, Any] | None = None,
        queue_size: int = 64,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._queue: Queue[SynchronizedFramePacket | object] = Queue(maxsize=queue_size)
        self._worker_error: BaseException | None = None
        self._closed = False

        metadata_payload = metadata if metadata is not None else {}
        (self.root / "metadata.json").write_text(
            json.dumps(metadata_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        self._worker = Thread(target=self._run, name="session-recorder", daemon=True)
        self._worker.start()

    def submit(self, packet: SynchronizedFramePacket) -> None:
        if self._closed:
            raise SessionRecordingError("Recorder is closed")
        if self._worker_error is not None:
            raise SessionRecordingError("Recorder worker failed") from self._worker_error

        try:
            self._queue.put_nowait(_copy_packet(packet))
        except Full as exc:
            raise SessionRecordingError("Recorder queue is full") from exc

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        self._queue.put(_SENTINEL)
        self._worker.join()

        if self._worker_error is not None:
            raise SessionRecordingError("Recorder worker failed") from self._worker_error

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SENTINEL:
                    return
                self._write_packet(item)
            except BaseException as exc:
                self._worker_error = exc
                return
            finally:
                self._queue.task_done()

    def _write_packet(self, packet: SynchronizedFramePacket) -> None:
        np.savez_compressed(
            self.root / f"packet_{packet.sequence:08d}.npz",
            color_bgr=packet.color_bgr,
            depth_raw=packet.depth_raw,
            depth_scale_mm=np.asarray(packet.depth_scale_mm, dtype=np.float64),
            depth_timestamp_us=np.asarray(packet.depth_timestamp_us, dtype=np.int64),
            color_timestamp_us=np.asarray(packet.color_timestamp_us, dtype=np.int64),
            sequence=np.asarray(packet.sequence, dtype=np.int64),
            imu_sensor=np.asarray([sample.sensor for sample in packet.imu_samples]),
            imu_timestamp_us=np.asarray(
                [sample.timestamp_us for sample in packet.imu_samples],
                dtype=np.int64,
            ),
            imu_xyz=np.asarray(
                [sample.xyz for sample in packet.imu_samples],
                dtype=np.float64,
            ).reshape(-1, 3),
        )


class SessionReplay:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def packets(self):
        for path in sorted(self.root.glob("packet_*.npz")):
            with np.load(path) as payload:
                imu_samples = tuple(
                    ImuSample(str(sensor), int(timestamp_us), xyz.copy())
                    for sensor, timestamp_us, xyz in zip(
                        payload["imu_sensor"],
                        payload["imu_timestamp_us"],
                        payload["imu_xyz"],
                    )
                )
                yield SynchronizedFramePacket(
                    color_bgr=payload["color_bgr"].copy(),
                    depth_raw=payload["depth_raw"].copy(),
                    depth_scale_mm=float(payload["depth_scale_mm"].item()),
                    depth_timestamp_us=int(payload["depth_timestamp_us"].item()),
                    color_timestamp_us=int(payload["color_timestamp_us"].item()),
                    imu_samples=imu_samples,
                    sequence=int(payload["sequence"].item()),
                )


def _copy_packet(packet: SynchronizedFramePacket) -> SynchronizedFramePacket:
    return SynchronizedFramePacket(
        color_bgr=packet.color_bgr.copy(),
        depth_raw=packet.depth_raw.copy(),
        depth_scale_mm=float(packet.depth_scale_mm),
        depth_timestamp_us=int(packet.depth_timestamp_us),
        color_timestamp_us=int(packet.color_timestamp_us),
        imu_samples=tuple(
            ImuSample(sample.sensor, int(sample.timestamp_us), sample.xyz.copy())
            for sample in packet.imu_samples
        ),
        sequence=int(packet.sequence),
    )
