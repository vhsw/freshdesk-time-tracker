#!/usr/bin/env python3.7
# -*- coding: utf-8 -*-
import argparse
import asyncio
import configparser
import os
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Tuple, Dict

import aiohttp


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

    def ceil(self, seconds):
        if self.seconds % seconds != 0:
            self.seconds = self.seconds // seconds * seconds
            self.seconds += seconds
        return self

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


class TermColor:
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    NORM = END


@dataclass
class Entry(object):
    id: int
    billable: bool
    spent: Time
    note: str = ''


@dataclass
class TicketingSystem:
    config: configparser.RawConfigParser
    report_date: datetime = datetime.min
    json: Dict = None
    entries: List[Entry] = field(default_factory=list)
    auth: Tuple[str] = field(init=False)
    params: Dict[str, str] = field(init=False)
    url: str = field(init=False)
    api_url: str = field(init=False)
    entry_url: str = field(init=False)
    max_retries: int = field(init=False, default=5)
    timeout: int = field(init=False, default=5)

    def __str__(self):
        res = []
        for entry in self.entries:
            res.append(
                f'''{self.entry_url}{entry.id}'''
                f'''\n\t{'Bill' if entry.billable else 'Free'}: {entry.spent} {entry.note}''')
        return '\n'.join(res)

    def __repr__(self):
        return __name__ + self.__str__()

    async def get_json(self):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.api_url, params=self.params, timeout=self.timeout, auth=self.auth) as resp:
                    self.json = await resp.json()
            except asyncio.TimeoutError:
                print(f'Got timeout while getting {self.__class__.__name__}')

    def get_bill(self):
        time = Time(sum(i.spent.seconds for i in self.entries if i.billable))
        return time

    def get_free(self):
        time = Time(sum(i.spent.seconds for i in self.entries if not i.billable))
        return time

    def get_total(self):
        return self.get_bill() + self.get_free()


@dataclass
class Freshesk(TicketingSystem):
    def __post_init__(self):
        self.report_date -= timedelta(hours=self.config.getint('freshdesk', 'tz_shift')) + timedelta(seconds=1)
        self.auth = aiohttp.BasicAuth(self.config.get('freshdesk', 'api_key'), 'X')
        self.params = {'agent_id': self.config.get('freshdesk', 'agent_id'),
                       'executed_after': self.report_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
                       'executed_before': (self.report_date + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}
        self.url = self.config.get('freshdesk', 'url')
        self.api_url = self.url + '/api/v2/time_entries'
        self.entry_url = self.url + '/a/tickets/'

    def get_entries(self):
        data = sorted(self.json, key=lambda k: (k.get('ticket_id'), k.get('updated_at'))) if self.json else []
        self.entries = [Entry(id=i.get('ticket_id'),
                              billable=i.get('billable'),
                              spent=Time.from_string(i.get('time_spent')),
                              note=i.get('note'))
                        for i in data]


@dataclass
class TeamWork(TicketingSystem):
    def __post_init__(self):
        self.auth = aiohttp.BasicAuth(self.config.get('teamwork', 'api_key'), 'x')
        self.url = self.config.get('teamwork', 'url')
        self.api_url = self.url + '/time_entries.json'
        self.entry_url = self.url + '/#tasks/'
        self.params = {
            'userId': self.config.get('teamwork', 'agent_id'),
            'fromdate': self.report_date.strftime('%Y%m%d'),
            'todate': self.report_date.strftime('%Y%m%d')
        }

    def get_entries(self):
        data = sorted(self.json.get('time-entries'), key=lambda k: (k.get('date'))) if self.json else []
        self.entries = [Entry(id=i.get('todo-item-id'),
                              spent=(Time(int(i.get('hours')) * 3600 + int(i.get('minutes')) * 60)),
                              billable=(i.get('isbillable') == 1),
                              note=i.get('project-name'))
                        for i in data]


@dataclass
class Jira(TicketingSystem):
    def __post_init__(self):
        jira_login = self.config.get('jira', 'login')
        jira_pass = self.config.get('jira', 'password')
        self.auth = aiohttp.BasicAuth(jira_login, jira_pass)
        self.url = self.config.get('jira', 'url')
        self.api_url = self.url + '/rest/api/2/search'
        self.entry_url = self.url + '/browse/'
        self.params = {
            'jql': f'''worklogAuthor=currentUser() and worklogDate={self.report_date.strftime('%Y-%m-%d')}''',
            'maxResults': 1000,
            'fields': 'id'}

    # FIXME
    def get_entries(self):
        async def get_issue(url, issue_id):
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url, timeout=self.timeout, auth=self.auth, compress=True) as resp:
                        result = await resp.json()
                        for worklog in result['worklogs']:
                            if (worklog['author']['name'] == self.config.get('jira', 'login') and
                                    worklog['started'].split('T')[0] == report_date.strftime('%Y-%m-%d')):
                                time_spent = int(worklog.get('timeSpentSeconds'))
                                self.entries.append(Entry(id=issue_id,
                                                          billable=False,
                                                          spent=Time(time_spent),
                                                          note=worklog.get('comment')))
                except asyncio.TimeoutError:
                    print(f'Got timeout while getting {url}')

        loop = asyncio.get_event_loop()
        if self.json:
            tasks = [get_issue(issue.get('self') + '/worklog', issue.get('key')) for issue in self.json.get('issues')]
        else:
            tasks = []
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()


