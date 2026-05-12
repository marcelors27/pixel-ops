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
