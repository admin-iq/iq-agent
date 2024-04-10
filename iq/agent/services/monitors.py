'''
This module is responsible for collecting system information and sending it to the service.
'''

from datetime import datetime
from datetime import timedelta
from logging import Logger

import json
import logging
import platform
import select
import socket
import subprocess

from platform import uname_result
from systemd import journal
from tenacity import AsyncRetrying
from tenacity import RetryError
from tenacity import stop_after_attempt

import aiohttp
import psutil
import cpuinfo

from iq.agent.models import LogEvent
from iq.agent.models import LogProperty
from iq.agent.models import VitalsEvent
from iq.agent.security import SecurityProvider


class JournaldMonitor:
    '''
    This class is responsible for monitoring the system journal.
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

        # Create a new journal reader.
        self._reader: journal.Reader = journal.Reader()

        # Move to the end of the journal.
        self._reader.seek_tail()

        # Add matches for entries with a priority of error or higher.
        self._reader.log_level(journal.LOG_ERR)

        # Setup a poll object.
        self._poll: select.poll = select.poll()

        # Register the journal file descriptor.
        self._poll.register(self._reader.fileno(), select.POLLIN)

    async def run(self) -> None:
        '''
        Consume the system journal and send important entries to the service.
        '''

        # Dedupe cache for journal entries.
        dedupe: set[str] = set()

        # Poll for new journal entries.
        for _, event in self._poll.poll():
            if event & select.POLLIN:
                # Get the next journal entry.
                entry: any = self._reader.get_next()

                # Skip invalid entries.
                if entry is None:
                    continue

                # Check the message field.
                if 'MESSAGE' not in entry:
                    continue

                # Check if the message is empty.
                if not entry['MESSAGE'] or len(entry['MESSAGE']) == 0:
                    continue

                # Skip duplicate entries.
                if entry['MESSAGE'] in dedupe:
                    continue

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

                # Add the entry to the dedupe cache.
                dedupe.add(entry['MESSAGE'])

    def to_log_event(self, entry: any) -> 'LogEvent':
        '''
        Convert a journal entry to a log event.
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
            source='journald',
            properties=properties
        )

