# GoogleCalendarHueSync
Synchronize Google Calendar Meetings with Hue Lights

Steps:
1. Get Philips 7820330U7_2 Hue Play Bar and a Philips Hue Bridge.
2. Setup Calandar API access for your Google Calendar: https://developers.google.com/calendar/quickstart/python
(If you are a Google Employee you need to request Cloud Platforms exyperiments to be enabled to access Calendar API for your corp account. Follow steps in the "Caller does not have permission" error message.)
3. Install phue API library: sudo pip install phue.
4. Get IP address of your Philips Hue bridge and enter into python script.
5. Setup a Room called "Office" in your Hue app with all lights added.
6. Setup Scenes for the room
    - MeetingLater (indicates that there is an upcoming meeting)
    - MeetingSoon (indicates that the meeting will start in 10 minutes)
    - Meeting (Light setting during the meeting)
    - Chill (Light setting after the last meeting of the day)
    See sample scenes in the image. 
7. Select light settings for each scene.
8. Press Connect Button on bridge before first run.
9. Use Cron to run the script every e.g. 15 minutes to update light schedules.
10. Enjoy.
