#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import configparser
from datetime import datetime, date, timedelta as td

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth


class Time(object):
    format = '''{sign}{day}{hour:02}:{minute:02}'''

    def __init__(self, time=None):
        """Args:
                time (int) time span in seconds
                time (str) time span in format HH:MM
                time (tuple) (hh,mm)
                time (Time)
        """
        if time is None:
            self.time = 0.0
        elif isinstance(time, (int, float)):
            self.time = float(time)
        elif type(time) is str:
            self.time = float(time[:2]) * 3600.0 + float(time[3:]) * 60.0
        elif type(time) is tuple:
            self.time = time[0] * 3600.0 + time[1] * 60.0
        elif type(time) is td:
            self.time = time.total_seconds()
        elif type(time) is Time:
            self.time = time.time
        else:
            raise TypeError('Time must be integer number of seconds or string in format HH:MM')

    def __repr__(self):
        negative = self.time < 0
        total_seconds = round(abs(self.time))

        msec = 60
        hsec = 60 * msec
        dsec = 24 * hsec

        day = total_seconds // dsec
        total_seconds -= day * dsec

        hour = total_seconds // hsec
        total_seconds -= hour * hsec

        minute = total_seconds // msec
        total_seconds -= minute * msec

        second = total_seconds

        repr = Time.format.format(sign='-' if negative else '',
                                  day=f'{day} day ' if day > 0 else '',
                                  hour=hour,
                                  minute=minute,
                                  second=second)
        return repr

    def __add__(self, other):
        if other == 0:
            return self
        return Time(self.time + other.time)

    def __radd__(self, other):
        if type(other) is int:
            return self
        else:
            return self.__add__(other)

    def __sub__(self, other):
        return self.__add__(Time(-other.time))

    def __lt__(self, other):
        return self.time < other.time

    def __le__(self, other):
        return self.time <= other.time


class Entry(object):
    def __init__(self, entry_id, billable, spent, note=''):
        self.id = entry_id
        self.billable = billable
        self.spent = spent
        self.note = note


class TicketingSystem(object):
    def prepare_url(self):
        raise (Exception, 'Not implemented')

    def get_json(self):
        try:
            s = requests.Session()
            s.mount('https://', HTTPAdapter(max_retries=self.max_retries))
            ans = s.get(self.api_url, params=self.params, auth=self.auth, timeout=self.timeout)
        except requests.ConnectTimeout:
            print('Connection timeout...')
            raise
        return ans.json()

    def parse_json(self):
        raise (Exception, 'Not implemented')

    def get_billable(self):
        time = Time(sum(i.spent for i in self.entries if i.billable))
        return time

    def get_notbillable(self):
        time = Time(sum(i.spent for i in self.entries if not i.billable))
        return time

    def get_total(self):
        return self.get_billable() + self.get_notbillable()

    def __init__(self, config, report_date):
        self.config = config
        self.report_date = report_date
        self.auth = None
        self.params = None
        self.url = None
        self.api_url = None
        self.max_retries = 5
        self.timeout = 3
        self.entries = []
        self.entry_url = None

    def __repr__(self):
        res = []
        for entry in self.entries:
            res.append(
                f'''{self.entry_url}{entry.id}'''
                f'''\n\t{'Billable' if entry.billable else 'Not billable'}: {entry.spent} {entry.note}''')
        return '\n'.join(res)


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
        self.entries = [Entry(entry_id=i.get('ticket_id'),
                              billable=i.get('billable'),
                              spent=Time(i.get('time_spent')),
                              note=i.get('note'))
                        for i in sorted(self.get_json(),
                                        key=lambda k: (k.get('ticket_id'), k.get('updated_at')))]


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
        self.entries = [Entry(entry_id=i.get('todo-item-id'),
                              spent=(i.get('hours'), i.get('minutes')),
                              billable=(i.get('isbillable') == 1),
                              note=i.get('project-name'))
                        for i in sorted(self.get_json().get('time-entries'))]


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
                    entries.append(Entry(entry_id=issue.get('key'),
                                         billable=False,
                                         spent=Time(time_spent),
                                         note=worklog.get('comment')))
        self.entries = entries


parser = argparse.ArgumentParser(description='Simple time tracker for Freshdesk')
parser.add_argument('config_path', action='store', type=str, nargs='?', help='Path to config')
parser.add_argument('offset', action='store', type=int, nargs='?', help='Offset in days from today')
parser.set_defaults(offset=0, config_path='./config.ini')

args = parser.parse_args()

config = configparser.RawConfigParser()
config.read(args.config_path)
offset = args.offset
report_date = datetime.combine(date.today(), datetime.min.time()) - td(days=offset)

print(report_date.strftime('%d %b %Y'))
print()

fd = Freshesk(config, report_date, offset)
print(fd)
ji = Jira(config, report_date, offset)
print(ji)
tw = TeamWork(config, report_date, offset)
print(tw)

workday_begin = Time(config.get('global', 'workday_begin'))
workday_end = Time(config.get('global', 'workday_end'))
launch_begin = Time(config.get('global', 'launch_begin'))
launch_end = Time(config.get('global', 'launch_end'))

launch_duration = launch_end - launch_begin
workday_duration = workday_end - workday_begin - launch_duration

time_now = Time((datetime.now().hour, datetime.now().minute))
total_tracked_time = sum((fd.get_total(), tw.get_total(), ji.get_total()))
if args.offset == 0 and workday_begin <= time_now <= workday_end:
    total_time = time_now - workday_begin
    if launch_begin <= time_now <= launch_end:
        total_time = launch_begin - workday_begin
    if time_now > launch_end:
        total_time -= launch_duration

    untracked_time = total_time - total_tracked_time
else:
    untracked_time = workday_duration - total_tracked_time
#
print(f'''
Total tracked time:    {sum((fd.get_total(), tw.get_total(), ji.get_total()))}
- Freshdesk billable:  {fd.get_billable()}
- Freshdesk free:      {fd.get_notbillable()}
- Teamwork billable:   {tw.get_billable()}
- Teamwork free:       {tw.get_notbillable()}
- Jira:                {ji.get_notbillable()}

Untracked time{' by now' if offset == 0 else ''}: {untracked_time}
''')
