#!/usr/bin/env python3
# Author: Markus muehlbauer

from __future__ import print_function
import datetime
import os.path
import pickle
import time
import schedule
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from phue import Bridge

# If modifying the scope, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
# Connect Philips Hue Bridge.
b = Bridge('192.168.178.66')
# Define user.
user_account = '123@google.com'
# Skip events created by these users.
blocked_creators = ['345@gmail.com']
# Room to be controlled by hue bridge.
hue_group = 'Office'
# Available scenes of this room.
heu_scene_meeting = 'Meeting'
heu_scene_meetingsoon = 'MeetingSoon'
hue_scene_meetinglater = 'MeetingLater'
hue_scene_chill = 'Chill'

def datetime2str(dt):
    return (dt).strftime('%Y-%m-%dT%H:%M:%S')

def str2datetime(st):
    return datetime.datetime.strptime(st, '%Y-%m-%dT%H:%M:%S')

def add_minutes(dt, min):
    return dt + datetime.timedelta(minutes=min)

def duration_minutes(start_dt, end_dt):
    return int((start_dt - end_dt).seconds / 60)

def sync_calendar_with_hue():
    # Get upcoming meetings from Calendar.
    creds = None
    event_dict = {}
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)

    # Call the Calendar API
    now = add_minutes(datetime.datetime.utcnow(), -200).isoformat() + 'Z' # 'Z' indicates UTC time
    print('Getting upcoming Calendar events:')
    events_result = service.events().list(calendarId='primary', timeMin=now,
                                        maxResults=20, singleEvents=True,
                                        orderBy='startTime').execute()
    events = events_result.get('items', [])
    if not events:
        print('No upcoming events found.')


    # Create a sorted event dict.
    for event in events:
        id          = event.get('id', '')[0:26]
        attendees   = event.get('attendees', [])
        creator     = event.get('creator', {})
        hangoutLink = event.get('hangoutLink', '')
        summary     = event.get('summary', '')
        responseStatus = ''
        # Get event response status.
        for attendee in attendees:
            if attendee['email'] == user_account:
                responseStatus = attendee['responseStatus']
        # Check if event is accepted, with a hangouts link, not created by blocked creators and more than 1 participatns.
        if responseStatus == 'accepted' and hangoutLink != '' and creator['email'] not in blocked_creators and (len(attendees) > 1 or summary.find('Interview') != -1):
            start = event['start'].get('dateTime', event['start'].get('date'))[:-6]
            end = event['end'].get('dateTime', event['end'].get('date'))[:-6]
            start_datetime = str2datetime(start)
            end_datetime = str2datetime(end)
            end_minute = int(end_datetime.strftime('%M'))
            end_day = int(end_datetime.strftime('%d'))
            now_day = int(datetime.datetime.now().strftime('%d'))
            now = datetime.datetime.now()
            # Round up end time to full half hour.
            if end_minute > 0 and end_minute<= 29:
                end_datetime = add_minutes(end_datetime, 30 - end_minute)
                end = datetime2str(end_datetime)
            # Round up end time to full hour.
            if end_minute > 30 and end_minute <= 59:
                end_datetime = add_minutes(end_datetime, 60 - end_minute)
                end = datetime2str(end_datetime)
            # Set start to now if meeting has already started.
            if start_datetime <= now and end_datetime > now:
                start_datetime = now
                start = datetime2str(start_datetime)
            # Calculate meeting duration
            duration = int((end_datetime - start_datetime).seconds / 60)
            # Only continue for running or upcoming events on the same day.
            if end_day == now_day and end_datetime > now:
                event_detail = {}
                event_detail['title'] = event['summary']
                event_detail['start'] = start
                event_detail['end'] = end
                event_detail['duration'] = duration
                event_detail['before'] = 0
                # Default value to indicate last event of day.
                event_detail['after'] = 999
                # Add event details to dict.
                event_dict[start+id] = event_detail
            
        
    # Calculate time before and after each meeting.
    last_event_id = ''
    for event, v in sorted(event_dict.items()):
        start = str2datetime(event_dict[event]['start'])
        end = str2datetime(event_dict[event]['end'])
        # Calculate time before the meeting.
        if last_event_id == '':
            if start < datetime.datetime.now():
                before = 0
            else:
                before = duration_minutes(start, datetime.datetime.now())
        else:
            last_end = str2datetime(event_dict[last_event_id]['end'])
            if last_end > start_datetime:
                before = 0
            else:
                before = duration_minutes(start, last_end)
        event_dict[event]['before'] = before
        # Resolve overlapping events
        for check_event, v in sorted(event_dict.items()):
            check_start = str2datetime(event_dict[check_event]['start'])
            check_end = str2datetime(event_dict[check_event]['end'])
            if check_start < start and check_end > start:
                event_dict[event]['before'] = 0
            if check_end > end and check_start < end:
                event_dict[event]['after'] = 0

        # Set time after the meeting for previous event.
        if last_event_id != '':
            event_dict[last_event_id]['after'] = before
        last_event_id = event
        
    #Print Final Event List
    for event, v in sorted(event_dict.items()):       
        print('Start: '        + event_dict[event]['start'] \
              + ', End: '      + event_dict[event]['end'] \
              + ', Duration: ' + str(event_dict[event]['duration']) \
              + ', Before: '   + str(event_dict[event]['before']) \
              + ', After: '    + str(event_dict[event]['after']) \
              + ', Title: '    + event_dict[event]['title'])


    # Setup Schedule for Philips Hue lights.
    print('')
    print('Set Hue Schedule:')
    # If the app is not registered and the button is not pressed, press the
    # button and call connect() (this only needs to be run a single time)
    b.connect()
    # Get available groups.
    groups = b.get_group()
    groups_dict = {}
    for key in groups:
        groups_dict[groups[key]['name']] = key
    # Get available scenes and load into a dictionary.
    scenes = b.get_scene()
    scenes_dict = {}
    for key in scenes:
        scenes_dict[scenes[key]['name']] = key
    # Delete old schedules creted by this script.
    count =  0
    schedules = b.get_schedule()
    #print(schedules)
    for schedule in schedules:
        if schedules[schedule]['description'] == 'Calendar':
            b.delete_schedule(schedule)
            count += 1
    print(str(count) + ' remaining schedules deleted.')
    print('')
    # Set new schedules for each meeting.
    first_event = True
    count = 0
    for event,v in sorted(event_dict.items()):
        #print(event_dict)
        # Indicate upcoming meetings before first meeting.
        if first_event:
            data = {'on': True, 'scene': scenes_dict[hue_scene_meetinglater]}
            start = datetime2str(datetime.datetime.now())
            # Only set schedule if meeting is more than 10 minutes away.
            if datetime.datetime.now() < add_minutes(str2datetime(event_dict[event]['start']), -10):
                b.create_group_schedule(event+'_first', start, groups_dict[hue_group], data, 'Calendar' )
                print('Start: ' + start + ' Scene: ' + hue_scene_meetinglater)
            first_event = False
        # Indicate meeting to start soon if there was a >10 min break between meetings.
        if event_dict[event]['before'] >= 10:
            start = add_minutes(str2datetime(event_dict[event]['start']), -10)
            start = datetime2str(start)
            data = {'on': True, 'scene': scenes_dict[heu_scene_meetingsoon]}
            b.create_group_schedule(event+'_soon', start, groups_dict[hue_group], data, 'Calendar' )
            count += 1
            print('Start: ' + start + ' Scene: ' + heu_scene_meetingsoon)
        # Start actual meeting.
        data = {'on': True, 'scene': scenes_dict[heu_scene_meeting]}
        start = event_dict[event]['start']
        b.create_group_schedule(event+'_on', start, groups_dict[hue_group], data, 'Calendar' )
        count += 1
        print('Start: ' + start + " Scene: " + heu_scene_meeting)
        if event_dict[event]['after'] == 999:
            # Last meeting of the day - switch into Chill mode 3 min after meeting.
            data = {'on': True, 'scene': scenes_dict[hue_scene_chill]}
            start = add_minutes(str2datetime(event_dict[event]['end']), 3)
            start = datetime2str(start)
            b.create_group_schedule(event+'_last', start, groups_dict[hue_group], data, 'Calendar' )
            count += 1
            print('Start: ' + start + ' Scene: ' + hue_scene_chill)
            # Turn off lights at 10pm.
            data = {'on': False}
            start = datetime.datetime.now().strftime('%Y-%m-%d')+'T22:00:00'
            b.create_group_schedule(event+'_off', start, groups_dict[hue_group], data, 'Calendar' )
            count += 1
            print('Start: ' + start + ' Scene: ' + 'OFF')
        else:
            # more meetings to come  - signalized more meetings.
            if event_dict[event]['after'] >= 1:
                data = {'on': True, 'scene': scenes_dict[hue_scene_meetinglater]}
                # Allow meetings to run over for 3 minutes.
                start = add_minutes(str2datetime(event_dict[event]['end']), 3)
                start = datetime2str(start)
                b.create_group_schedule(event+'_more', start, groups_dict[hue_group], data, 'Calendar' )
                count += 1
                print('Start: ' + start + ' Scene: ' + hue_scene_meetinglater)

    print('')
    print(str(len(b.get_schedule())) + ' of ' + str(count) + ' schedule(s) created.')

def main():
    sync_calendar_with_hue()

if __name__ == '__main__':
    main()
