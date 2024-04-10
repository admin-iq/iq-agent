'''
This module provides classes for managing configuration data.
'''

from logging import Logger

import logging
import toml


class Configuration:
    '''
    A class for managing configuration data.
    '''

    # The logger instance for the class.
    _logger: 'Logger'

    # The configuration data.
    _data: 'dict[str, any]'

    def __init__(self) -> None:
        # Raise an exception if the class is instantiated directly.
        raise NotImplementedError('This class cannot be instantiated directly.')

    def get(self, key: str) -> 'any | None':
        '''
        Get the value for the specified key in the configuration data.
        '''

        parts: 'list[str]' = key.split('.')
        data: 'dict[str, any]' = self._data
        for part in parts:
            if part not in data:
                return None
            data = data[part]
        return data

    def get_bool(self, key: str) -> bool | None:
        '''
        Get the boolean value for the specified key in the configuration data.
        '''

        value = self.get(key)
        if value is None:
            return None

        # Check if the value is a boolean. If it is, convert it to
        # a boolean type.
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value == 1
        if isinstance(value, str):
            return value.lower() == 'true' or value == '1'

        # Raise an exception if the value is not a boolean.
        raise ValueError(
            f'The value for key "{key}" is not a boolean value.')

    def get_float(self, key: str) -> float | None:
        '''
        Get the float value for the specified key in the configuration data.
        '''

        value = self.get(key)
        if value is None:
            return None

        return float(value)

    def get_int(self, key: str) -> int | None:
        '''
        Get the integer value for the specified key in the configuration data.
        '''

        value = self.get(key)
        if value is None:
            return None

        return int(value)

    def get_str(self, key: str) -> str:
        '''
        Get the string value for the specified key in the configuration data.
        '''

        return str(self.get(key))

    def has(self, key: str) -> bool:
        '''
        Check if the specified key is defined in the configuration data.
        '''

        parts: list[str] = key.split('.')
        data: dict[str, any] = self._data
        for part in parts:
            if part not in data:
                return False
            data = data[part]
        return True


class TomlConfiguration(Configuration):
    '''
    A class for managing configuration data loaded from a TOML file.
    '''

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def load(self, path: str) -> None:
        '''
        Load the configuration data from a TOML file at the specified path.
        '''

        # Assert that the path is defined.
        assert path is not None, 'The TOML file path is not defined.'

        # Load the configuration data from the TOML file.
        with open(path, 'r', encoding='utf-8') as file:
            self._data = toml.load(file)
