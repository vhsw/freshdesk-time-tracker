# Freshdesk
import configparser
import os
from datetime import timedelta, datetime

import requests

config = configparser.RawConfigParser()
config.read(os.path.join(os.path.dirname(__file__), 'config.ini'))

freshdesk_api_key = config.get('freshdesk', 'api_key')


def get_timesheet(last_update=None):
    fd_url = 'https://{company}.freshdesk.com/api/v2/time_entries?executed_after=2018-02-14T13:00:00Z&agent_id={freshdesk_id}'.format(
        company=config.get('freshdesk', 'company'), freshdesk_id=config.get('freshdesk', 'agent_id'))

    try:
        ans = requests.get(fd_url,
                           auth=(freshdesk_api_key, 'X'))
    except requests.exceptions.RequestException as e:
        print(e)

    else:
        res = []
        for item in ans.json():
            t = item['time_entry']
            entry = {'id': None,
                     'billable_t': timedelta(0),
                     'nonbillable_t': timedelta(0),
                     'updated_at': datetime.min,
                     'note': ''

                     }
            entry
        if last_update:
            return None
