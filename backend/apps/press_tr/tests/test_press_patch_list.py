"""Check the format of the Press patch list."""

import unittest
from pathlib import Path

PATCH_LIST = Path(__file__).resolve().parents[1] / "press_tr" / "patches.txt"


class PressPatchListTest(unittest.TestCase):
	def test_patch_list_ends_with_a_newline(self):
		self.assertTrue(PATCH_LIST.read_bytes().endswith(b"\n"))
