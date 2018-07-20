#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import configparser
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime, date, timedelta as td

import requests
import urllib3
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth


@dataclass(order=True)
class Time(object):
    seconds: float = field(compare=True, default=0.0)

    @classmethod
    def from_string(cls, string):
        seconds = float(string[:2]) * 3600.0 + float(string[3:]) * 60.0
        return Time(seconds)

    @classmethod
    def from_params(cls, hours=0, minutes=0, seconds=0):
        seconds = hours * 3600 + minutes * 60 + seconds
        return Time(seconds)

    def __format__(self, t_format=None):
        if not t_format:
            t_format = '''{sign}{day}{hour:02}:{minute:02}'''
        negative = self.seconds < 0
        total_seconds = round(abs(self.seconds))

        m_sec = 60
        h_sec = 60 * m_sec
        d_sec = 24 * h_sec

        day = total_seconds // d_sec
        total_seconds -= day * d_sec

        hour = total_seconds // h_sec
        total_seconds -= hour * h_sec

        minute = total_seconds // m_sec
        total_seconds -= minute * m_sec

        second = total_seconds

        repr_str = t_format.format(sign='-' if negative else '',
                                   day=f'{day} day ' if day > 0 else '',
                                   hour=hour,
                                   minute=minute,
                                   second=second)
        return repr_str

    def __repr__(self):
        return self.__format__('''{sign}{day}{hour:02}:{minute:02}''')

    def __add__(self, other):
        if other == 0:
            return self
        return Time(self.seconds + other.seconds)

    def __radd__(self, other):
        if type(other) is int:
            return self
        else:
            return self.__add__(other)

    def __sub__(self, other):
        return self.__add__(Time(-other.seconds))


class TerminalColor:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


@dataclass
class Entry(object):
    id: int
    billable: bool
    spent: Time
    note: str = ''


@dataclass
class TicketingSystem(object):
    config: configparser.RawConfigParser
    report_date: datetime
    auth: tuple = field(init=False)
    params: dict = field(init=False)
    url: str = field(init=False)
    api_url: str = field(init=False)
    entries: list = field(init=False)
    entry_url: str = field(init=False)
    max_retries: int = field(init=False, default=5)
    timeout: int = field(init=False, default=5)

    # def __init__(self, config, report_date):
    #     self.config = config
    #     self.report_date = report_date
    #     self.auth = None
    #     self.params = None
    #     self.url = None
    #     self.api_url = None
    #     self.max_retries = 5
    #     self.timeout = 3
    #     self.entries = []
    #     self.entry_url = None

    def __repr__(self):
        res = []

        if not self.entries:
            return ''

        for entry in self.entries:
            res.append(
                f'''{self.entry_url}{entry.id}'''
                f'''\n\t{'Bill' if entry.billable else 'Free'}: {entry.spent} {entry.note}''')
        return '\n'.join(res)

    def prepare_url(self):
        raise (Exception, 'Not implemented')

    def get_json(self):
        try:
            s = requests.Session()
            s.mount('https://', HTTPAdapter(max_retries=self.max_retries))
            ans = s.get(self.api_url, params=self.params, auth=self.auth, timeout=self.timeout)
        except urllib3.exceptions.ConnectTimeoutError:
            print('Connection timeout...')
            return None
        return ans.json()

    def parse_json(self):
        raise (Exception, 'Not implemented')

    def get_bill(self):
        time = Time(sum(i.spent.seconds for i in self.entries if i.billable))
        return time

    def get_free(self):
        time = Time(sum(i.spent.seconds for i in self.entries if not i.billable))
        return time

    def get_total(self):
        return self.get_bill() + self.get_free()


