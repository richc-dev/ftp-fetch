# FTP Fetch
A commandline utility to get and update files from a FTP server.

# Requirements
Python 3.13 or greater

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
### Notes:
The whitelist only works with directories, not files.
It doesn't matter whether you include starting or trailing slashes, the program will take care of that for you.

Then run the program with:
```bash
python ftp_fetch.py /path/to/connection_info.json
```

# License
This program is licensed under the MIT license.
