"""
Magnet link parsing and reconstruction.

Provides the MagnetLink class for parsing magnet URIs into components
(info hash, name, trackers, size) and reconstructing them. The to_uri()
method preserves the unencoded 'urn:btih:' format required by most
torrent clients including rTorrent.
"""

import re
from urllib.parse import parse_qs, quote
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
        """
        Reconstruct the magnet URI from the parsed data.

        The xt parameter is built manually to avoid encoding colons in
        'urn:btih:' which breaks compatibility with many torrent clients
        including rTorrent.
        """
        # Build xt parameter manually - colons in urn:btih: must NOT be encoded
        parts = [f"xt=urn:btih:{self.info_hash}"]

        if self.name:
            parts.append(f"dn={quote(self.name, safe='')}")

        for tracker in self.trackers:
            parts.append(f"tr={quote(tracker, safe='')}")

        if self.size:
            parts.append(f"xl={self.size}")

        return f"magnet:?{'&'.join(parts)}"

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
        """
        Download torrent metadata from the swarm and save as a .torrent file.

        Uses magnet2torrent module which handles tracker augmentation and the
        libtorrent params.trackers copy issue correctly.
        """
        from magnet2torrent import core as m2t

        output_dir = os.path.dirname(os.path.abspath(path))

        # Get public trackers for better connectivity
        public_trackers = m2t.get_public_trackers(proxy_enabled=False)

        # Create session and process magnet
        ses = m2t.create_session(enable_dht=False)
        try:
            m2t.process_magnet(ses, self.magnet_uri, output_dir, public_trackers)
        finally:
            del ses

        # magnet2torrent saves with the torrent name, we may need to rename
        # Find the generated file and rename if needed
        expected_name = os.path.basename(path)
        generated_files = [f for f in os.listdir(output_dir) if f.endswith('.torrent')]

        # If the file wasn't created with our expected name, find and rename it
        if expected_name not in generated_files and generated_files:
            # Find the most recently created .torrent file
            latest = max(
                [os.path.join(output_dir, f) for f in generated_files],
                key=os.path.getmtime
            )
            if latest != path:
                os.rename(latest, path)