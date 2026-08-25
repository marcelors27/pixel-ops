from unittest import TestCase, mock

from pixel_ops.outputs.turzx_usb import TURZXOutput


class TurzxOutputTests(TestCase):
    def test_serial_selector_ignores_ephemeral_bus_and_address(self):
        output = TURZXOutput.from_config(
            480,
            320,
            {
                "vid": "0x1a86",
                "pid": "0x5722",
                "serial_number": "USB35INCHIPSV2",
                "bus": 2,
                "address": 3,
            },
        )

        with mock.patch("pixel_ops.outputs.turzx_usb.UsbBulkRevA") as backend:
            output.start()

        backend.assert_called_once_with(
            width=480,
            height=320,
            vid=0x1A86,
            pid=0x5722,
            timeout_ms=5000,
            serial_number="USB35INCHIPSV2",
            bus=None,
            address=None,
        )
