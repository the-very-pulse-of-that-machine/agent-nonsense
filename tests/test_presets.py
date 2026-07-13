import unittest

from agent_nonsense.server import load_presets


class PresetsTestCase(unittest.TestCase):
    def test_presets_have_unique_ids_and_long_scripts(self):
        presets = load_presets()
        ids = [preset["id"] for preset in presets]
        self.assertGreaterEqual(len(presets), 10)
        self.assertEqual(len(ids), len(set(ids)))
        for preset in presets:
            self.assertGreaterEqual(len(preset["steps"]), 10)
            self.assertTrue(preset.get("question"))
            self.assertGreaterEqual(preset.get("compiled_chars", 0), 5000)
            self.assertGreaterEqual(sum(len(step["text"]) for step in preset["steps"]), 5000)
            self.assertTrue(preset.get("closing"))
            for step in preset["steps"]:
                self.assertIn("### 阶段", step["text"])
                self.assertIn("```text", step["text"])
                self.assertIn("- [x]", step["text"])
                self.assertNotIn("剧本", step["text"])
                self.assertIn(step["module"], {"research", "file_ops", "code_edit", "test_run", "debug_trace"})
                if step.get("tool"):
                    self.assertIn(step["tool"], {"list_files", "read_file", "write_file"})


if __name__ == "__main__":
    unittest.main()
