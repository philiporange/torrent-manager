import hashlib
import os
from urllib.parse import urlencode

import bencode


class TorrentFile:
    def __init__(self, torrent_path):
        with open(torrent_path, 'rb') as f:
            self.torrent_data = bencode.bdecode(f.read())
        self.info = self.torrent_data['info']
        self.is_multi_file = 'files' in self.info

    def files(self):
        if self.is_multi_file:
            return [os.path.join(self.info['name'], *file['path']) for file in self.info['files']]
        else:
            return [self.info['name']]

    def info_hash(self):
        return hashlib.sha1(bencode.bencode(self.info)).hexdigest().upper()

    def size(self):
        if self.is_multi_file:
            return sum(file['length'] for file in self.info['files'])
        else:
            return self.info['length']

    def sizes(self):
        if self.is_multi_file:
            return [file['length'] for file in self.info['files']]
        else:
            return [self.info['length']]

    def piece_length(self):
        return self.info['piece length']

    def num_pieces(self):
        return len(self.info['pieces']) // 20

    def piece_hash(self, piece_index):
        return self.info['pieces'][piece_index*20:(piece_index+1)*20].hex()

    def trackers(self):
        if 'announce-list' in self.torrent_data:
            return [tracker for tier in self.torrent_data['announce-list'] for tracker in tier]
        elif 'announce' in self.torrent_data:
            return [self.torrent_data['announce']]
        else:
            return []

    def metadata(self):
        data = {}
        for key in ['creation date', 'comment', 'created by']:
            if key in self.torrent_data:
                data[key] = self.torrent_data[key]
        return data

    def magnet_link(self):
        params = {
            'xt': f"urn:btih:{self.info_hash()}",
            'dn': self.info['name'],
        }
        for i, tracker in enumerate(self.trackers()):
            params[f'tr.{i}'] = tracker
        return f"magnet:?{urlencode(params)}"

    def validate(self):
        # Top-level keys
        required_keys = ['info', 'announce']
        for key in required_keys:
            if key not in self.torrent_data:
                raise ValueError(f"Missing required key: {key}")
        
        return True

    def save(self, path):
        with open(path, 'wb') as f:
            f.write(bencode.bencode(self.torrent_data))
