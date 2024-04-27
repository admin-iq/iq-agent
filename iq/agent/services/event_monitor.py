'''
This module is responsible for collecting system information from windows event log and send it to the service.
'''

from datetime import datetime
from datetime import timedelta
from logging import Logger

import asyncio
import json
import logging
import platform
import requests
import select
import socket
import subprocess
import xml.etree.ElementTree as ET

from platform import uname_result
if platform.system() == 'Windows':
    import win32evtlog
    import win32evtlogutil
    
from tenacity import Retrying
from tenacity import RetryError
from tenacity import stop_after_attempt

import aiohttp
import psutil
import cpuinfo

from iq.agent.models import LogEvent
from iq.agent.models import LogProperty
from iq.agent.security import SecurityProvider

class EventLogMonitor:
    '''
    This class is responsible for monitoring the event log.
    '''

    def __init__(self,
                 url: str,
                 security: 'SecurityProvider',
                 retries=3,
                 timeout=300) -> None:

        # Initialize the logger.
        self._logger: Logger = logging.getLogger(__name__)

        # Set the default headers.
        self._headers: dict[str, str] = {
            'Authorization': f'Bearer {security.access_token}',
            'Client-ID': security.client_id
        }

        # Set the service URL.
        self._url: str = url

        # Set the number of retries.
        self._retries: int = retries

        # Set the timeout.
        self._timeout: int = timeout

        # Set the security provider.
        self._security: SecurityProvider = security

        self._running = True

    def get_event_by_record_id(self, event_record_id, level, logtype):
        # Open the event log
        handle = win32evtlog.OpenEventLog(None, logtype)

        # Set the offset to read events starting from the desired event number
        flags = win32evtlog.EVENTLOG_SEEK_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
        evtLogs = win32evtlog.ReadEventLog(handle, flags, event_record_id, 1)

        if evtLogs:
            message = win32evtlogutil.SafeFormatMessage(evtLogs[0], logtype)
            log_event = self.to_log_event(evtLogs[0], message, level)
            self.send_event(log_event)
        else:
            self._logger.error("Failed to find event with record number %d", event_record_id)
        
        win32evtlog.CloseEventLog(handle)

  
    def event_callback(self, action, context, event, logtype):
        """
        Callback function that gets called when an event is received.
        """
        if action == win32evtlog.EvtSubscribeActionDeliver:
            #logtype = "System"
            print (f"Event received from {logtype} log")
            
            # Render the event to get its event record number
            rendered_event = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
            
            # Parse the event XML
            root = ET.fromstring(rendered_event)

            # Extract the namespace URI from the root element to get record number and level element
            namespace_uri = root.tag.split('}')[0][1:]
            element_name = 'EventRecordID'
            element_level = 'Level'
            event_record_id = root.find(f".//{{{namespace_uri}}}{element_name}")
            event_level = root.find(f".//{{{namespace_uri}}}{element_level}")

            if event_record_id is not None:
                self.get_event_by_record_id(int(event_record_id.text), event_level.text, logtype)

    async def subscribe_system(self) -> None:
        '''
        Run the event log monitor.
        '''

        # Create the event log session. --todo clean up seesion
        query = "*[System[(Level=1 or Level=2)]]"  # Example query: Critical and Error events
        session = win32evtlog.EvtSubscribe(
            'System',  # The name of the log to subscribe to
            win32evtlog.EvtSubscribeToFutureEvents,  # Subscribe to future events
            None,
            lambda action, context, event: self.event_callback(action, context, event, 'System'),
            None,
            query
        )

        logging.info("Subscribed to event log")

        # Run the subscribe forever.
        while self._running:
            # Wait for the interval.
            await asyncio.sleep(1)

    async def stop(self) -> None:
        '''
        Stop the event log monitor.
        '''
        self._running = False

    def send_event(self, entry: 'LogEvent') -> None:
        # Serialize the entry.
        payload: bytes = entry.model_dump_json().encode('utf-8')

        # Sign the result.
        signature: str = self._security.sign(payload)

        # Define the request headers.
        headers: dict[str, str] = self._headers.copy()
        headers['Content-Type'] = 'application/json'
        headers['Signature'] = signature

        # Send the entry to the service.
        try:
            for attempt in Retrying(stop=stop_after_attempt(self._retries)):
                with attempt:
                    response = requests.post(self._url, headers=headers, data=payload, timeout=self._timeout)
                    # Check if the request was not successful.
                    print(response.status_code)
                    if response.status_code != 201:
                        error = response.json()
                        self._logger.error(
                            'Failed to send the system log event. Code: %s Reason: %s',
                            response.status_code, json.dumps(error.get('detail', ''), indent=4))
                        # You might want to raise an exception here to trigger a retry
                        raise Exception("Failed to send event")
        except RetryError as error:
            self._logger.exception(error)

    def to_log_event(self, entry: any, message: str, level: str) -> 'LogEvent':
        '''
        Convert a event entry to a log event.
        '''
        # Create a list of log properties.
        properties: 'list[LogProperty]' = []
        properties.append(LogProperty(name="message", value=message))
        properties.append(LogProperty(name="priority", value=level))
        # Loop through the record to access its members
        for member in dir(entry):
            if not member.startswith('__') and member in ['ClosingRecordNumber','Data','EventCategory','EventID','EventType', 'RecordNumber', 'Reserved', 'ReservedFlags','Sid','SourceName','TimeGenerated','TimeWritten']:
                value = getattr(entry, member)
                print(f"{member}: {value}")
        
                # Convert the key to lowercase.
                name = member.lower()

                # Convert the value to a string.
                if isinstance(value, datetime):
                    value = value.isoformat()
                else:
                    value = str(value)

                if self._logger.isEnabledFor(logging.DEBUG):
                   self._logger.debug('Adding property: %s=%s', name, value)

                # Add the property to the list.
                properties.append(LogProperty(name=name, value=value))

        # Return the log event.
        return LogEvent(
            source='journald',
            properties=properties
        )