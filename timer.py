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
import keyring
import pytz


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

        return t_format.format(
            sign='-' if negative else '',
            day=f'{day} day ' if day > 0 else '',
            hour=hour,
            minute=minute,
            second=second,
        )

    def ceil(self, seconds):
        tmp = self
        if tmp.seconds % seconds != 0:
            tmp.seconds = tmp.seconds // seconds * seconds
            tmp.seconds += seconds
        return tmp

    def __repr__(self):
        return self.__format__('''{sign}{day}{hour:02}:{minute:02}''')

    def __add__(self, other):
        return self if other == 0 else Time(self.seconds + other.seconds)

    def __radd__(self, other):
        return self if type(other) is int else self.__add__(other)

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
    return colors[color] + text + colors['reset'] if text else text


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
        res = [
            f'''{self.entry_url}{entry.id}\n\t{'Bill' if entry.billable else 'Free'}: {entry.spent} {entry.note}'''
            for entry in self.entries
        ]

        return '\n'.join(res)

    def __repr__(self):
        return __name__ + self.__str__()

    async def get_json(self):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.api_url, params=self.params, timeout=self.timeout, auth=self.auth) as resp:
                    return await resp.json()
            except asyncio.TimeoutError:
                print(f'Got timeout while getting {self.__class__.__name__}')

    async def get_entries(self):
        raise NotImplementedError

    def get_bill(self):
        return Time(sum(i.spent.seconds for i in self.entries if i.billable))

    def get_free(self):
        return Time(sum(i.spent.seconds for i in self.entries if not i.billable))

    def get_total(self):
        return self.get_bill() + self.get_free()

    def print_if_not_empty(self):
        if self.entries:
            print(self)


