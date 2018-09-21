#!/usr/bin/env python3.7
# -*- coding: utf-8 -*-
import argparse
import asyncio
import configparser
import os
from collections import namedtuple
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
        tmp = self
        if tmp.seconds % seconds != 0:
            tmp.seconds = tmp.seconds // seconds * seconds
            tmp.seconds += seconds
        return tmp

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


def colored(text, color):
    colors = {'black': '\033[30m',
              'red': '\033[31m',
              'green': '\033[32m',
              'yellow': '\033[33m',
              'blue': '\033[34m',
              'magenta': '\033[35m',
              'cyan': '\033[36m',
              'white': '\033[37m',
              'reset': '\033[39m',
              'normal': '\033[39m'}
    if text:
        return colors[color] + text + colors['reset']
    else:
        return text


@dataclass
class Entry(object):
    id: int
    billable: bool
    spent: Time
    note: str = ''


@dataclass
class TicketingSystem:
    config: configparser.RawConfigParser
    report_date: datetime = datetime.today()
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

    def get_entries(self):
        raise NotImplementedError

    def get_bill(self):
        time = Time(sum(i.spent.seconds for i in self.entries if i.billable))
        return time

    def get_free(self):
        time = Time(sum(i.spent.seconds for i in self.entries if not i.billable))
        return time

    def get_total(self):
        return self.get_bill() + self.get_free()

    def print_if_not_empty(self):
        if self.entries:
            print(self)


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

    def get_ticket(self, ticket_num):
        self.api_url = f'''{self.config.get('freshdesk', 'url')}/api/v2/tickets/{ticket_num}/time_entries'''
        self.params = None
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            asyncio.wait(
                (
                    self.get_json(),
                )
            )
        )

        self.entries = [Entry(id=i.get('ticket_id'),
                              billable=i.get('billable'),
                              spent=Time.from_string(i.get('time_spent')),
                              note=i.get('note'))
                        for i in self.json]

        return (f'''Time records for ticket {ticket_num}:
        Total: {self.get_total()}
        Bill:  {self.get_bill()}
        Free:  {self.get_free()}
        ''')


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
                                    worklog['started'].split('T')[0] == self.report_date.strftime('%Y-%m-%d')):
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


def get_stats(config, pool, report_date, ceil_seconds=5 * 60):
    workday_begin = Time.from_string(config.get('global', 'workday_begin'))
    workday_end = Time.from_string(config.get('global', 'workday_end'))
    launch_begin = Time.from_string(config.get('global', 'launch_begin'))
    launch_end = Time.from_string(config.get('global', 'launch_end'))

    launch_duration = launch_end - launch_begin
    workday_duration = workday_end - workday_begin - launch_duration

    time_now = Time.from_string(datetime.now().strftime('%H:%M'))

    total_bill_time = sum(ts.get_bill() for ts in pool)  # sum((fd.get_bill(), tw.get_bill(), ji.get_bill()))
    total_free_time = sum(ts.get_free() for ts in pool)  # sum((fd.get_free(), tw.get_free(), ji.get_free()))
    total_tracked_time = total_bill_time + total_free_time

    report_is_now = report_date.date() == date.today() and workday_begin <= time_now <= workday_end

    if report_is_now:
        total_time = time_now - workday_begin
        if launch_begin <= time_now <= launch_end:
            total_time = launch_begin - workday_begin
        if time_now > launch_end:
            total_time -= launch_duration

        untracked_time = total_time - total_tracked_time
        rest_time = workday_duration - total_tracked_time
    else:
        untracked_time = workday_duration - total_tracked_time
        rest_time = Time(0)

    # Ceil to 5 minutes
    untracked_time = untracked_time.ceil(ceil_seconds)

    stats = namedtuple('Stats', ['total_tracked_time',
                                 'total_bill_time',
                                 'total_free_time',
                                 'untracked_time',
                                 'workday_duration', ])

    return stats(total_tracked_time, total_bill_time, total_free_time, untracked_time, rest_time)


