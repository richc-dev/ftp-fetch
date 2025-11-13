# Name       : FTP Fetch
# Description: A commandline utility to get and update files
#              from a FTP server.
# Author     : Richie C.
# Version    : 1.0.0
# License    : MIT

import argparse
import copy
#import cryptography
from datetime import datetime
import ftplib
import json
import os
import sys
import time

class ConnectionInfo:
    def __init__(
        self,
        host: str,
        user: str,
        pswd: str = '',
        tls: bool = False,
        port: int = 21,
        timeout: int = 60
    ):
        self.host = host
        self.user = user
        self.pswd = pswd
        self.tls = tls
        self.port = port
        self.timeout = timeout

class FileInfo:
    def __init__(
        self,
        path: str,
        name: str,
        m_date: int = 0,
        size: int = 0,
        is_dir: bool = False
    ):
        self.path = path
        self.name = name
        self.m_date = m_date
        self.size = int(size)
        self.is_dir = is_dir

class SyncInfo:
    def __init__(
        self,
        remote_root: str = '',
        local_root: str = '',
        blacklist: list = [],
        whitelist: list = [],
    ):
        self.remote_root = remote_root
        self.local_root = local_root
        self.blacklist = blacklist
        self.whitelist = whitelist

def connect(con_info: ConnectionInfo, remote_root: str)->ftplib.FTP:
    """
    Connects to the FTP server.

    Arguments:
        con_info: a ConnectionInfo object

    Returns:
        A ftplib.FTP object connected to the server.
    """
    ftp: ftplib.FTP = ftplib.FTP_TLS() if (con_info.tls) else ftplib.FTP()
    ftp.set_debuglevel(0)
    print(f'Connecting to {con_info.host} on port {con_info.port}...')

    try:
        ftp.connect(con_info.host, con_info.port, con_info.timeout)
        print('Connection successful!')
    except:
        print('Connection Failed!\nPlease make sure your settings are correct and the server is running.')
        sys.exit()

    print(f'Logging in as {con_info.user} with the provided password...')
    try:
        ftp.login(con_info.user, con_info.pswd)
        print('Login successful!')
    except:
        print('Login failed!\nPlease make sure the login details are correct.')
        sys.exit()

    if con_info.tls:
        ftp.prot_p()

    try:
        ftp.cwd(remote_root)
    except:
        print(f'The directory `{remote_root}` doesn\'t exist on the server!')
        sys.exit()

    return ftp

def load_connection_json(path: str)->tuple:
    """
    Loads the connection settings

    Arguments:
        path: a string containing the json settings file path

    Returns:
        A ConnectionInfo object containing the specified settings
    """
    try:
        if path.rsplit('.', 1)[1] != 'json':
            print('File is not of type: JSON')
            raise Exception()
        f = open(path, 'r')
        data = json.load(f)
    except:
        print(f'Failed to open file: {path}')
        sys.exit()
    finally:
        if 'f' in locals():
            f.close()

    rc_data = data['remote_connection']
    return (
        ConnectionInfo(
            rc_data['host'],
            rc_data['user'],
            rc_data['password'],
            rc_data['tls'],
            rc_data['port'],
            rc_data['timeout'],
        ),
        SyncInfo(
            data['remote_root'],
            data['local_root'] if data['local_root'][-1] != '/' else data['local_root'].rsplit('/', 1)[0],
            [('' if entry[:1] == '/' else '/') + entry + ('/' if entry[-1] == '/' else '')
             for entry in data['blacklist']],
            [('' if entry[:1] == '/' else '/') + entry + ('/' if entry[-1] == '/' else '')
             for entry in data['whitelist']]
        )
    )

def get_remote_files(ftp: ftplib.FTP, sync_info: SyncInfo)->dict[str, FileInfo]:
    files: dict[str, FileInfo] = {}
    scan_list: list = ['']

    if sync_info.whitelist:
        scan_list = []
        # Only add whitelist entries if they exist.
        for d in sync_info.whitelist:
            try:
                ftp.cwd(d)
            except:
                print(f"WARNING: {d} doesn't exist on the remote server!")
                continue
            files[d] = FileInfo(d, d.rsplit('/', 1)[1], 0, 0, True)
            scan_list.append(d)
            # Return to the root directory.
            ftp.cwd('/')

    for d in scan_list:
        # Set the working directory.
        ftp.cwd(d)

        dir_files = ftp.mlsd(d, facts=['size', 'modify', 'type'])
        for f in dir_files:
            f_path: str = f"{d}/{f[0]}"
            f_info: dict = f[1]

            # Skip the entry if it's not a normal file or directory
            # or blacklisted.
            if (f_info['type'] not in {'file', 'dir'}) or (f_path in sync_info.blacklist):
                continue
            # If the entry is a directory, add it to the scan list.
            f_is_dir: bool = False
            if ('dir' == f_info['type']):
                scan_list.append(f_path)
                f_is_dir = True

            m_time = time.mktime(datetime.strptime(str(f_info['modify']), '%Y%m%d%H%M%S').timetuple())
            files[f_path] = FileInfo(f_path, f[0], m_time, f_info.get('size', 0), f_is_dir)
    # Return to the root directory.
    ftp.cwd('/')
    return files

