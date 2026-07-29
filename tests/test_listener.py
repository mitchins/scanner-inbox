import importlib.util
import pathlib
import sys
import unittest
from datetime import datetime, timezone


MODULE_PATH = pathlib.Path(__file__).parents[1] / "src" / "es60w_listener.py"
SPEC = importlib.util.spec_from_file_location("es60w_listener", MODULE_PATH)
assert SPEC and SPEC.loader
LISTENER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LISTENER
SPEC.loader.exec_module(LISTENER)


class ListenerConfigurationTest(unittest.TestCase):
    def test_button_marker_is_specific(self) -> None:
        self.assertEqual(
            LISTENER.EVENT_MARKER, b"service:NetScanMonitor-agent"
        )

    def test_defaults_preserve_proven_lab_configuration(self) -> None:
        settings = LISTENER.Settings.from_env({})
        self.assertEqual(settings.scanner_ip, "192.168.6.134")
        self.assertEqual(settings.local_ip, "0.0.0.0")
        self.assertEqual(
            settings.sane_device, "epsonds:net:192.168.6.134"
        )
        self.assertEqual(
            settings.raw_scan, pathlib.Path("/opt/es60w-lab/output")
        )
        self.assertEqual(settings.output_format, "png")

    def test_environment_overrides_runtime_configuration(self) -> None:
        settings = LISTENER.Settings.from_env(
            {
                "ES60W_SCANNER_IP": "10.1.2.3",
                "ES60W_LOCAL_IP": "10.1.2.4",
                "ES60W_EVENT_PORT": "9999",
                "ES60W_OUTPUT_FORMAT": "tiff",
                "ES60W_LOG_FILE": "",
                "ES60W_RESOLUTION": "200",
                "RAW_SCAN": "/data/raw",
            }
        )
        self.assertEqual(settings.scanner_ip, "10.1.2.3")
        self.assertEqual(settings.local_ip, "10.1.2.4")
        self.assertEqual(settings.event_port, 9999)
        self.assertEqual(settings.sane_device, "epsonds:net:10.1.2.3")
        self.assertEqual(settings.raw_scan, pathlib.Path("/data/raw"))
        self.assertIsNone(settings.log_file)
        self.assertEqual(settings.output_format, "tiff")
        self.assertEqual(settings.resolution, 200)

    def test_output_name_contract(self) -> None:
        settings = LISTENER.Settings.from_env(
            {"RAW_SCAN": "/data/raw", "ES60W_OUTPUT_FORMAT": "tiff"}
        )
        when = datetime(2026, 7, 29, 12, 34, 56, tzinfo=timezone.utc)
        path = LISTENER.output_path(settings, when)
        self.assertEqual(
            path,
            pathlib.Path("/data/raw/2026-07-29_12-34-56_ES-60W.tiff"),
        )

    def test_scan_command_uses_settings(self) -> None:
        settings = LISTENER.Settings.from_env(
            {
                "ES60W_SCANNER_IP": "10.1.2.3",
                "ES60W_RESOLUTION": "200",
                "ES60W_SCAN_MODE": "Gray",
            }
        )
        command = LISTENER.scan_command(settings)
        self.assertEqual(command[0], "/usr/bin/scanimage")
        self.assertIn("epsonds:net:10.1.2.3", command)
        self.assertIn("200", command)
        self.assertIn("Gray", command)

    def test_raw_scan_must_be_absolute(self) -> None:
        with self.assertRaisesRegex(ValueError, "RAW_SCAN must be"):
            LISTENER.Settings.from_env({"RAW_SCAN": "relative/path"})

    def test_event_group_must_be_multicast(self) -> None:
        with self.assertRaisesRegex(ValueError, "multicast"):
            LISTENER.Settings.from_env({"ES60W_EVENT_GROUP": "10.1.2.3"})


if __name__ == "__main__":
    unittest.main()
