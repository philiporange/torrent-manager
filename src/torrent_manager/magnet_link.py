import re
from urllib.parse import parse_qs, urlencode
import tempfile
import time
import os


class MagnetLink:
    def __init__(self, magnet_uri):
        self.magnet_uri = magnet_uri
        self.parse_magnet_uri()

    def parse_magnet_uri(self):
        # Extract parameters from the magnet URI
        params = parse_qs(self.magnet_uri.split('?', 1)[1])
        
        self.info_hash = params.get('xt', [None])[0]
        if self.info_hash:
            self.info_hash = self.info_hash.split(':')[-1].lower()
        
        self.info_hash = self.info_hash.upper()
        
        self.name = params.get('dn', [None])[0]
        self.trackers = params.get('tr', [])
        self.size = int(params.get('xl', [0])[0])

    def to_uri(self):
        # Reconstruct the magnet URI from the parsed data
        params = {
            'xt': f'urn:btih:{self.info_hash}',
            'dn': self.name,
            'tr': self.trackers,
        }
        if self.size:
            params['xl'] = str(self.size)
        return f"magnet:?{urlencode(params, doseq=True)}"

    def info_hash(self):
        return self.info_hash

    def name(self):
        return self.name

    def size(self):
        return self.size

    def trackers(self):
        return self.trackers

    def add_tracker(self, tracker):
        if tracker not in self.trackers:
            self.trackers.append(tracker)

    def remove_tracker(self, tracker):
        if tracker in self.trackers:
            self.trackers.remove(tracker)

    @staticmethod
    def from_torrent_file(torrent_file):
        # Create a magnet link from a TorrentFile object
        info_hash = torrent_file.info_hash()
        name = torrent_file.info['name']
        trackers = torrent_file.trackers()
        size = torrent_file.size()

        params = {
            'xt': f'urn:btih:{info_hash}',
            'dn': name,
            'tr': trackers,
            'xl': str(size)
        }
        return MagnetLink(f"magnet:?{urlencode(params, doseq=True)}")

    @staticmethod
    def is_valid_magnet(magnet_uri):
        # Basic validation of a magnet URI
        pattern = r'^magnet:\?xt=urn:btih:[a-fA-F0-9]{40}.*$'
        return re.match(pattern, magnet_uri) is not None

    def download_torrent(self, path):
        import libtorrent as lt
        temp_dir = tempfile.gettempdir()

        ses = lt.session()
        params = {
            'save_path': temp_dir,
            'storage_mode': lt.storage_mode_t(2),
        }
        
        handle = lt.add_magnet_uri(ses, self.magnet_uri, params)
        while not handle.has_metadata():
            time.sleep(1)

        # Save the torrent file
        torrent_info = handle.get_torrent_info()
        filename = os.path.basename(path)
        save_path = os.path.join(temp_dir, filename)
        with open(save_path, 'wb') as f:
            f.write(lt.bencode(torrent_info.generate()))

        # Delete the handle
        ses.remove_torrent(handle)

        # Move the torrent file to the specified path
        os.rename(save_path, path)
        os.rmdir(temp_dir)