#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import configparser
from datetime import datetime, date, timedelta as td

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth


class SpentTime(object):
    def __init__(self, delta=td(0)):
        self.delta = delta

    def __repr__(self):
        minutes = round(self.delta.seconds / 60)
        dt = datetime.min + td(minutes=minutes)
        return dt.strftime('%H:%M')


class Entry(object):
    def __init__(self, id, billable, spent, note=''):
        self.id = id
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

    def __init__(self, config_path, report_date, offset):
        self.config = configparser.RawConfigParser()
        self.config.read(config_path)
        self.report_date = report_date - td(days=offset)
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
    def __init__(self, config_path, report_date, offset):
        TicketingSystem.__init__(self, config_path, report_date, offset)
        self.report_date -= td(hours=self.config.getint('freshdesk', 'tz_shift')) + td(seconds=1)
        self.auth = (self.config.get('freshdesk', 'api_key'), 'X')
        self.params = {'agent_id': self.config.get('freshdesk', 'agent_id'),
                       'executed_after': self.report_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
                       'executed_before': (self.report_date + td(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}
        self.url = self.config.get('freshdesk', 'url')
        self.api_url = self.url + '/api/v2/time_entries'
        self.entry_url = self.url + '/helpdesk/tickets/'
        self.entries = (Entry(id=i.get('ticket_id'),
                              billable=i.get('billable'),
                              spent=SpentTime(
                                  td(hours=int(i.get('time_spent')[:2]), minutes=int(i.get('time_spent')[3:]))),
                              note=i.get('note'))
                        for i in sorted(self.get_json(),
                                        key=lambda k: (k.get('ticket_id'), k.get('updated_at'))))


class TeamWork(TicketingSystem):
    def __init__(self, config_path, report_date, offset):
        TicketingSystem.__init__(self, config_path, report_date, offset)


class Jira(TicketingSystem):
    def __init__(self, config_path, report_date, offset):
        TicketingSystem.__init__(self, config_path, report_date, offset)
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
                                         spent=SpentTime(td(seconds=time_spent)),
                                         note=worklog.get('comment')))
        self.entries = entries

config = 'config.ini'
report_date = datetime.combine(date.today(), datetime.min.time())
offset = 0
fd = Freshesk(config,report_date,offset)
print(fd)
ji = Jira(config,report_date,offset)
print(ji)
tw = TeamWork(config,report_date,offset)
print(tw)


# # Variables
# fd_bill_time = td(0)
# fd_free_time = td(0)
#
# tw_bill_time = td(0)
# tw_free_time = td(0)
#
# jira_time = td(0)
#
# config = configparser.RawConfigParser()
# config.read('config.ini')
#
# report_date = datetime.combine(date.today(), datetime.min.time())
# parser = argparse.ArgumentParser(description='Simple time tracker for Freshdesk')
# parser.add_argument('offset', action='store', type=int, nargs='?', default=0, help='Offset in days from today')
# parser.set_defaults(offset=0)
#
# args = parser.parse_args()
# report_date -= td(days=int(args.offset))
#
# print(report_date.strftime('%d %B %Y'))
#
# # Freshdesk
# # tz_shift = td(hours=config.getint('freshdesk', 'tz_shift'))
# # tz_shift += td(seconds=1)
# #
# # fd_id = config.get('freshdesk', 'agent_id')
# # fd_api_key = config.get('freshdesk', 'api_key')
# # fd_url = config.get('freshdesk', 'url')
# # fd_api_url = fd_url + '/api/v2/time_entries'
# # fd_params = {'agent_id': fd_id,
# #              'executed_after': (report_date - tz_shift).strftime('%Y-%m-%dT%H:%M:%SZ'),
# #              'executed_before': (report_date - tz_shift + td(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}
# #
# # try:
# #     try:
# #         s = requests.Session()
# #         s.mount('https://', HTTPAdapter(max_retries=5))
# #         ans = s.get(fd_api_url, params=fd_params, auth=(fd_api_key, 'X'), timeout=3)
# #     except requests.ConnectTimeout:
# #         print('Freshdesk connection timeout...')
# #         raise
# #
# #     time_entries = sorted(ans.json(), key=lambda k: (k.get('ticket_id'), k.get('updated_at')))
# #
# #     if time_entries:
# #         print("\nFRESHDESK:")
# #
# #     for entry in time_entries:
# #         print(
# #             f'''Ticket: {fd_url}/helpdesk/tickets/{entry['ticket_id']}'''
# #             f'''\n\t{'Billable' if entry.get('billable') else 'Not billable'}: {entry.get('time_spent')} {entry.get('note')}''')
# #         spent_dt = datetime.strptime(entry.get('time_spent'), '%H:%M')
# #         spent = td(hours=spent_dt.hour, minutes=spent_dt.minute)
# #         if entry.get('billable'):
# #             fd_bill_time += spent
# #         else:
# #             fd_free_time += spent
# #
# # except BaseException as e:
# #     print(e)
#
# # Jira
# jira_login = config.get('jira', 'login')
# jira_pass = config.get('jira', 'password')
#
# ans = requests.post('https://dev.latera.ru/rest/api/2/search',
#                     headers={"Content-Type": "application/json"},
#                     json={
#                         "jql": f'''worklogAuthor = {jira_login} AND worklogDate = {report_date.strftime('%Y-%m-%d')}''',
#                         "fields": ["key"],
#                         "maxResults": 1000},
#                     auth=HTTPBasicAuth(jira_login, jira_pass)).json()
#
# issues = ans.get('issues')
#
# if issues:
#     print("\nJIRA:")
#
#     for issue in ans['issues']:
#         ans = requests.get('https://dev.latera.ru/rest/api/2/issue/' +
#                            issue['key'] + '/worklog',
#                            auth=HTTPBasicAuth(jira_login, jira_pass)).json()
#         for worklog in ans['worklogs']:
#             if (worklog['author']['name'] == jira_login and
#                     worklog['started'].split('T')[0] == report_date.strftime('%Y-%m-%d')):
#                 time_spent = int(worklog['timeSpentSeconds'])
#                 print(('Issue:  https://dev.latera.ru/browse/' + issue['key']))
#                 print(('\tSpent: ' + td2srt(td(seconds=time_spent)) + 'Note: ' + worklog['comment']))
#                 jira_time += td(seconds=time_spent)

