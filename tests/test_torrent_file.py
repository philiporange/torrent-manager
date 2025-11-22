import unittest
import os
from urllib.parse import unquote

from torrent_manager.torrent_file import TorrentFile


class TestTorrentFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.torrent_path = "assets/debian-12.6.0-amd64-netinst.iso.torrent"
        cls.torrent_file = TorrentFile(cls.torrent_path)

    def test_file_existence(self):
        self.assertTrue(os.path.exists(self.torrent_path), "Test torrent file does not exist")

    def test_init(self):
        self.assertIsInstance(self.torrent_file, TorrentFile)
        self.assertIn('info', self.torrent_file.torrent_data)

    def test_is_multi_file(self):
        self.assertFalse(self.torrent_file.is_multi_file)

    def test_files(self):
        files = self.torrent_file.files()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0], "debian-12.6.0-amd64-netinst.iso")

    def test_info_hash(self):
        info_hash = self.torrent_file.info_hash()
        self.assertEqual(len(info_hash), 40)  # SHA1 hash is 40 characters long
        self.assertTrue(all(c in '0123456789abcdef' for c in info_hash))

    def test_size(self):
        size = self.torrent_file.size()
        self.assertEqual(size, 661651456)

    def test_piece_length(self):
        piece_length = self.torrent_file.piece_length()
        self.assertEqual(piece_length, 262144)  # 256 KB

    def test_num_pieces(self):
        num_pieces = self.torrent_file.num_pieces()
        self.assertEqual(num_pieces, 2524)

    def test_piece_hash(self):
        first_piece_hash = self.torrent_file.piece_hash(0)
        self.assertEqual(len(first_piece_hash), 40)
        self.assertTrue(all(c in '0123456789abcdef' for c in first_piece_hash))

    def test_trackers(self):
        trackers = self.torrent_file.trackers()
        expected_trackers = [
            'http://bttracker.debian.org:6969/announce',
        ]
        for tracker in expected_trackers:
            self.assertIn(tracker, trackers)

    def test_metadata(self):
        metadata = self.torrent_file.metadata()
        self.assertIn('creation date', metadata)
        self.assertIn('comment', metadata)

    def test_magnet_link(self):
        magnet_link = self.torrent_file.magnet_link()
        magnet_link = unquote(magnet_link)

        self.assertTrue(magnet_link.startswith('magnet:?'))
        self.assertIn('xt=urn:btih:', magnet_link)
        self.assertIn('dn=debian-12.6.0-amd64-netinst.iso', magnet_link)

    def test_validate(self):
        self.assertTrue(self.torrent_file.validate())

    def test_save(self):
        temp_path = "temp_test_torrent.torrent"
        self.torrent_file.save(temp_path)
        self.assertTrue(os.path.exists(temp_path))
        
        # Clean up
        os.remove(temp_path)


if __name__ == '__main__':
    unittest.main()