@dataclass
class Freshdesk(TicketingSystem):
    # FIXME someday in must become async and include self.json = self.get.json() initialisation
    def __post_init__(self):
        local = pytz.timezone(self.config.get('global', 'timezone'))
        local_dt = local.localize(self.report_date)
        utc_dt = local_dt.astimezone(pytz.utc)
        self.report_date = utc_dt - timedelta(seconds=1)
        self.agent_id = self.config.get('freshdesk', 'agent_id')
        self.auth = aiohttp.BasicAuth(keyring.get_password('freshdesk', self.agent_id), 'X')
        self.params = {'agent_id': self.agent_id,
                       'executed_after': self.report_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
                       'executed_before': (self.report_date + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}
        self.url = self.config.get('freshdesk', 'url')
        self.api_url = f'{self.url}/api/v2/time_entries'
        self.entry_url = f'{self.url}/a/tickets/'
        self.free_tags = self.config.get('freshdesk', 'free_tags').split()

    def __parse_json__(self):
        if not self.json:
            return
        data = sorted(self.json, key=lambda k: (k.get('ticket_id'), k.get('updated_at')))
        self.entries = [Entry(id=i.get('ticket_id'),
                              billable=i.get('billable'),
                              spent=Time.from_string(i.get('time_spent')),
                              note=i.get('note'))
                        for i in data]

        if self.free_tags:
            for entry in self.entries:
                if entry.billable:
                    if any(tag in entry.note for tag in self.free_tags):
                        entry.note += colored(' Warn! Billable entry with free tag!', 'red')
                elif all(tag not in entry.note for tag in self.free_tags):
                    entry.note += colored(' Warn! Free entry without free tag!', 'red')

    async def get_entries(self):
        self.json = await self.get_json()
        self.__parse_json__()
        return self

    async def get_ticket(self, ticket_num):
        self.api_url = f'''{self.config.get('freshdesk', 'url')}/api/v2/tickets/{ticket_num}/time_entries'''
        self.params = None
        self.json = await self.get_json()
        self.__parse_json__()

        return (f'''Time records for ticket {ticket_num}:
        Total: {self.get_total()}
        Bill:  {self.get_bill()}
        Free:  {self.get_free()}
        ''')


@dataclass
class TeamWork(TicketingSystem):
    def __post_init__(self):
        self.agent_id = self.config.get('teamwork', 'agent_id')
        self.auth = aiohttp.BasicAuth(keyring.get_password('teamwork', self.agent_id), 'x')
        self.url = self.config.get('teamwork', 'url')
        self.api_url = f'{self.url}/time_entries.json'
        self.entry_url = f'{self.url}/#tasks/'
        self.params = {
            'userId': self.config.get('teamwork', 'agent_id'),
            'fromdate': self.report_date.strftime('%Y%m%d'),
            'todate': self.report_date.strftime('%Y%m%d')
        }

    async def get_entries(self):
        self.json = await self.get_json()
        if self.json:
            data = sorted(self.json.get('time-entries'), key=lambda k: (k.get('date')))
            self.entries = [Entry(id=i.get('todo-item-id'),
                                  spent=(Time(int(i.get('hours')) * 3600 + int(i.get('minutes')) * 60)),
                                  billable=(i.get('isbillable') == 1),
                                  note=i.get('project-name'))
                            for i in data]
        return self


@dataclass
class Jira(TicketingSystem):
    def __post_init__(self):
        self.login = self.config.get('jira', 'login')
        self.auth = aiohttp.BasicAuth(self.login, keyring.get_password('jira', self.login))
        self.url = self.config.get('jira', 'url')
        self.api_url = f'{self.url}/rest/api/2/search'
        self.entry_url = f'{self.url}/browse/'
        self.params = {
            'jql': f'''worklogAuthor=currentUser() and worklogDate={self.report_date.strftime('%Y-%m-%d')}''',
            'maxResults': 1000,
            'fields': 'id'}

    async def get_entries(self):
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

        self.json = await self.get_json()
        if self.json:
            for issue in self.json.get('issues'):
                await get_issue(issue.get('self') + '/worklog', issue.get('key'))

        return self


def calc_stats(total_bill_time, total_free_time, time_now, report_date, config, ceil_seconds=5 * 60):
    workday_begin = Time.from_string(config.get('global', 'workday_begin'))
    workday_end = Time.from_string(config.get('global', 'workday_end'))
    launch_begin = Time.from_string(config.get('global', 'launch_begin'))
    launch_end = Time.from_string(config.get('global', 'launch_end'))

    launch_duration = launch_end - launch_begin
    workday_duration = workday_end - workday_begin - launch_duration
    total_tracked_time = total_bill_time + total_free_time
    report_is_now = report_date.date() == date.today() and workday_begin <= time_now <= workday_end

    if report_is_now:
        if time_now < launch_begin:
            time_from_wd_begin = time_now - workday_begin
        elif launch_begin <= time_now <= launch_end:
            time_from_wd_begin = launch_begin - workday_begin
        else:
            time_from_wd_begin = time_now - workday_begin - launch_duration

        untracked_time = time_from_wd_begin - total_tracked_time
        till_end_of_work_time = workday_duration - time_from_wd_begin
    else:
        untracked_time = workday_duration - total_tracked_time
        till_end_of_work_time = Time(0)

    # Ceil to 5 minutes
    untracked_time = untracked_time.ceil(ceil_seconds)

    stats = namedtuple('Stats', ['total_tracked_time',
                                 'total_bill_time',
                                 'total_free_time',
                                 'untracked_time',
                                 'till_end_of_work_time',
                                 'workday_duration', ])

    return stats(total_tracked_time,
                 total_bill_time,
                 total_free_time,
                 untracked_time,
                 till_end_of_work_time,
                 workday_duration)


def get_stats_str(pool, stats):
    res = [f'Total tracked time: {stats.total_tracked_time}']
    for ts in pool:
        ts_name = ts.__class__.__name__
        ts_bill = ts.get_bill()
        if ts_bill.seconds > 0:
            res.append(f'     {ts_name:<8} bill: {ts_bill}')
        ts_free = ts.get_free()
        if ts_free.seconds > 0:
            res.append(f'     {ts_name:<8} free: {ts_free}')

    return '\n'.join(res)


def get_ratio_str(stats, terminal_width_chr: int = 48) -> str:
    total = max(stats.total_tracked_time, stats.workday_duration)

    width = total.seconds / terminal_width_chr

    if stats.untracked_time.seconds > 0:
        untracked_time = stats.untracked_time
    else:
        untracked_time = Time(0)

    if stats.total_tracked_time > stats.workday_duration:
        rest_time = Time(0)
    else:
        rest_time = stats.workday_duration - stats.total_tracked_time - untracked_time

    bill_part = colored('#' * round(stats.total_bill_time.seconds / width), 'green')
    free_part = colored('#' * round(stats.total_free_time.seconds / width), 'normal')
    none_part = colored('#' * round(untracked_time.seconds / width), 'red')
    rest_part = '_' * round(rest_time.seconds / width)
    return f'Progress: [{bill_part + free_part + none_part + rest_part}]'


def setup_wizard(config, config_path):
    def get_option(prompt, default=''):
        res = input(f'{prompt} [{default}]?: ') if default else input(f'{prompt}: ')
        if not res:
            res = default
        return res

    print(f'''Cannot find config at {config_path}. Let's create it!''')
    config.add_section('global')
    config.set('global', 'workday_begin', get_option('Workday begins at', '10:00'))
    config.set('global', 'workday_end', get_option('Workday ends at', '19:00'))
    config.set('global', 'launch_begin', get_option('Launch begins at', '13:00'))
    config.set('global', 'launch_end', get_option('Launch ends at', '14:00'))
    config.set('global', 'timezone', get_option('Timezone is', 'Europe/Moscow'))
    config.set('global', 'date_format', get_option('Date format is', '%d.%m.%Y'))

    if 'y' in get_option('Add Freshdesk details', 'Y/n').lower():
        config.add_section('freshdesk')
        config.set('freshdesk', 'url', 'https://' + get_option('Company name').lower() + '.freshdesk.com')
        config.set('freshdesk', 'agent_id', get_option('Agent ID'))
        keyring.set_password('freshdesk', config.get('freshdesk', 'agent_id'), get_option('API key'))
        config.set('freshdesk', 'free_tags', get_option('Tags with non-billable time',
                                                        'DEVBUG SUPBUG STUDY HELP CONTR COM ORG OTHER UPDATE'))

    if 'y' in get_option('Add Jira details', 'Y/n').lower():
        config.add_section('jira')
        config.set('jira', 'url', get_option('Jira URL'))
        config.set('jira', 'login', get_option('Login'))
        keyring.set_password('jira', config.get('jira', 'login'), get_option('Password'))

    if 'y' in get_option('Add TeamWork details', 'Y/n').lower():
        config.add_section('teamwork')
        config.set('teamwork', 'url', get_option('TeamWork URL', 'latera'))
        config.set('teamwork', 'agent_id', get_option('Agent ID'))
        keyring.set_password('teamwork', config.get('teamwork', 'agent_id'), get_option('API key'))

    with open(config_path, mode='w') as f:
        config.write(f)


async def main():
    parser = argparse.ArgumentParser(description='Simple time tracker for Freshdesk, TeamWork and Jira')
    parser.add_argument('offset', default='0', type=str, nargs='?',
                        help='Offset in days from today or date in format dd-mm-yyyy')
    parser.add_argument('-c', '--config', default='~/timer.conf', type=str, nargs='?', help='Path to config')
    parser.add_argument('-t', '--ticket', type=int, nargs='?',
                        help='Freshdesk ticker number. If provided, return spent time for the ticket')

    args = parser.parse_args()
    config = configparser.RawConfigParser()
    config_path = os.path.expanduser(args.config)
    if not os.path.exists(config_path):
        setup_wizard(config, config_path)

    config.read(os.path.expanduser(args.config))

    if args.ticket:
        fd = Freshdesk(config)
        result = await fd.get_ticket(args.ticket)
        print(result)

    else:
        if args.offset.isdigit():
            report_date = datetime.combine(date.today(), datetime.min.time()) - timedelta(days=int(args.offset))
        else:
            try:
                report_date = datetime.strptime(args.offset, config.get('global', 'date_format'))
            except ValueError:
                print(
                    f'{args.offset} is neither an integer nor matches format {config.get("global", "date_format")}.')
                print('Try to run script with -h to get help')
                raise SystemExit(1)

        # Highlight date if report date if weekend
        date_str = report_date.strftime('%a %d %b %Y')
        if report_date.weekday() in (5, 6):
            date_str = colored(date_str, 'red')
        print(f'Time records for {date_str}')

        pool = [cls(config, report_date) for cls in TicketingSystem.__subclasses__() if
                config.has_section(cls.__name__.lower())]
        tasks = asyncio.as_completed([asyncio.create_task(ts.get_entries()) for ts in pool])
        for task in tasks:
            try:
                ts = await task
                ts.print_if_not_empty()
            except asyncio.CancelledError:
                task.close()

        time_now = Time.from_string(datetime.now().strftime('%H:%M'))

        total_bill_time = sum(ts.get_bill() for ts in pool)
        total_free_time = sum(ts.get_free() for ts in pool)

        stats = calc_stats(total_bill_time=total_bill_time,
                           total_free_time=total_free_time,
                           time_now=time_now,
                           report_date=report_date,
                           config=config)

        print('\n' + get_stats_str(pool, stats))
        print('\n' + get_ratio_str(stats))
        print(f'''Untracked time: {stats.untracked_time}''')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        SystemExit(1)
