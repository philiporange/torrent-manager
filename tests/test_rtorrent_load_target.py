"""Tests for rTorrent load target fallback behavior."""

from unittest.mock import MagicMock, patch
from xmlrpc import client

from torrent_manager.rtorrent_client import RTorrentClient


def make_client():
    with patch('torrent_manager.rtorrent_client.client.ServerProxy') as mock_proxy:
        proxy = MagicMock()
        mock_proxy.return_value = proxy
        instance = RTorrentClient('http://example.com/RPC2', view='main')
    return instance, proxy


def test_load_with_target_fallback_uses_view_before_blank_target():
    rtorrent, proxy = make_client()
    proxy.load.raw_start.side_effect = [0]

    result = rtorrent._load_with_target_fallback('raw_start', b'data')

    assert result == 0
    proxy.load.raw_start.assert_called_once_with('main', b'data')


def test_load_with_target_fallback_retries_blank_target_after_invalid_view():
    rtorrent, proxy = make_client()
    proxy.load.raw_start.side_effect = [client.Fault(-500, 'invalid parameters: invalid target'), 0]

    result = rtorrent._load_with_target_fallback('raw_start', b'data')

    assert result == 0
    assert proxy.load.raw_start.call_args_list[0].args == ('main', b'data')
    assert proxy.load.raw_start.call_args_list[1].args == ('', b'data')
