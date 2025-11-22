"""
Torrent file parser with comprehensive error handling.

Provides the TorrentFile class for parsing bencoded torrent files,
extracting metadata, generating info hashes, and creating magnet links.

Custom exceptions:
- TorrentFileError: Base exception for all torrent file errors
- InvalidTorrentFileError: Raised when file is not valid bencode format
- MissingRequiredKeyError: Raised when required keys are missing
"""

import hashlib
import os
from urllib.parse import urlencode

import bencodepy


class TorrentFileError(Exception):
    """Base exception for torrent file parsing errors."""
    pass


class InvalidTorrentFileError(TorrentFileError):
    """Raised when torrent file is not valid bencode format."""
    pass


class MissingRequiredKeyError(TorrentFileError):
    """Raised when torrent file is missing required keys."""
    pass


class TorrentFile:
    def __init__(self, torrent_path):
        try:
            with open(torrent_path, 'rb') as f:
                file_content = f.read()
        except FileNotFoundError:
            raise TorrentFileError(f"Torrent file not found: {torrent_path}")
        except PermissionError:
            raise TorrentFileError(f"Permission denied reading torrent file: {torrent_path}")
        except Exception as e:
            raise TorrentFileError(f"Failed to read torrent file: {e}")

        # Try to decode bencode
        try:
            torrent_data_raw = bencodepy.decode(file_content)
        except bencodepy.DecodingError as e:
            raise InvalidTorrentFileError(f"Invalid bencode format: {e}")
        except Exception as e:
            raise InvalidTorrentFileError(f"Failed to decode torrent file: {e}")

        # Validate torrent structure
        if not isinstance(torrent_data_raw, dict):
            raise InvalidTorrentFileError("Torrent data is not a dictionary")

        # Check for required 'info' key (can be bytes or string)
        info_key = b'info' if b'info' in torrent_data_raw else 'info'
        if info_key not in torrent_data_raw:
            raise MissingRequiredKeyError("Torrent file missing required 'info' dictionary")

        # Store raw info for hash calculation
        self._raw_info = torrent_data_raw[info_key]

        # Normalize keys: bencodepy returns byte keys, convert to strings for easier access
        self.torrent_data = self._normalize_dict(torrent_data_raw)
        self.info = self.torrent_data['info']

        # Validate info dictionary
        if not isinstance(self.info, dict):
            raise InvalidTorrentFileError("'info' field is not a dictionary")

        # Check for 'files' key
        self.is_multi_file = 'files' in self.info

    def _normalize_dict(self, d):
        """Recursively convert byte keys to strings, preserving byte values needed for hashing."""
        if isinstance(d, dict):
            result = {}
            for k, v in d.items():
                # Convert byte keys to strings
                key = k.decode('utf-8', errors='ignore') if isinstance(k, bytes) else k

                # Recursively normalize nested dicts and lists
                if isinstance(v, dict):
                    value = self._normalize_dict(v)
                elif isinstance(v, list):
                    value = [self._normalize_dict(item) if isinstance(item, dict) else item for item in v]
                elif isinstance(v, bytes) and key not in ['pieces']:  # Don't decode binary data like pieces
                    # Try to decode byte values that look like strings
                    try:
                        value = v.decode('utf-8')
                    except (UnicodeDecodeError, AttributeError):
                        value = v
                else:
                    value = v

                result[key] = value
            return result
        return d

    def files(self):
        if self.is_multi_file:
            return [os.path.join(self.info['name'], *file['path']) for file in self.info['files']]
        else:
            return [self.info['name']]

    def info_hash(self):
        # Use raw info dict to ensure hash is correct (needs original bytes)
        return hashlib.sha1(bencodepy.encode(self._raw_info)).hexdigest().upper()

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
            f.write(bencodepy.encode(self.torrent_data))
