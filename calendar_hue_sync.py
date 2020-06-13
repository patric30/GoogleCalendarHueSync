from __future__ import print_function
import datetime
import pickle
import os.path
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
user_email = 'muehlbauer@google.com'
# Skip events created by these creators.
blocked_creators = ['cortina1996@gmail.com']
# Room to be controlled by hue bridge.
hue_group = 'Office'
# Available Scenes of this Room.
heu_scene_meeting = 'Meeting'
heu_scene_meetingsoon = 'MeetingSoon'
hue_scene_meetinglater = 'MeetingLater'
hue_scene_chill = 'Chill'

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
    now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
    print('Getting upcoming Calendar events:')
    events_result = service.events().list(calendarId='primary', timeMin=now,
                                        maxResults=20, singleEvents=True,
                                        orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        print('No upcoming events found.')
    # Identify VC events and add into list.
    last_event_id = ''
    for event in events:
        id          = event.get('id', '')
        attendees   = event.get('attendees', [])
        creator     = event.get('creator', {})
        hangoutLink = event.get('hangoutLink', '')
        responseStatus = ''
        for attendee in attendees:
            if attendee['email'] == user_email:
                responseStatus = attendee['responseStatus']
        # Check if event is accepted, with a hangouts link, not created by blocked creators and more than 1 participatns.
        if responseStatus == 'accepted' and hangoutLink != '' and creator['email'] not in blocked_creators and len(attendees) > 1:
            start = event['start'].get('dateTime', event['start'].get('date'))[:-6]
            end = event['end'].get('dateTime', event['end'].get('date'))[:-6]
            start_datetime = datetime.datetime.strptime(start, '%Y-%m-%dT%H:%M:%S')
            end_datetime = datetime.datetime.strptime(end, '%Y-%m-%dT%H:%M:%S')
            end_minute = int(end_datetime.strftime('%M'))
            end_day = int(end_datetime.strftime('%d'))
            now_day = int(datetime.datetime.now().strftime('%d'))
            # Round up end time to full half hour.
            if end_minute > 0 and end_minute<= 29:
                end_datetime = end_datetime + datetime.timedelta(minutes=30 - end_minute)
                end = (end_datetime).strftime('%Y-%m-%dT%H:%M:%S')
            # Round up end time to full hour.
            if end_minute > 30 and end_minute <= 59:
                end_datetime = end_datetime + datetime.timedelta(minutes=60 - end_minute)
                end = (end_datetime).strftime('%Y-%m-%dT%H:%M:%S')
            # Set start to now+1 if meeting has already started.
            if start_datetime <= datetime.datetime.now():
                start_datetime = datetime.datetime.now() + datetime.timedelta(minutes=1)
                start = (start_datetime).strftime('%Y-%m-%dT%H:%M:%S')
            # Calculate meeting duration
            duration = int((end_datetime - start_datetime).seconds / 60)
            # Calculate time before the meeting.
            if last_event_id == '':
                before = int((start_datetime - datetime.datetime.now()).seconds / 60)
            else:
                before = int((start_datetime - datetime.datetime.strptime(event_dict[last_event_id]['end'], '%Y-%m-%dT%H:%M:%S')).seconds / 60)
            # Only continue for events on the same day.
            if end_day == now_day:
                event_detail = {}
                event_detail['title'] = event['summary']
                event_detail['start'] = start
                event_detail['end'] = end
                event_detail['duration'] = duration
                event_detail['before'] = before
                # Default value to indicate last event of day.
                event_detail['after'] = 999
                # Add event details to dict.
                event_dict[id] = event_detail
                print('Start: ' + start + ', End: ' + end + ', Duration: ' + str(duration) + ', Before: ' + str(before) + ', Title: ' + event['summary'])
                # Set time after the meeting for previous event.
                if last_event_id != '':
                    event_dict[last_event_id]['after'] = before
                last_event_id = id
            else:
                # Exit loop after last event of the day
                break

    # Setup Schedule for Philips Hue lights.
    print('')
    print('Set Hue Schedule:')
    # If the app is not registered and the button is not pressed, press the button and call connect() (this only needs to be run a single time)
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
    for schedule in schedules:
        if schedules[schedule]['description'] == 'Calendar':
            b.delete_schedule(schedule)
            count += 1
    if count > 0:
        print(str(count) + ' schedules deleted.')
        print('')
    # Set new schedules for each meeting.
    first_event = True
    for event in event_dict:
        # Indicate upcoming meetings before first meeting.
        if first_event:
            data = {'on': True, 'scene': scenes_dict[hue_scene_meetinglater]}
            start = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            # Only set schedule if meeting is more than 10 minutes away.
            if datetime.datetime.now() < datetime.datetime.strptime(event_dict[event]['start'], '%Y-%m-%dT%H:%M:%S') - datetime.timedelta(minutes=10):
                b.create_group_schedule(event+'_first', start, groups_dict[hue_group], data, 'Calendar' )
                print('Start: ' + start + ' Scene: ' + hue_scene_meetinglater)
            first_event = False
        # Indicate meeting to start soon if there was a >10 min break between meetings.
        if event_dict[event]['before'] >= 10:
            start = datetime.datetime.strptime(event_dict[event]['start'], '%Y-%m-%dT%H:%M:%S') - datetime.timedelta(minutes=10)
            start = (start).strftime('%Y-%m-%dT%H:%M:%S')
            data = {'on': True, 'scene': scenes_dict[heu_scene_meetingsoon]}
            b.create_group_schedule(event+'_on', start, groups_dict[hue_group], data, 'Calendar' )
            print('Start: ' + start + ' Scene: ' + heu_scene_meetingsoon)
        data = {'on': True, 'scene': scenes_dict[heu_scene_meeting]}
        start = event_dict[event]['start']
        b.create_group_schedule(event+'_on', start, groups_dict[hue_group], data, 'Calendar' )
        print('Start: ' + start + " Scene: " + heu_scene_meeting)
        if event_dict[event]['after'] == 999:
            # Last meeting of the day - switch into Gaming mode.
            data = {'on': True, 'scene': scenes_dict[hue_scene_chill]}
            start = event_dict[event]['end']
            b.create_group_schedule(event+'_last', start, groups_dict[hue_group], data, 'Calendar' )
            print('Start: ' + start + ' Scene: ' + hue_scene_chill)
            # Turn off lights at 10pm.
            data = {'on': False}
            start = datetime.datetime.now().strftime('%Y-%m-%d')+'T23:00:00'
            b.create_group_schedule(event+'_off', start, groups_dict[hue_group], data, 'Calendar' )
            print('Start: ' + start + ' Scene: ' + 'OFF')
        else:
            # more meetings to come  - signalized more meetings.
            if event_dict[event]['after'] >= 1:
                data = {'on': True, 'scene': scenes_dict[hue_scene_meetinglater]}
                start = event_dict[event]['end']
                b.create_group_schedule(event+'_more', start, groups_dict[hue_group], data, 'Calendar' )
                print('Start: ' + start + ' Scene: ' + hue_scene_meetinglater)

    print('')
    print('Done.')

def main():
    sync_calendar_with_hue()

if __name__ == '__main__':
    main()