def show_stats(pool, stats):
    print(f'\nTotal tracked time: {stats.total_tracked_time}')
    for ts in pool:
        ts_name = ts.__class__.__name__
        ts_bill = ts.get_bill()
        if ts_bill.seconds > 0:
            print(f'     {ts_name:<8} bill: {ts_bill}')
        ts_free = ts.get_free()
        if ts_free.seconds > 0:
            print(f'     {ts_name:<8} free: {ts_free}')


def get_ratio(total_tracked_time: Time,
              total_bill_time: Time,
              total_free_time: Time,
              untracked_time: Time,
              rest_time: Time,
              terminal_width_chr: int = 55) -> str:
    total = sum((total_tracked_time,
                 untracked_time,
                 rest_time,))

    width = terminal_width_chr / total.seconds

    bill_part = colored('#' * int(total_bill_time.seconds * width), 'green')
    free_part = colored('#' * int(total_free_time.seconds * width), 'normal')
    none_part = colored('#' * int(untracked_time.seconds * width), 'red')
    rest_part = '_' * int(rest_time.seconds * width)
    return f'''Progress: [{bill_part + free_part + none_part + rest_part}]'''

def export_to_sheet():
    from googleapiclient.discovery import build
    from httplib2 import Http
    from oauth2client import file, client, tools
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
        creds = tools.run_flow(flow, store)
    service = build('sheets', 'v4', http=creds.authorize(Http()))

    # Call the Sheets API
    SPREADSHEET_ID = '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
    RANGE_NAME = 'Class Data!A2:E'
    result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID,
                                                 range=RANGE_NAME).execute()
    values = result.get('values', [])

    if not values:
        print('No data found.')
    else:
        print('Name, Major:')
        for row in values:
            # Print columns A and E, which correspond to indices 0 and 4.
            print('%s, %s' % (row[0], row[4]))


def main():
    parser = argparse.ArgumentParser(description='Simple time tracker for Freshdesk, Jira and TeamWork')
    parser.add_argument('offset', default='0', type=str, nargs='?',
                        help='Offset in days from today or date in format dd-mm-yyyy')
    parser.add_argument('-c', '--config', default='~/config.ini', type=str, nargs='?', help='Path to config')
    parser.add_argument('-ft', '--ticket', type=int, nargs='?',
                        help='Freshdesk ticker number. If provided, return spent time for the ticket')

    args = parser.parse_args()
    config = configparser.RawConfigParser()
    config.read(os.path.expanduser(args.config))

    if args.ticket:
        fd = Freshesk(config)
        print(fd.get_ticket(args.ticket))

    else:
        if args.offset.isdigit():
            report_date = datetime.combine(date.today(), datetime.min.time()) - timedelta(days=int(args.offset))
        else:
            try:
                report_date = datetime.strptime(args.offset, config.get('global', 'date_format'))
            except ValueError as e:
                print(
                    f'''{args.offset} is neither an integer nor matches format {config.get('global', 'date_format')}.''')
                print(f'''Try to run script with -h to get help''')
                raise SystemExit(1)

        # Highlight date if report date if weekend
        date_str = report_date.strftime('%a %d %b %Y')
        if report_date.weekday() in (5, 6):
            date_str = colored(date_str, 'red')
        print(f'Time records for {date_str}')

        pool = [cls(config, report_date) for cls in TicketingSystem.__subclasses__()]
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            asyncio.wait([ts.get_json() for ts in pool])
        )

        # FIXME
        for ts in pool:
            ts.get_entries()
            ts.print_if_not_empty()

        stats = get_stats(config, pool, report_date)
        show_stats(pool, stats)

        print('\n' + get_ratio(*stats))

        print(f'''Untracked time: {stats.untracked_time}''')


if __name__ == '__main__':
    main()
