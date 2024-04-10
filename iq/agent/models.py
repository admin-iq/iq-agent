'''
This module provides the pydantic models for communicating with the AdminIQ API.
'''

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID
from uuid import uuid4

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_serializer


class LogProperty(BaseModel):
    '''
    Defines a log property.
    '''

    # The property name.
    name: str = Field(description='The property name.')

    # The property value.
    value: str = Field(description='The property value.')

class LogEvent(BaseModel):
    '''
    Defines a log event.
    '''

    # The date and time the account was created.
    event_date: datetime = Field(
        default_factory=datetime.now,
        description='The date and time the account was created')

    # The source of the event.
    source: str = Field(description='The source of the event.')

    # The event properties.
    properties: list[LogProperty] = Field(description='The event properties.')

    @field_serializer('event_date')
    def serialize_date_time(self, date_time: datetime):
        '''
        Serializes a date/time object to an ISO 8601 formatted string.
        '''

        return date_time.isoformat()


class ServerCommandStatus(str, Enum):
    '''
    Defines the all the possible statuses of a server command.
    '''

    CANCELED = 'canceled'
    COMPLETED = 'completed'
    PENDING = 'pending'
    REJECTED = 'rejected'
    REQUESTED = 'requested'


class ServerCommand(BaseModel):
    '''
    Defines a server command.
    '''

    id: UUID = Field(
        default_factory=uuid4,
        description='The ID of the server command.')

    create_date: datetime = Field(
        default_factory=datetime.now,
        description='The date and time the server command was created.')

    channel_id: str = Field(
        description='The channel ID of the channel from which the command was requested.')

    server_id: UUID = Field(
        description='The server ID for the server on which the command is executed on.')

    thread_id: Optional[str] = Field(
        default=None,
        description='The thread ID of the thread from which the command was requested.')

    user_id: UUID = Field(
        description='The ID of the user who requested the command be executed on the server.')

    channel_name: str = Field(
        description='The name of the channel from which the command was requested.')

    server_name: str = Field(
        description=' The name of the server on which the command is executed on.')

    user_name: str = Field(
        description='The name of the user who requested the command be executed on the server.')

    query: str = Field(
        description='The query that initiated the command.')

    command: str = Field(description='The command that is executed on the server.')

    status: ServerCommandStatus = Field(description='The status of the command.')

    notification_url: Optional[str] = Field(
        description='A notification URL to which which the command result is sent.')

    @field_serializer('create_date')
    def serialize_date_time(self, date_time: datetime):
        '''
        Serializes a date/time object to an ISO 8601 formatted string.
        '''

        return date_time.isoformat()

    @field_serializer('id', 'server_id', 'user_id')
    def serialize_uuid(self, uuid: UUID):
        '''
        Serializes a UUID to a string.
        '''

        return str(uuid)


class ServerCommandResult(BaseModel):
    '''
    Defines a server command result.
    '''

    # The date and time the command started.
    start_date: datetime = Field(description="The date and time the command started")

    # The date and time the command ended.
    end_date: datetime = Field(description="The date and time the command ended")

    # The run time of the command in seconds.
    total_time: float = Field(description="The run time of the command")

    # The exit code of the command.
    exit_code: int = Field(description="The exit code of the command")

    # The standard output of the command.
    stdout: Optional[str] = Field(
        default=None, description="The standard output of the command")

    # The standard error of the command.
    stderr: Optional[str] = Field(
        default=None, description="The standard error of the command")

    @field_serializer('start_date', 'end_date')
    def serialize_date_time(self, date_time: datetime):
        '''
        Serializes a date/time object to an ISO 8601 formatted string.
        '''

        return date_time.isoformat()


class VitalsEvent(BaseModel):
    '''
    Defines a vitals event.
    '''

    vitals: str = Field(
        description='The vitals data.')
