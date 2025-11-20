# FTP Fetch
A simple command line utility that uses FTP to make sure local files match those on a server.  

# Requirements
Python 3.13 or greater.  
The server being connected to must be running GNU/Linux and support the MLSD command.  

# Usage
FTP Fetch uses JSON files in the following format to store the connection data:  
```json
{
    "remote_connection": {
        "host": "https://example.com",
        "user": "username",
        "password": "user password",
        "tls": false,
        "port": 21,
        "timeout": 60
    },
    "remote_root": "",
    "local_root": "/path/to/local/files",
    "blacklist": [
        "dont/include/me"
        "i_shouldnt/be_synced.txt"
    ],
    "whitelist": [
        "only_include_me"
    ]
}
```
`remote_connection` Everything here whould be self explanitory.  
`remote_root` Where to start checking files from on the remote server.  
`local_root` Where to start checking files from on the local machine.  
`blacklist` Files and directories to not include when checking.  
`whitelist` If specified, ONLY these files and directories will be checked.  

Run the program using:  
```bash
python ftp_fetch.py /path/to/connection_info.json
```
**Additional commandline options:**  
`-wl, --whitelist` A comma-seperated list of paths to overwrite the config whitelist with.  
`-bl, --blacklist` A comma-seperated list of paths to overwrite the config blacklist with.  
`-p, --password` Ovewrite the config user password, useful if you don't want to store your FTP passwords in plain text.  
`-nc, --no-confirm` Don't ask for confirmation before applying found changes. The summary will still be writen to summary.txt.  
`-v --verbose` Shows more information about what the program is doing.  

### Notes:  
All the entries are required, but can be emtpy values.  
Blacklist and whitelist paths should be relative to the root directories.  
It doesn't matter whether you include starting or trailing slashes, the program will take care of that for you.  
**For Windows users:**  
All paths MUST use forward-slashes (`/`) NOT back-slashes (`\`).  

# License
This program is licensed under the MIT license.  