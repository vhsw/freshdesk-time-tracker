# Freshdesk timer
Simple time tracker for Freshdesk, Jira and Teamwork.

## Installation
Just place timer.py in any convenient place on your device. Also, you may want to add alias in your bash or zsh profile.
```
alias latime="~/timer.py"
```

You also need to install Python 3.7 or greater and AIOHTTP module to run this script.
```
sudo apt install python3.7
pip3 install aiohttp pytz
```

By default, this script looking for config in user's home directory, so put config.ini to home directory and add replace parameters by you're own.
You also can specify config location like this:
```
timer.py -c /path/to/config.ini
```
## Usage
To get time report for the current date just run script without any args:

```
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

Total tracked time:    03:05
- Freshdesk billable:  00:50
- Freshdesk free:      02:50
- Teamwork billable:   00:00
- Teamwork free:       00:00
- Jira:                00:15

Progress:
[###########________________________________]

Untracked time: 04:55
```

To get time report for any other day you must specify offset argument e.g., for yesterday it will be 
```
timer.py 1
```

and for the day before yesterday and so on
```
timer.py 2
```

Also, you can specify the exact date DD.MM.YYYY (you can change date format in config) for time report like this:
```
timer.py 14.09.2018
```

And you can get total spent time report for single Freshdesk ticket using -ft and ticket number:
```
timer.py -ft 27974
```
