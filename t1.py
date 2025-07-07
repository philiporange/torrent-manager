import json
import sys
import time

from src.torrent_manager.docker_rtorrent import DockerRTorrent
from src.torrent_manager.rtorrent_client import RTorrentClient
from src.torrent_manager.magnet_link import MagnetLink



def test():
    client = RTorrentClient()
    version = client.system.client_version()
    print(f"Connected to rTorrent: {version}")

    print("Erasing all torrents")
    #client.erase_all()
    print("All torrents erased")
  

    magnet_link = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fbig-buck-bunny.torrent"
    ml = MagnetLink(magnet_link)
    print(ml.info_hash)

    client.add_magnet(magnet_link)

    #client.stop_all()
    
    torrents = list(client.list_torrents(files=True))
    for torrent in torrents:
        print(json.dumps(torrent, indent=4))

    torrent = torrents[0]
    
    # Only download the first file
    info_hash = torrent['info_hash']
    client.set_priority(info_hash, 0)
    client.set_file_priority(info_hash, 0, 1)
    exit()

    client.add_torrent("assets/debian-12.6.0-amd64-netinst.iso.torrent")
    print("Torrent added")

    start = time.time()
    torrents = list(client.list_torrents(files=True))
    duration = time.time() - start
    print(f"Listed {len(torrents)} torrents in {duration:.6f} seconds")
    for torrent in torrents:
        print(json.dumps(torrent, indent=4))

def main():
    args = sys.argv[1:]
    
    if 'start' in args:
        docker = DockerRTorrent()
        docker.start()
        print(docker.get_container_ip())
    
    if 'stop' in args:
        docker = DockerRTorrent()
        docker.stop()
        
    if 'test' in args:
        test()
        

if __name__ == '__main__':
    main()
    