# Teamwork
tw_id = config.get('teamwork', 'agent_id')
tw_api_key = config.get('teamwork', 'api_key')

ans = requests.get('http://pm.hydra-billing.com/time_entries.json',
                   params={
                       'userId': tw_id,
                       'fromdate': report_date.strftime('%Y%m%d'),
                       'todate': report_date.strftime('%Y%m%d')
                   },
                   auth=HTTPBasicAuth(tw_api_key, 'X')).json()
entries = ans.get('time-entries')

if entries:
    print("\nTEAMWORK:")
    proj_name_len = max([len(s['project-name']) for s in entries])
    list_name_len = max([len(s['todo-list-name']) for s in entries])
    task_name_len = max([len(s['todo-item-name']) for s in entries])

    for entry in entries:
        entry_time = float(entry['hours']) + round(float(entry['minutes']) / 60.0, 2)
        if entry['isbillable'] == '1':
            tw_bill_time += entry_time
            entry['isbillable'] = 'True'
        else:
            tw_free_time += entry_time
            entry['isbillable'] = 'False'
        print(('Task:   http://pm.hydra-billing.com/#tasks/' + entry['todo-item-id']))
        print(('\tProject: ' + entry['project-name']))
        print(('\tList: ' + entry['todo-list-name'].ljust(list_name_len + 1) +
               ', Task: ' + entry['todo-item-name'].ljust(task_name_len + 1)))
        if len(entry['tags']) == 0:
            entry['tags'].append('')
        print(('\tTime: ' + str(entry_time) + ', Billable: ' +
               entry['isbillable'].ljust(5) + ', Tags: ' + ', '.join(entry['tags'][0])))
        print(('\tComment: ' + entry['description']))

total_tracked_time = (fd_bill_time +
                      fd_free_time +
                      jira_time +
                      tw_bill_time +
                      tw_free_time)


def str2dt(s):
    return datetime.combine(report_date.date(), datetime.strptime(s, '%H:%M').time())


workday_begin = str2dt(config.get('global', 'workday_begin'))
workday_end = str2dt(config.get('global', 'workday_end'))
launch_begin = str2dt(config.get('global', 'launch_begin'))
launch_end = str2dt(config.get('global', 'launch_end'))

launch_duration = launch_end - launch_begin
workday_duration = workday_end - workday_begin - launch_duration

if args.offset == 0 and workday_begin <= datetime.now() <= workday_end:
    total_time = datetime.now() - workday_begin
    if launch_begin <= datetime.now() <= launch_end:
        total_time = launch_begin - workday_begin
    if datetime.now() > launch_end:
        total_time -= launch_duration

    untracked_time = total_time - total_tracked_time
else:
    untracked_time = workday_duration - total_tracked_time
#
# print(f'''
# Total tracked time:    {td2srt(total_tracked_time)}
# - Freshdesk billable:  {td2srt(fd_bill_time)}
# - Freshdesk free:      {td2srt(fd_free_time)}
# - Teamwork billable:   {td2srt(tw_bill_time)}
# - Teamwork free:       {td2srt(tw_free_time)}
# - Jira:                {td2srt(jira_time)}
#
# Untracked time by now: {td2srt(untracked_time)}
# ''')
