# Freshdesk timer
Simple time tracker for Freshdesk, Jira and Teamwork.

## Installation
Just place timer.py in any convenient place on your device. 

You also need to install Python 3.7 or greater to run this script. For Debian/Ubuntu:
```bash
sudo apt install python3.7
```
For Mac OS:
```bash
brew install python3.7
```
Then install required modules:
```bash
python3.7 -m pip install aiohttp pytz keyring
```

By default, this script looking for config in user's home directory (`~/timer.conf`), 
if no config found, this script will offer you to create one. 

You also can specify config location like this:
```bash
timer.py -c /path/to/config.ini
```
## Usage
To get time report for the current date just run script without any args:

```bash
timer.py
```

Example of script output:
```
Time records for Wed 12 Sep 2018

https://company.freshdesk.com/a/tickets/27525
    Free: 02:00 Some comment
https://company.freshdesk.com/a/tickets/23111
    Free: 00:50 BUGFIX
https://company.freshdesk.com/a/tickets/12345
    Bill: 00:30
https://company.freshdesk.com/a/tickets/34112
    Bill: 00:20 Not a bug
https://company.freshdesk.com/a/tickets/27968
    Free: 00:25 STUDY 
https://company.freshdesk.com/a/tickets/27974
    Bill: 00:05
https://jira.example.com/browse/DEV-141
    Free: 00:15 standup

Total tracked time:  03:05
    Freshdesk bill:  00:50
    Freshdesk free:  02:50
    Teamwork  bill:  00:00
    Teamwork  free:  00:00
    Jira      free:  00:15

Progress:
[###########________________________________]

Untracked time: 04:55
```

To get time report for any other day you must specify offset argument e.g., for yesterday it will be `timer.py 1`, and for the day before yesterday `timer.py 2` and so on.


Also, you can specify the exact date DD.MM.YYYY (you can change date format in config) for time report like this:
```bash
timer.py 14.09.2018
```

And you can get total spent time report for single Freshdesk ticket using -ft and ticket number:
```bash
timer.py -t 27974
```

Also, you may want to add alias in your bash or zsh profile.
```bash
alias latime="~/timer.py"
```