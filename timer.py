#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os.path
from datetime import datetime, date, timedelta

import requests
from requests.auth import HTTPBasicAuth

# Variables
total_time = 0
bill_time_fd = 0
free_time_fd = 0
time_jira = 0
bill_time_tw = 0
free_time_tw = 0


def hours2hhmm(f_hours):
    return '{0:02d}:{1:02d}'.format(int(f_hours), int((f_hours * 60) % 60))


# Files to store credentials
credents_fd = os.path.expanduser("~/.freshdesk_credentials")
credents_jr = os.path.expanduser("~/.jira_credentials")
credents_tw = os.path.expanduser("~/.teamwork_credentials")

# Load/ask Freshdesk credentials
try:
    with open(credents_fd) as f:
        data = f.readlines()
        data = [s.strip() for s in data]
    agent_id = str(data[0])
    api_key = str(data[1])
except:
    agent_id = input("Enter your agent ID in freshdesk: ")
    api_key = input("Enter your API key (found at https://"
                    "support.hydra-billing.com/profiles/"
                    + agent_id + "/): ")
    with open(credents_fd, 'w+') as f:
        f.write(agent_id + '\n' + api_key)

# Load/ask Jira credentials
try:
    with open(credents_jr) as f:
        data = f.readlines()
        data = [s.strip() for s in data]
    login_jira = str(data[0])
    passw_jira = str(data[1])
except:
    login_jira = input("Enter your JIRA login: ")
    passw_jira = input("Enter your JIRA password: ")
    with open(credents_jr, 'w+') as f:
        f.write(login_jira + '\n' + passw_jira)

# Load/ask Teamwork credentials
try:
    with open(credents_tw) as f:
        data = f.readlines()
        data = [s.strip() for s in data]
    tw_id = str(data[0])
    tw_key = str(data[1])
except:
    tw_id = input("Enter your agent ID in teamwork: ")
    tw_key = input("Enter your API key (found at http://"
                   "pm.hydra-billing.com/#/people/"
                   + tw_id + "/details -> Edit My Profile -> API&Mobile): ")
    with open(credents_tw, 'w+') as f:
        f.write(tw_id + '\n' + tw_key)

date = date.today()

parser = argparse.ArgumentParser(description='Simple time tracker for Freshdesk')
parser.add_argument('offset', action='store', type=int, nargs='?', default=0, help='Offset in days from today')
parser.set_defaults(offset=0)

results = parser.parse_args()

date -= timedelta(days=int(results.offset))

print(date.strftime('%d %B %Y'))

# Freshdesk
ans1 = None
ans2 = None
times = None
try:
    ans1 = requests.get('https://latera.freshdesk.com/helpdesk/'
                        'time_sheets.json?agent_id=' + agent_id + '&billable=true',
                        auth=(api_key, 'X'))

    ans2 = requests.get('https://latera.freshdesk.com/helpdesk/'
                        'time_sheets.json?agent_id=' + agent_id + '&billable=false',
                        auth=(api_key, 'X'))

except requests.exceptions.RequestException as e:
    print(e)
if ans1 and ans2:
    times = sorted(ans1.json() + ans2.json(), key=lambda k: k['time_entry']['ticket_id'])

if times:
    print("\nFRESHDESK:")

    for time in times:
        time = time['time_entry']
        day = datetime.strptime(time['executed_at'].split('T')[0], '%Y-%m-%d')
        if day.date() == date:
            print(("Ticket: https://support.hydra-billing.com/helpdesk/tickets/" + str(time['ticket_id'])))
            print(("\tBillable: " + str(time['billable']).ljust(7) + "Spent: " +
                   hours2hhmm(float(time['timespent'])).ljust(6) + ' Client: ' +
                   time['customer_name'].ljust(16) + 'Note: ' + time['note']))

            if (time['billable']):
                bill_time_fd += float(time['timespent'])
            else:
                free_time_fd += float(time['timespent'])