class VitalsMonitor:
    '''
    This class is responsible for collecting system information and sending it to the service.
    '''

    def __init__(self,
                 url: str,
                 security: 'SecurityProvider',
                 timeout=300):
        # Initialize the logger.
        self._logger: Logger = logging.getLogger(__name__)

        # Set the default headers.
        self._headers: dict[str, str] = {
            'Authorization': f'Bearer {security.access_token}',
            'Client-ID': security.client_id
        }

        # Set the service URL.
        self._url: str = url

        # Set the timeout.
        self._timeout: int = timeout

        # Set the security provider.
        self._security: SecurityProvider = security

    def collect_vitals(self) -> 'dict[str, any]':
        '''
        Collect all the system information.
        '''

        # Get the system information.
        info: 'dict[str, any]' = {
            'system_info': self.get_system_info(),
            'boot_time': self.get_boot_time(),
            'cpu_info': self.get_cpu_info(),
            'memory_info': self.get_memory_info(),
            'swap_info': self.get_swap_info(),
            'disk_info': self.get_disk_info(),
            'network_info': self.get_network_info()
        }

        # Get the installed packages.
        if self.has_command('pip'):
            info['python_packages'] = self.get_installed_python_packages()

        if self.has_command('dpkg'):
            info['deb_packages'] = self.get_installed_deb_packages()

        if self.has_command('rpm'):
            info['rpm_packages'] = self.get_installed_rpm_packages()

        return info

    @staticmethod
    def get_size(size: int, suffix: str = 'B') -> str:
        '''
        Get the size in human readable format.
        '''

        factor: int = 1024
        for unit in ['', 'K', 'M', 'G', 'T', 'P']:
            if size < factor:
                return f'{size:.2f}{unit}{suffix}'
            size /= factor

        # If the size is too large, raise an error.
        raise ValueError('Size is too large')

    def get_system_info(self) -> 'dict[str, any]':
        '''
        Get system information.
        '''

        # Get the platform information.
        uname: uname_result = platform.uname()

        # Return the system information.
        return {
            'system': uname.system,
            'node_name': uname.node,
            'release': uname.release,
            'version': uname.version,
            'machine': uname.machine,
            'processor': uname.processor,
        }

    def get_boot_time(self) -> 'dict[str, any]':
        '''
        Get the boot time.
        '''

        timestamp: float = psutil.boot_time()
        timestamp: datetime = datetime.fromtimestamp(timestamp)
        return {
            'boot_time': timestamp.isoformat()
        }

    def get_cpu_info(self) -> 'dict[str, any]':
        '''
        Get the CPU information.
        '''

        # Get the CPU brand.
        cpu_info: 'dict[str, any]' = cpuinfo.get_cpu_info()

        # Get the CPU frequency.
        cpufreq: any = psutil.cpu_freq()

        return {
            'cpu_brand': cpu_info.get('brand_raw', ''),
            'physical_cores': psutil.cpu_count(logical=False),
            'total_cores': psutil.cpu_count(logical=True),
            'max_frequency': cpufreq.max,
            'min_frequency': cpufreq.min,
            'current_frequency': cpufreq.current,
            'cpu_usage_per_core': psutil.cpu_percent(percpu=True, interval=1),
            'total_cpu_usage': psutil.cpu_percent()
        }

    def get_memory_info(self) -> 'dict[str, any]':
        '''
        Get the memory information.
        '''

        memory: any = psutil.virtual_memory()

        return {
            'total': self.get_size(memory.total),
            'available': self.get_size(memory.available),
            'used': self.get_size(memory.used),
            'percentage': memory.percent
        }

    def get_swap_info(self) -> 'dict[str, any]':
        '''
        Get the swap information.
        '''

        swap = psutil.swap_memory()

        return {
            'total': self.get_size(swap.total),
            'free': self.get_size(swap.free),
            'used': self.get_size(swap.used),
            'percentage': swap.percent
        }

    def get_disk_info(self) -> 'dict[str, any]':
        '''
        Get the disk information.
        '''

        partitions: any = psutil.disk_partitions()
        disk_info: 'list[dict[str, any]]' = []
        for partition in partitions:
            try:
                partition_usage: any = psutil.disk_usage(partition.mountpoint)
            except PermissionError as error:
                self._logger.exception(error)
                continue
            disk_info.append({
                'device': partition.device,
                'mountpoint': partition.mountpoint,
                'fstype': partition.fstype,
                'total_size': self.get_size(partition_usage.total),
                'used': self.get_size(partition_usage.used),
                'free': self.get_size(partition_usage.free),
                'percentage': partition_usage.percent
            })
        disk_io: any = psutil.disk_io_counters()
        disk_io_stats: 'dict[str, any]' = {
            'total_read': self.get_size(disk_io.read_bytes),
            'total_write': self.get_size(disk_io.write_bytes)
        }
        return {'partitions': disk_info, 'disk_io': disk_io_stats}

    def get_network_info(self) -> 'dict[str, any]':
        '''
        Get the network information.
        '''

        network_info: 'dict[str, any]' = {}

        # Get the network interfaces.
        if_addrs: 'dict[str, any]' = psutil.net_if_addrs()
        for interface_name, interface_addresses in if_addrs.items():
            if_info: 'list[dict[str, any]]' = []
            for address in interface_addresses:
                address_info: 'dict[str, any]' = {
                    'address': address.address,
                    'netmask': address.netmask,
                    'broadcast': address.broadcast if hasattr(address, 'broadcast') else None,
                    'family': str(address.family)
                }
                if_info.append(address_info)
            network_info[interface_name] = if_info
        net_io = psutil.net_io_counters()
        net_io_stats: 'dict[str, any]' = {
            'bytes_sent': self.get_size(net_io.bytes_sent),
            'bytes_recv': self.get_size(net_io.bytes_recv)
        }

        # Get the host name.
        host_name: str = socket.gethostname()

        # Get the IP address.
        ip_address: str = socket.gethostbyname(host_name)

        return {
            'host_name': host_name,
            'ip_address': ip_address,
            'interfaces': network_info,
            'io_counters': net_io_stats
        }

    def get_installed_python_packages(self) -> 'list[list[str]] | dict[str, any]':
        '''
        Get the installed Python packages.
        '''

        packages = []
        try:
            # Get the installed packages using pip.
            packages: str = subprocess.check_output(['pip', 'list'], text=True)

            # Remove any leading or trailing whitespace.
            packages = packages.strip()

            # Split the output into lines.
            packages: 'list[str]' = packages.split('\n')

            # Skip header lines
            packages = packages[2:]

            # Get package name and version
            packages: 'list[list[str]]' = [package.split()[:2] for package in packages]
        except Exception as error:
            self._logger.exception(error)

            packages = {'pip_error': str(error)}
        return packages

    def get_installed_deb_packages(self) -> 'list[list[str]] | dict[str, any]':
        '''
        Get the installed Debian packages.
        '''

        packages = []
        try:
            # Get the installed packages using dpkg.
            packages: str = subprocess.check_output(['dpkg', '-l'], text=True)

            # Remove any leading or trailing whitespace.
            packages = packages.strip()

            # Split the output into lines.
            packages: 'list[str]' = packages.split('\n')

            # Skip header lines
            packages = packages[5:]

            # Filter for installed packages only.
            packages: 'list[list[str]]' = [
                package.split()[:2] for package in packages if package.startswith('ii')
            ]
        except Exception as error:
            self._logger.exception(error)

            packages = {'dpkg_error': str(error)}
        return packages

    def get_installed_rpm_packages(self) -> 'list[str] | dict[str, any]':
        '''
        Get the installed RPM packages.
        '''

        packages = []
        try:
            # Get the installed packages using rpm.
            packages: str = subprocess.check_output(['rpm', '-qa'], text=True)

            # Remove any leading or trailing whitespace.
            packages = packages.strip()

            # Split the output into lines.
            return packages.split('\n')
        except Exception as error:
            self._logger.exception(error)

            packages = {'rpm_error': str(error)}
        return packages

    def has_command(self, cmd: str) -> bool:
        '''
        Check if a command exists on the system.
        '''

        try:
            subprocess.run(
                [cmd, "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    async def run(self):
        '''
        Send the system vitals to the service.
        '''

        # Collect the system vitals.
        vitals: 'dict[str, any]' = self.collect_vitals()

        # Create a vitals event.
        vitals_event: 'VitalsEvent' = VitalsEvent(
            vitals=json.dumps(vitals, indent=4))

        # Encode the vitals as bytes.
        payload: bytes = vitals_event.model_dump_json().encode('utf-8')

        # Sign the result.
        signature: str = self._security.sign(payload)

        # Define the request headers.
        headers: dict[str, str] = self._headers.copy()
        headers['Content-Type'] = 'application/json'
        headers['Signature'] = signature

        # Send the vitals to the service.
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
                        'Failed to send the system vitals. Code: %s Reason: %s',
                        response.status, json.dumps(error['detail'], indent=4))
