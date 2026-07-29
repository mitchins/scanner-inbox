import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "src" / "es60w_listener.py"
SPEC = importlib.util.spec_from_file_location("es60w_listener", MODULE_PATH)
assert SPEC and SPEC.loader
LISTENER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LISTENER)


class ListenerConstantsTest(unittest.TestCase):
    def test_button_marker_is_specific(self) -> None:
        self.assertEqual(
            LISTENER.EVENT_MARKER, b"service:NetScanMonitor-agent"
        )

    def test_output_name_contract(self) -> None:
        path = LISTENER.output_path()
        self.assertEqual(path.parent, LISTENER.OUTPUT_DIR)
        self.assertTrue(path.name.endswith("_ES-60W.png"))


if __name__ == "__main__":
    unittest.main()
