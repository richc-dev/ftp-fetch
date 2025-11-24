# Name       : FTP Fetch
# Description: A commandline utility to get and update files
#              from a FTP server.
# Author     : Richie C.
# Version    : 1.0.0
# License    : MIT

# Copyright (c) 2025 Richie C.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
# USE OR OTHER DEALINGS IN THE SOFTWARE.

import argparse
import copy
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
        m_date: int = 0,
        size: int = 0,
        is_dir: bool = False
    ):
        self.path = path
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

def is_windows()->bool:
    """ Check if the current system is Windows. """
    return True if os.name == 'nt' else False

def get_dir_level(path: str)->int:
    """ 
    Get how many directories deep the path is
    based on how many slashes are in it.
    """
    return path.count('/')

def write_summary(text: str)->None:
    """ Write text to summary.txt. """
    with open("summary.txt", "w") as f:
        f.write(text)
        f.close()

def format_list_to_str(l: list)->str:
    """ Output each list item on a new line. """
    output: str = ""
    for i in l:
        output += f"\n{i}"
    return output

def standardize_slashes(path: str, beginning_slash: bool = True)->str:
    """
    Makes sure `path`s first character is a slash and the last one isn't a slash.

    Arguments:
        path: A string with the path to check.
        beginning_slash: A boolean indicating if the beginning slash should be
            added or not. Exists so a slash doesn't get added before the drive
            letter on Windows.

    Return:
        A string containing the modified path.
    """
    if not path:
        return ''
    if beginning_slash:
        path = ('' if path[:1] == '/' else '/') + path
    return path.rsplit('/', 1)[0] if path[-1] == '/' else path

def generate_fileinfo_for_remote_files(sync_info: SyncInfo, parent_path: str, mlsd_info: list, v: bool = False)->tuple|None:
    """
    Creates a FileInfo object for remote files.

    Args:
        sync_info: A SyncInfo object.
        parent_path: A string containing the parent directory of the current path.
        mlsd_info: A list with the results of the MSLD command.
        v: A bool indicating if more info should be outputed to the console.
    
    Returns:
        None if the path doesn't exist or is blacklisted, otherwise returns a tuple
        where the first element is the path relative to the root directory and the
        second element is a FileInfo object.
    """
    path: str = f"{parent_path}/{mlsd_info[0]}"
    # Remote the root path since the local and remote roots are usually different.
    rel_path: str = path.replace(sync_info.remote_root, '')
    f_info: dict = mlsd_info[1]

    # Return None if the entry is not a normal file or directory or if it's blacklisted.
    if (f_info['type'] not in {'file', 'dir'}) or (rel_path in sync_info.blacklist):
        return None

    if v: print(f"Found: {rel_path}")
    is_dir: bool = True if 'dir' == f_info['type'] else False

    # Find the modified date.
    m_date = time.mktime(datetime.strptime(str(f_info['modify']), '%Y%m%d%H%M%S').timetuple())
    # Return a filled out FileInfo object.
    return (rel_path, FileInfo(path, m_date, f_info.get('size', 0), is_dir))

def load_connection_settings(args)->tuple:
    """
    Loads the connection settings.

    Arguments:
        args: Arguments from the command line.

    Returns:
        A tuple where the first element is a ConnectionInfo object and
        the second is a SyncInfo object, both are filled with the relavant
        settings specified in the commandline and config file.
    """
    path: str = args.connection_json
    try:
        # Make sure the file is a json file.
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

    # Apply commandline overrides for the whitelist and blacklist.
    if args.blacklist:
        blacklist = [standardize_slashes(entry) for entry in args.blacklist.split(',')]
    else:
        blacklist = [standardize_slashes(entry) for entry in data['blacklist']]

    if args.whitelist:
        whitelist = [standardize_slashes(entry) for entry in args.whitelist.split(',')]
    else:
        whitelist = [standardize_slashes(entry) for entry in data['whitelist']]

    rc_data = data['remote_connection']
    return (
        ConnectionInfo(
            rc_data['host'],
            rc_data['user'],
            args.password or rc_data['password'],
            rc_data['tls'],
            rc_data['port'],
            rc_data['timeout'],
        ),
        SyncInfo(
            standardize_slashes(data['remote_root']),
            standardize_slashes(data['local_root'], not is_windows()),
            blacklist,
            whitelist
        )
    )