class Freshesk(TicketingSystem):
    def __init__(self, config, report_date, offset):
        TicketingSystem.__init__(self, config, report_date)
        self.report_date -= td(hours=self.config.getint('freshdesk', 'tz_shift')) + td(seconds=1)
        self.auth = (self.config.get('freshdesk', 'api_key'), 'X')
        self.params = {'agent_id': self.config.get('freshdesk', 'agent_id'),
                       'executed_after': self.report_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
                       'executed_before': (self.report_date + td(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}
        self.url = self.config.get('freshdesk', 'url')
        self.api_url = self.url + '/api/v2/time_entries'
        self.entry_url = self.url + '/a/tickets/'
        self.json = self.get_json()
        self.data = sorted(self.json, key=lambda k: (k.get('ticket_id'), k.get('updated_at'))) if self.json else []
        self.entries = [Entry(id=i.get('ticket_id'),
                              billable=i.get('billable'),
                              spent=Time.from_string(i.get('time_spent')),
                              note=i.get('note'))
                        for i in self.data]


class TeamWork(TicketingSystem):
    def __init__(self, config_path, report_date, offset):
        TicketingSystem.__init__(self, config_path, report_date)
        self.auth = HTTPBasicAuth(self.config.get('teamwork', 'api_key'), 'X')
        self.url = self.config.get('teamwork', 'url')
        self.api_url = self.url + '/time_entries.json'
        self.params = params = {
            'userId': self.config.get('teamwork', 'agent_id'),
            'fromdate': self.report_date.strftime('%Y%m%d'),
            'todate': self.report_date.strftime('%Y%m%d')
        }
        self.json = self.get_json()
        self.data = sorted(self.get_json().get('time-entries')) if self.json else []
        self.entries = [Entry(id=i.get('todo-item-id'),
                              spent=(i.get('hours') * 3600 + i.get('minutes') * 60),
                              billable=(i.get('isbillable') == 1),
                              note=i.get('project-name'))
                        for i in self.data]


class Jira(TicketingSystem):
    def __init__(self, config_path, report_date, offset):
        TicketingSystem.__init__(self, config_path, report_date)
        jira_login = self.config.get('jira', 'login')
        jira_pass = self.config.get('jira', 'password')
        self.auth = HTTPBasicAuth(jira_login, jira_pass)
        self.url = self.config.get('jira', 'url')
        self.api_url = self.url + '/rest/api/2/search'
        self.entry_url = self.url + '/browse/'
        json = requests.post(self.api_url,
                             headers={"Content-Type": "application/json"},
                             json={
                                 'jql': f'''worklogAuthor = {jira_login} AND worklogDate = {self.report_date.strftime('%Y-%m-%d')}''',
                                 "fields": ["key"],
                                 "maxResults": 1000},
                             auth=HTTPBasicAuth(jira_login, jira_pass)).json()
        entries = []
        for issue in json['issues']:
            ans = requests.get(f'{self.url}/rest/api/2/issue/' +
                               issue['key'] + '/worklog',
                               auth=HTTPBasicAuth(jira_login, jira_pass)).json()
            for worklog in ans['worklogs']:
                if (worklog['author']['name'] == jira_login and
                        worklog['started'].split('T')[0] == report_date.strftime('%Y-%m-%d')):
                    time_spent = int(worklog.get('timeSpentSeconds'))
                    entries.append(Entry(id=issue.get('key'),
                                         billable=False,
                                         spent=Time(time_spent),
                                         note=worklog.get('comment')))
        self.entries = entries


parser = argparse.ArgumentParser(description='Simple time tracker for Freshdesk')
parser.add_argument('offset', action='store', type=int, nargs='?', help='Offset in days from today')
parser.add_argument('config_path', action='store', type=str, nargs='?', help='Path to config')
parser.set_defaults(offset=0, config_path='./config.ini')

args = parser.parse_args()

config = configparser.RawConfigParser()
config.read(args.config_path)
offset = args.offset
report_date = datetime.combine(date.today(), datetime.min.time()) - td(days=offset)

print(f'''Time records for {report_date.strftime('%d %b %Y')}\n''')

params = (config, report_date, offset)

print('\rGetting Freshesk...', end='')
fd = Freshesk(*params)
print('\rGetting Jira...    ', end='')
ji = Jira(*params)
print('\rGetting TeamWork...', end='')
tw = TeamWork(*params)
print('\r                   ', end='\r')

print(fd)
print(ji)
print(tw)

workday_begin = Time.from_string(config.get('global', 'workday_begin'))
workday_end = Time.from_string(config.get('global', 'workday_end'))
launch_begin = Time.from_string(config.get('global', 'launch_begin'))
launch_end = Time.from_string(config.get('global', 'launch_end'))

launch_duration = launch_end - launch_begin
workday_duration = workday_end - workday_begin - launch_duration

time_now = Time.from_string(datetime.now().strftime('%H:%M'))

total_bill_time = sum((fd.get_bill(), tw.get_bill(), ji.get_bill()))
total_free_time = sum((fd.get_free(), tw.get_free(), ji.get_free()))
total_tracked_time = total_bill_time + total_free_time

if args.offset == 0 and workday_begin <= time_now <= workday_end:
    total_time = time_now - workday_begin
    if launch_begin <= time_now <= launch_end:
        total_time = launch_begin - workday_begin
    if time_now > launch_end:
        total_time -= launch_duration

    untracked_time = total_time - total_tracked_time
else:
    untracked_time = workday_duration - total_tracked_time

terminal_width = 60
try:
    bill_part = int(total_bill_time.seconds / total_tracked_time.seconds * terminal_width)
    free_part = int(total_free_time.seconds / total_tracked_time.seconds * terminal_width)
except ZeroDivisionError:
    bill_part = 0
    free_part = terminal_width

print(f'''

Total tracked time:    {total_tracked_time}
- Freshdesk billable:  {fd.get_bill()}
- Freshdesk free:      {fd.get_free()}
- Teamwork billable:   {tw.get_bill()}
- Teamwork free:       {tw.get_free()}
- Jira:                {ji.get_free()}

Bill to free ratio:
[{TerminalColor.GREEN + ('#' * bill_part) + TerminalColor.END + (' ' * free_part)}]

Untracked time{' by now' if offset == 0 else ''}: {untracked_time}
''')