# Jira
ans = requests.post('https://dev.latera.ru/rest/api/2/search',
                    headers={"Content-Type": "application/json"},
                    json={"jql": "worklogAuthor = " + login_jira +
                                 " AND worklogDate = " + date.strftime('%Y-%m-%d'),
                          "fields": ["key"],
                          "maxResults": 1000},
                    auth=HTTPBasicAuth(login_jira, passw_jira)).json()

issues = ans['issues']

if issues:
    print("\nJIRA:")

    for issue in ans['issues']:
        ans = requests.get('https://dev.latera.ru/rest/api/2/issue/' +
                           issue['key'] + '/worklog',
                           auth=HTTPBasicAuth(login_jira, passw_jira)).json()
        for worklog in ans['worklogs']:
            if (worklog['author']['name'] == login_jira and
                    worklog['started'].split('T')[0] == date.strftime('%Y-%m-%d')):
                time_spent = round(float(worklog['timeSpentSeconds']) / 3600.0, 2)
                print(('Issue:  https://dev.latera.ru/browse/' + issue['key']))
                print(('\tSpent: ' + hours2hhmm(time_spent).ljust(6) + 'Note: ' + worklog['comment']))
                time_jira += time_spent

# Teamwork
ans = requests.get('http://pm.hydra-billing.com/time_entries.json',
                   params={
                       'userId': tw_id,
                       'fromdate': date.strftime('%Y%m%d'),
                       'todate': date.strftime('%Y%m%d')
                   },
                   auth=HTTPBasicAuth(tw_key, 'X')).json()
entries = ans['time-entries']

if entries:
    proj_name_len = max([len(s['project-name']) for s in entries])
    list_name_len = max([len(s['todo-list-name']) for s in entries])
    task_name_len = max([len(s['todo-item-name']) for s in entries])

    print("\nTEAMWORK:")

    for entry in entries:
        entry_time = float(entry['hours']) + round(float(entry['minutes']) / 60.0, 2)
        if entry['isbillable'] == '1':
            bill_time_tw += entry_time
            entry['isbillable'] = 'True'
        else:
            free_time_tw += entry_time
            entry['isbillable'] = 'False'
        print(('Task:   http://pm.hydra-billing.com/#tasks/' + entry['todo-item-id']))
        print(('\tProject: ' + entry['project-name']))
        print(('\tList: ' + entry['todo-list-name'].ljust(list_name_len + 1) +
               ', Task: ' + entry['todo-item-name'].ljust(task_name_len + 1)))
        if len(entry['tags']) == 0:
            entry['tags'].append('')
        print(('\tTime: ' + hours2hhmm(entry_time) + ', Billable: ' +
               entry['isbillable'].ljust(5) + ', Tags: ' + ', '.join(entry['tags'][0])))
        print(('\tComment: ' + entry['description']))

total_time += (bill_time_fd +
               free_time_fd +
               time_jira +
               bill_time_tw +
               free_time_tw)

if date == date.today() and 10 < datetime.now().hour < 19:
    tracked_time = datetime.combine(date, datetime.min.time())
    tracked_time += timedelta(hours=10) + timedelta(hours=total_time)
    if datetime.now().hour > 13:
        tracked_time += timedelta(hours=1)

    tdelta = datetime.now() - tracked_time
else:
    tdelta = timedelta(hours=(8 - total_time))

print('\n\nTotal tracked time: ' + hours2hhmm(total_time))
print('Untracked time by now: {0:02d}:{1:02d}'.format(tdelta.seconds // 3600, tdelta.seconds % 3600 // 60))
print('Of which: ')
print('- Freshdesk billable: ' + hours2hhmm(bill_time_fd))
print('- Freshdesk free: ' + hours2hhmm(free_time_fd))
print('- Jira: ' + hours2hhmm(time_jira))
print('- Teamwork billable: ' + hours2hhmm(bill_time_tw))
print('- Teamwork free: ' + hours2hhmm(free_time_tw))