def get_local_files(sync_info: SyncInfo)->dict[str, FileInfo]:
    files: dict[str, FileInfo] = {}
    scan_list: list = [sync_info.local_root]

    if sync_info.whitelist:
        scan_list = []
        # Only add whitelist entries if the exist.
        for d in scan_list:
            if os.path.exists(d):
                files[d] = FileInfo(d.replace(sync_info.local_root, ''), d.rsplit('/', 1)[1], 0, 0, True)
                scan_list.append(d)
        
    for d in scan_list:
        results = os.scandir(d)

        for entry in results:
            rel_path = entry.path.replace(sync_info.local_root, '')
            # Ignore blacklisted paths.
            if rel_path in sync_info.blacklist:
                continue

            # We only want files and directories.
            if not entry.is_file() and not entry.is_dir():
                continue

            is_dir: bool = False
            if entry.is_dir():
                is_dir = True
                scan_list.append(entry.path)

            stat = entry.stat(follow_symlinks=False)
            files[rel_path] = FileInfo(rel_path, entry.name, stat.st_mtime, stat.st_size, is_dir)
    return files

def sort_by_dir_level(x):
    return x.count('/')

def format_list_to_str(l: list)->str:
    output: str = ""
    for i in l:
        output += f"\n{i}"
    return output

def sync(args)->None:
    info = load_connection_json(args.connection_json)
    con_info: ConnectionInfo = info[0]
    sync_info: SyncInfo = info[1]
    ftp: ftplib.FTP = connect(con_info, sync_info.remote_root)

    # Apply any commandline overrides
    if args.blacklist:
        sync.blacklist = args.blacklist.split(',')
    if args.whitelist:
        sync.whitelist = args.whitelist.split(',')

    r_files: dict[str, FileInfo] = get_remote_files(ftp, sync_info)
    l_files: dict[str, FileInfo] = get_local_files(sync_info)
    
    f_to_down: dict[str, int] = {}
    f_to_del: list[str] = []
    d_to_down: list[str] = []
    d_to_del: list[str] = []

    if r_files:
        # Loop through all the remote files and set any
        # files that only exist on the remote server or
        # that are newer than local ones to be downloaded.
        for key in copy.deepcopy(r_files):
            # Get the local file data
            f: SyncInfo = r_files[key]
            # Get the equivelent local file (if it exists) and remove
            # it from the local files list.
            l_file: SyncInfo|None = l_files.pop(key, None)
            # If the file/directory doesn't exist locally,
            # add it to the download list.
            if l_file is None:
                if f.is_dir:
                    d_to_down.append(key)
                else:
                    f_to_down[key] = f.m_date
                continue

            # Skip directories beacuse modified date doesn't matter for them.
            if l_file.is_dir:
                continue

            # Download if there is a size or last-modified date difference between
            # the local and remote files.
            if f.size != l_file.size or f.m_date != l_file.m_date:
                f_to_down[key] = f.m_date
            else:
                r_files.pop(key)

    # Delete any local files that don't exist on the remote server.
    for f in l_files:
        # The block checking if files need to be downloaded should
        # have removed all entries that exist in both locations, so
        # we can just mark any remaining local entries for deletion
        if l_files[f].is_dir:
            d_to_del.append(f)
        else:
            f_to_del.append(f)

    if not f_to_down and not f_to_del and not d_to_down and not d_to_del:
        print("Everything is up to date!")
        sys.exit()

    # Sort all the lists by how deep they are in the file structure.
    # This prevents the program from attempting to download files or
    # directories into paths that don't exist.
    f_to_down = dict(sorted(f_to_down.items(), key=lambda x: x[0].count('/')))
    d_to_down.sort(key=sort_by_dir_level)
    d_to_del.sort(key=sort_by_dir_level)
    f_to_del.sort(key=sort_by_dir_level)

    # Output the summary to a text file and ask for confirmation
    # before doing anything with the files.
    summary: str = "--- == Downloads == ---"
    summary += format_list_to_str(d_to_down)
    summary += format_list_to_str(f_to_down)
    summary += "\n--- == Deletions == ---"
    summary += format_list_to_str(f_to_del)
    summary += format_list_to_str(d_to_del)
    
    with open("summary.txt", "w") as f:
        f.write(summary)

    # Ask for confirmation if the --no-confirm flag isn't set.
    if not args.no_confirm:
        print("Would you like to apply the changes in summary.txt? (y)es/(n)o")
        if input().lower() not in {'y', 'yes'}:
            print("Sync canceled")
            sys.exit()

    # Delete marked files...
    for f in f_to_del:
        path = sync_info.local_root + f
        try:
            os.remove(path)
        except:
            print(f"Error deleting file: {path}")

    # Delete marked directories...
    for d in d_to_del:
        path = sync_info.local_root + d
        try:
            os.rmdir(path)
        except:
            print(f"Error deleting directory: {path}")

    # Create marked directories...
    for d in d_to_down:
        path = sync_info.local_root + d
        try:
            os.mkdir(path)
        except:
            print(f"Error creating directory: {path}")

    # Download marked files...
    for f in f_to_down:
        path = sync_info.local_root + f
        r_path = sync_info.remote_root + f

        try:
            # Download the file
            with open(path, 'wb') as open_file:
                ftp.retrbinary(f"RETR {r_path}", open_file.write)
            os.utime(path, (os.stat(path).st_atime, int(f_to_down[f])))
        except:
            print(f"Error downloading: {path}")

    ftp.quit()
    print("Sync finished")

# Parser for command line args
parser = argparse.ArgumentParser(prog='ftp_fetch')
parser.add_argument('connection_json', metavar='connection-json', type=str, help='path to the connection info json file')
parser.add_argument('-wl', '--whitelist', type=str, default='none', help='overwrite the config whitelist, should be a comma seperated list')
parser.add_argument('-bl', '--blacklist', type=str, default='none', help='overwrite the config blacklist, should be a comma seperated list')
parser.add_argument('-dk', '--decrypt-key', type=str, default='none', help='key to decrypt the password field')
parser.add_argument('-nc', '--no-confirm', action='store_true', help='skip the preview changes step')
parser.set_defaults(func=sync )

args = parser.parse_args()
if hasattr(args, 'func'):
    args.func(args)
