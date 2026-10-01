import unittest
from unittest.mock import MagicMock, patch

import booklet_store


class TestBookletStore(unittest.TestCase):
    def test_cloud_listing_includes_records_after_first_page(self):
        storage = MagicMock()
        first_page = [{"name": f"{number:032x}.json"} for number in range(100)]
        storage.list.side_effect = [first_page, [{"name": f"{100:032x}.json"}]]

        with patch.object(booklet_store, "_bucket", return_value=storage):
            uids = booklet_store.list_uids("theory")

        self.assertEqual(len(uids), 101)
        self.assertEqual(uids[-1], f"{100:032x}")
        self.assertEqual(storage.list.call_args_list[1].args[1]["offset"], 100)

    def test_invalid_record_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid booklet cloud identifier"):
            booklet_store._path("theory", "../other")


if __name__ == "__main__":
    unittest.main()
