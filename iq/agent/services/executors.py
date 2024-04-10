'''
This module provides the server command executor service.
'''

from datetime import datetime
from logging import Logger
from subprocess import CompletedProcess

import json
import logging
import subprocess

from tenacity import AsyncRetrying
from tenacity import RetryError
from tenacity import stop_after_attempt

import aiohttp

from iq.agent.models import ServerCommand
from iq.agent.models import ServerCommandResult
from iq.agent.security import SecurityProvider


class ShellExecutor:
    '''
    Consumes commands from the service and executes them on behalf of the user.
    '''
    def __init__(self,
                 url: str,
                 security: 'SecurityProvider',
                 poll_timeout=300,
                 reply_retries=3,
                 reply_timeout=300):

        # Initialize the logger.
        self._logger: Logger = logging.getLogger(__name__)

        # Set the default headers.
        self._headers: dict[str, str] = {
            'Authorization': f'Bearer {security.access_token}',
            'Client-ID': security.client_id
        }

        # Set the service URL.
        self._url: str = url

        # Set the polling timeout.
        self._poll_timeout: int = poll_timeout

        # Set the number of reply retries.
        self._reply_retries: int = reply_retries

        # Set the reply timeout.
        self._reply_timeout: int = reply_timeout

        # Set the security provider.
        self._security: SecurityProvider = security

    def execute(self, command: 'ServerCommand'):
        '''
        Executes a command.
        '''

        # Save the start time.
        start: datetime = datetime.now()

        # Execute the command.
        process: CompletedProcess = subprocess.run(
            command.command,
            capture_output=True,
            check=False,
            shell=True,)

        # Save the end time.
        end: datetime = datetime.now()

        # Calculate the total time.
        total: float = (end - start).total_seconds()

        # Create a result for the command.
        return ServerCommandResult(
            start_date=start,
            end_date=end,
            total_time=total,
            exit_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr
        )

    async def poll(self):
        '''
        Polls the service for commands to execute.
        '''

        async with aiohttp.ClientSession() as session:
            url: str = f'{self._url}?status=pending'
            async with session.get(url,
                                   headers=self._headers,
                                   timeout=self._poll_timeout) as response:
                # Check if the request was not successful.
                if response.status != 200:
                    self._logger.error(
                        'Failed to poll the service. Code: %s Reason: %s',
                        response.status, response.reason)
                    return []

                # Parse the commands from the response.
                commands: 'list[dict[str, any]]' = await response.json()
                commands: 'list[ServerCommand]' = [
                    ServerCommand(**command) for command in commands]

                # Return the commands.
                return commands

    async def run(self):
        '''
        Polls the service for commands to execute.
        '''

        commands: 'list[ServerCommand]' = await self.poll()

        for command in commands:
            # Execute the command.
            result: ServerCommandResult = self.execute(command)

            # Encode the result as bytes.
            payload: bytes = result.model_dump_json().encode('utf-8')

            # Sign the result.
            signature: str = self._security.sign(payload)

            # Define the request headers.
            headers: dict[str, str] = self._headers.copy()
            headers['Content-Type'] = 'application/json'
            headers['Signature'] = signature

            # Send the result to the service.
            try:
                async for attempt in AsyncRetrying(stop=stop_after_attempt(self._reply_retries)):
                    with attempt:
                        async with aiohttp.ClientSession() as session:
                            url: str = f'{self._url}{command.id}/result/'
                            async with session.post(url,
                                                    headers=headers,
                                                    data=payload,
                                                    timeout=self._reply_timeout) as response:
                                # Check if the request was not successful.
                                if response.status != 201:
                                    error: dict[str, any] = await response.json()
                                    self._logger.error(
                                        'Failed to send the result. Code: %s Reason: %s',
                                        response.status, json.dumps(error['detail'], indent=4))
            except RetryError as error:
                self._logger.exception(error)
