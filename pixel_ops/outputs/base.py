from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image


class DisplayOutput(ABC):
    """Transport boundary for rendered frames.

    The core renderer always produces PIL.Image frames. Output implementations
    decide how those frames reach hardware, files, or streams.
    """

    def start(self) -> None:
        pass

    @abstractmethod
    def send(self, frame: Image.Image) -> None:
        pass

    def stop(self) -> None:
        pass


class CroppedOutput(DisplayOutput):
    """Output wrapper that sends a display-sized crop from a virtual frame."""

    def __init__(self, output: DisplayOutput, box: tuple[int, int, int, int], rotation: int = 0):
        self.output = output
        self.box = box
        self.rotation = rotation if rotation in (0, 90, 180, 270) else 0

    def start(self) -> None:
        self.output.start()

    def send(self, frame: Image.Image) -> None:
        cropped = frame.crop(self.box)
        if self.rotation:
            cropped = cropped.rotate(-self.rotation, expand=True)
        self.output.send(cropped)

    def stop(self) -> None:
        self.output.stop()