parser = argparse.ArgumentParser(description='Simple time tracker for Freshdesk')
parser.add_argument('offset', default='0', type=str, nargs='?',
                    help='Offset in days from today or date in format dd-mm-yyyy')
parser.add_argument('-c', '--config', default='~/config.ini', type=str, nargs='?', help='Path to config')
parser.add_argument('-t', '--ticket', type=int, nargs='?',
                    help='Freshdesk ticker #. If provided, return spent time for the ticket')

args = parser.parse_args()
config = configparser.RawConfigParser()
config.read(os.path.expanduser(args.config))

# FIXME Time records for one ticket
if args.ticket:
    ts = TicketingSystem(config)
    ts.api_url = f'''{config.get('freshdesk', 'url')}/api/v2/tickets/{args.ticket}/time_entries'''
    ts.auth = aiohttp.BasicAuth(config.get('freshdesk', 'api_key'), 'X')
    ts.params = None
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        asyncio.wait(
            (
                ts.get_json(),
            )
        )
    )

    ts.entries = [Entry(id=i.get('ticket_id'),
                        billable=i.get('billable'),
                        spent=Time.from_string(i.get('time_spent')),
                        note=i.get('note'))
                  for i in ts.json]

    print(f'''Time records for ticket #{args.ticket}:
Total: {ts.get_total()}
Bill:  {ts.get_bill()}
Free:  {ts.get_free()}
''')
    exit(0)

if args.offset.isdigit():
    report_date = datetime.combine(date.today(), datetime.min.time()) - timedelta(days=int(args.offset))
else:
    try:
        report_date = datetime.strptime(args.offset, config.get('global', 'date_format'))
    except ValueError as e:
        print(f'''{TermColor.RED}{args.offset} is neither an integer nor matches format {config.get('global', 'date_format')}.
Try to run script with -h to get help{TermColor.END}''')
        exit(1)

# Highlight date if report date if weekend
date_color = TermColor.RED if report_date.weekday() in (5, 6) else TermColor.END
print(f'''Time records for {report_date.strftime(f'{date_color}%a %d %b %Y{TermColor.END}')}\n''')

params = config, report_date

fd = Freshesk(*params)
tw = TeamWork(*params)
ji = Jira(*params)

loop = asyncio.get_event_loop()
loop.run_until_complete(
    asyncio.wait(
        (
            fd.get_json(),
            tw.get_json(),
            ji.get_json(),

        )
    )
)

# FIXME
ji.get_entries()
fd.get_entries()
tw.get_entries()


def print_if_not_empty(ts: TicketingSystem):
    if ts.entries:
        print(ts)


print_if_not_empty(fd)
print_if_not_empty(ji)
print_if_not_empty(tw)

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

report_is_now = report_date.date() == date.today() and workday_begin <= time_now <= workday_end

if report_is_now:
    total_time = time_now - workday_begin
    if launch_begin <= time_now <= launch_end:
        total_time = launch_begin - workday_begin
    if time_now > launch_end:
        total_time -= launch_duration

    untracked_time = total_time - total_tracked_time
else:
    untracked_time = workday_duration - total_tracked_time

# Ceil to 5 minutes
untracked_time.ceil(5 * 60)


def bill_to_free_ratio(bill_time=Time(0), free_time=Time(0), untracked=Time(0),
                       workday_duration=Time.from_params(hours=8), terminal_width=80):
    total = bill_time.seconds + free_time.seconds + untracked_time.seconds
    rest_time = Time(workday_duration.seconds - total)
    if rest_time.seconds < 0:
        rest_time = Time(0)
    else:
        total = workday_duration.seconds

    bill_part = int(bill_time.seconds / total * terminal_width)
    free_part = int(free_time.seconds / total * terminal_width)
    none_part = int(untracked.seconds / total * terminal_width)
    rest_part = int(rest_time.seconds / total * terminal_width)
    return f'''Progress:
[{(TermColor.GREEN * (bill_part>0)) + ('#' * bill_part) +
  (TermColor.NORM  * (free_part>0)) + ('#' * free_part) +
  (TermColor.RED   * (none_part>0)) + ('#' * none_part) +
  TermColor.NORM  + ('_' * rest_part)}]
'''


print(f'''
Total tracked time: {total_tracked_time}
- Freshdesk bill:   {fd.get_bill()}
- Freshdesk free:   {fd.get_free()}
- Teamwork  bill:   {tw.get_bill()}
- Teamwork  free:   {tw.get_free()}
- Jira      free:   {ji.get_free()}

{bill_to_free_ratio(total_bill_time,
                    total_free_time,
                    untracked_time,
                    workday_duration)}
Untracked time{' by now' if report_is_now else ''}: {untracked_time}
''')
