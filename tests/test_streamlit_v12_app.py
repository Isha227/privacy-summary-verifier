from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "streamlit_v12_app.py"


class PrototypeSmokeTest(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=60)

    def test_opp_explorer_and_taxonomy_mapping_render(self):
        self.app.session_state["pv_view"] = "OPP-115 explorer"
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertTrue(any("OPP-115 evidence explorer" in block.value for block in self.app.markdown))

        mapping_app = AppTest.from_file(str(APP), default_timeout=60)
        mapping_app.session_state["pv_view"] = "Taxonomy mapping"
        mapping_app.run()
        self.assertFalse(mapping_app.exception)
        self.assertTrue(any("OPP taxonomy mapping" in block.value for block in mapping_app.markdown))


if __name__ == "__main__":
    unittest.main()
