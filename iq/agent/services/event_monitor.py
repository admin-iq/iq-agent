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
import select
import socket
import subprocess
import xml.etree.ElementTree as ET

from platform import uname_result
if platform.system() == 'Windows':
    import win32evtlog
    
from tenacity import AsyncRetrying
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
    
    def event_callback(self, action, context, event):
        """
        Callback function that gets called when an event is received.
        """
        if action == win32evtlog.EvtSubscribeActionDeliver:
            # Render the event to get its details
            rendered_event = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
            logging.info(rendered_event)  # Print the event details

            # Parse the event XML
            root = ET.fromstring(rendered_event)
            # Convert to dictionary
            dict_data = self.xml_to_dict(root)

            # Convert the event to a log event
            log_event = self.to_log_event(dict_data) 

            logging.info(dict_data)       
            self.send_event(log_event)


    async def subscribe(self) -> None:
        '''
        Run the event log monitor.
        '''

        # Create the event log session. --todo clean up seesion
        query = "*[System[(Level=1 or Level=2)]]"  # Example query: Critical and Error events
        session = win32evtlog.EvtSubscribe(
            'System',  # The name of the log to subscribe to
            win32evtlog.EvtSubscribeToFutureEvents,  # Subscribe to future events
            None,
            self.event_callback,
            None,
            query
        )

        logging.info("Subscribed to event log")

        # Run the subscribe forever.
        while True:
            # Wait for the interval.
            await asyncio.sleep(1)

    async def send_event(self, entry: 'LogEvent') -> None:
        # Serialize the entry.
        payload: bytes = self.to_log_event(entry) \
                             .model_dump_json() \
                             .encode('utf-8')

        # Sign the result.
        signature: str = self._security.sign(payload)

        # Define the request headers.
        headers: dict[str, str] = self._headers.copy()
        headers['Content-Type'] = 'application/json'
        headers['Signature'] = signature

        # Send the entry to the service.
        try:
            async for attempt in AsyncRetrying(stop=stop_after_attempt(self._retries)):
                with attempt:
                    async with aiohttp.ClientSession() as session:
                        url: str = self._url
                        async with session.post(url,
                                                headers=headers,
                                                data=payload,
                                                timeout=self._timeout) as response:
                            # Check if the request was not successful.
                            if response.status != 201:
                                error: dict[str, any] = await response.json()
                                self._logger.error(
                                    'Failed to send the system log event. Code: %s Reason: %s',
                                    response.status, json.dumps(error['detail'], indent=4))
        except RetryError as error:
            self._logger.exception(error)

    def xml_to_dict(self, elem, dict_data = None) -> dict:
        if dict_data is None:
            dict_data = {}
        for child in elem:
            if len(child) == 0:  # If the child has no children of its own
                dict_data[child.tag] = child.text
            else:  # If the child has its own children, recurse
                dict_data[child.tag] = self.xml_to_dict(child, {})
        return dict_data

    def to_log_event(self, entry: any) -> 'LogEvent':
        '''
        Convert a event entry to a log event.
        '''

        # Create a list of log properties.
        properties: 'list[LogProperty]' = []
        for name, value in entry.items():
            # Convert the key to lowercase.
            name = name.lower()

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
            source='event_log',
            properties=properties
        )