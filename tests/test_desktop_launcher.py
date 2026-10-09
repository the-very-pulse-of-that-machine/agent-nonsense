import sys
import unittest
from unittest.mock import patch

from agent_nonsense.desktop.launcher import main


class DesktopLauncherTestCase(unittest.TestCase):
    def test_bundled_server_dispatch_never_starts_a_second_gui(self):
        arguments = ["Doupi", "--doupi-server", "--port", "9898"]
        with patch.object(sys, "argv", arguments), patch("multiprocessing.freeze_support"), patch("agent_nonsense.server.main") as server, patch("agent_nonsense.desktop.main") as gui:
            main()
            server.assert_called_once_with()
            gui.assert_not_called()
            self.assertEqual(sys.argv, ["Doupi", "--port", "9898"])

    def test_selftest_dispatch_returns_failure_without_opening_normal_gui(self):
        with patch.object(sys, "argv", ["Doupi", "--self-test", "report.json"]), patch("multiprocessing.freeze_support"), patch("agent_nonsense.desktop.selftest.run", return_value=1) as check, patch("agent_nonsense.desktop.main") as gui:
            with self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code, 1)
            check.assert_called_once_with("report.json")
            gui.assert_not_called()

    def test_normal_launch_opens_desktop(self):
        with patch.object(sys, "argv", ["Doupi"]), patch("multiprocessing.freeze_support"), patch("agent_nonsense.desktop.main") as gui:
            main()
            gui.assert_called_once_with()