def connect(con_info: ConnectionInfo)->ftplib.FTP:
    """
    Connects to the FTP server.

    Arguments:
        con_info: A ConnectionInfo object.

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

    return ftp

def get_remote_files(ftp: ftplib.FTP, sync_info: SyncInfo, v: bool)->dict[str, FileInfo]:
    """
    Gets a list of all files on the remote server that exist in whitelisted paths.

    Arguments:
        ftp: A ftplib.FTP object connected to the remote server.
        sync_info: A SyncInfo object.
        v: A boolean indicating whether or not to display additional information.

    Returns:
        dict[str, FileInfo] A dictionary with the file path as the key and a FileInfo object
        as the entry.
    """
    files: dict[str, FileInfo] = {}
    scan_list: list = [sync_info.remote_root]
    print('Getting remote files...')

    if sync_info.whitelist:
        scan_list = []
        # Only add whitelist entries if they exist.
        for d in sync_info.whitelist:
            path: str = sync_info.remote_root + d
            split_path: list = path.rsplit('/', 1)
            try:
                # Get the children of the parent directory.
                parent_path_children = ftp.mlsd(split_path[0], facts=['size', 'modify', 'type'])
            except:
                print(f"WARNING: {path} doesn't exist on the remote server!")
                continue
            # Check if the whitelisted path exists.
            for f in parent_path_children:
                if f[0] != split_path[1]:
                    continue

                file_info = generate_fileinfo_for_remote_files(sync_info, split_path[0], f, False)
                if not file_info:
                    continue
                # Add the entry to the scan list if it's a directory.
                if file_info[1].is_dir:
                    scan_list.append(path)
                # Add whitelist entry to the file list.
                files[file_info[0]] = file_info[1]

    for d in scan_list:
        if v: print(f"Changing directory to: {d}")

        # Get the files in the directory.
        dir_files = ftp.mlsd(d, facts=['size', 'modify', 'type'])
        for f in dir_files:
            file_info = generate_fileinfo_for_remote_files(sync_info, d, f, v)
            if not file_info:
                continue
            # Add the entry to the scan list if it's a directory.
            if file_info[1].is_dir:
                scan_list.append(file_info[1].path)
            # Add entry to the file list.
            files[file_info[0]] = file_info[1]
            
            
            f_path: str = f"{d}/{f[0]}"
            # Remove the root path since the local and remote roots are (nearly) always different.
            rel_path: str = f_path.replace(sync_info.remote_root, '')
            f_info: dict = f[1]

            # Skip the entry if it's not a normal file or directory or if it's blacklisted.
            if (f_info['type'] not in {'file', 'dir'}) or (rel_path in sync_info.blacklist):
                continue

            if v: print(f"Found: {rel_path}")
            # If the entry is a directory, add it to the scan list.
            f_is_dir: bool = False
            if ('dir' == f_info['type']):
                scan_list.append(f_path)
                f_is_dir = True

            # Get the modified date.
            m_time = time.mktime(datetime.strptime(str(f_info['modify']), '%Y%m%d%H%M%S').timetuple())
            # Add the file to the file list.
            files[rel_path] = FileInfo(f_path, m_time, f_info.get('size', 0), f_is_dir)
    # Return to the root directory.
    ftp.cwd(sync_info.remote_root)
    
    return files

def get_local_files(sync_info: SyncInfo, v: bool = False)->dict[str, FileInfo]:
    """
    Gets a list of all local files that exist in whitelisted paths.

    Arguments:
        sync_info: A SyncInfo object
        is_win: A boolean indicating whether or not the program is running on a Windows machine.
        v: A boolean indicating whether or not to display additional information.

    Returns:
        dict[str, FileInfo] A dictionary with the file path as the key and a FileInfo object
        as the entry.
    """
    files: dict[str, FileInfo] = {}
    scan_list: list = [sync_info.local_root]
    print("Getting local files...")

    if sync_info.whitelist:
        scan_list = []
        # Only add whitelist entries if they exist.
        for d in sync_info.whitelist:
            path = sync_info.local_root + d
            if os.path.exists(path):
                # Check if the path leads to a directory.
                is_dir = os.path.isdir(path)
                files[d] = FileInfo(d, os.path.getmtime(path), os.path.getsize(path), is_dir)
                # If the path is a directory, add it to the scan list.
                if is_dir: scan_list.append(path)
        
    for d in scan_list:
        if v: print(f"Changing directory to: {d}")
        # Get files in the directory being scanned.
        results = os.scandir(d)

        for entry in results:
            # Remove the local root and backslashes (for Windows) so the path matches the remote one.
            rel_path = entry.path.replace(sync_info.local_root, '').replace('\\', '/')
            # Ignore blacklisted paths.
            if rel_path in sync_info.blacklist:
                continue

            # We only want files and directories.
            if not entry.is_file() and not entry.is_dir():
                continue

            if v: print(f"Found: {rel_path}")
            # Add directories to the scan list.
            is_dir: bool = False
            if entry.is_dir():
                is_dir = True
                scan_list.append(entry.path)

            # Get the file info.
            stat = entry.stat(follow_symlinks=False)
            # Add the file info to the file list.
            files[rel_path] = FileInfo(entry.path, stat.st_mtime, stat.st_size, is_dir)
    return files

def sync(args)->None:
    v: bool = args.verbose
    # Load settings from the passed json file and arguments.
    info = load_connection_settings(args)
    con_info: ConnectionInfo = info[0]
    sync_info: SyncInfo = info[1]
    ftp: ftplib.FTP = connect(con_info)

    # Get the remote and local files to be compared.
    r_files: dict[str, FileInfo] = get_remote_files(ftp, sync_info, v)
    l_files: dict[str, FileInfo] = get_local_files(sync_info, v)

    # These lists contain files belonging to each
    # operation.
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
            # the local and remote file.
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

    # No need to continue if no operations need to be done.
    if not f_to_down and not f_to_del and not d_to_down and not d_to_del:
        print("Everything is up to date!")
        write_summary("No changes")
        sys.exit()

    # Sort all list items by how deep they are in the file structure.
    # This prevents the program from attempting to download files or
    # directories into paths that don't exist.
    f_to_down = dict(sorted(f_to_down.items(), key=lambda x: x[0].count('/')))
    d_to_down.sort(key=get_dir_level)
    d_to_del.sort(key=get_dir_level)
    f_to_del.sort(key=get_dir_level)

    # Output the summary to a text file and ask for confirmation
    # before doing anything with the files.
    down_total: int = len(f_to_down) + len(d_to_down)
    summary: str = f"Downloads: {down_total}   Deletions: {len(f_to_del) + len(d_to_del)}\n"
    summary += "--- == Downloads == ---"
    summary += format_list_to_str(d_to_down)
    summary += format_list_to_str(f_to_down)
    summary += "\n--- == Deletions == ---"
    summary += format_list_to_str(f_to_del)
    summary += format_list_to_str(d_to_del)

    write_summary(summary)

    # Ask for confirmation if the --no-confirm flag isn't set.
    if not args.no_confirm:
        print("Would you like to apply the changes in summary.txt? (y)es/(n)o")
        if input().lower() not in {'y', 'yes'}:
            print("Sync canceled")
            sys.exit()

    if v: print("Deleting marked files and directories...")
    # Delete marked files...
    for f in f_to_del:
        path = sync_info.local_root + f
        try:
            os.remove(path)
            if v: print(f"Deleted file: {path}")
        except:
            print(f"Error deleting file: {path}")

    # Delete marked directories...
    for d in d_to_del:
        path = sync_info.local_root + d
        try:
            os.rmdir(path)
            if v: print(f"Deleted dir: {path}")
        except:
            print(f"Error deleting directory: {path}")

    i: int = 1
    # Create marked directories...
    for d in d_to_down:
        path = sync_info.local_root + d
        try:
            os.mkdir(path)
            if v: print(f"\rCreated dir: {path}")
        except:
            print(f"\rError creating directory: {path}")
        
        print(f"\rDownloading file {i} of {down_total}", end='', flush=True)
        i += 1

    # Download marked files...
    for f in f_to_down:
        path = sync_info.local_root + f
        r_path = r_files[f].path
        try:
            # Download the file
            with open(path, 'wb') as open_file:
                ftp.retrbinary(f"RETR {r_path}", open_file.write)
            # Set the last modified date to match the remote file.
            os.utime(path, (os.stat(path).st_atime, int(f_to_down[f])))
            if v: print(f"\nDownloaded file: {path}")
        except:
            print(f"\nError downloading: {r_path}")
        print(f"\rDownloading file {i} of {down_total}", end='', flush=True)
        i += 1

    ftp.quit()
    print("\nSync finished")

# Parser for command line args
parser = argparse.ArgumentParser(prog='ftp_fetch')
parser.add_argument('connection_json', metavar='connection-json', type=str, help='path to the connection info json file')
parser.add_argument('-wl', '--whitelist', type=str, default=None, help='overwrite the config whitelist, should be a comma seperated list')
parser.add_argument('-bl', '--blacklist', type=str, default=None, help='overwrite the config blacklist, should be a comma seperated list')
parser.add_argument('-p', '--password', type=str, default=None, help='overwrite the user password in the config')
parser.add_argument('-nc', '--no-confirm', action='store_true', help='skip the preview changes step')
parser.add_argument('-v', '--verbose', action='store_true', help='display more info about what the program is doing')
parser.set_defaults(func=sync)

args = parser.parse_args()
if hasattr(args, 'func'):
    args.func(args)
