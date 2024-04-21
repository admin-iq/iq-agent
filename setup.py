'''
This file provides the setup configuration for the IQ Agent package.
'''

#!/usr/bin/env python

from distutils.core import setup

import platform

# Common setup arguments
setup_args = {
    'name': 'iq-agent',
    'version': '0.1.0',
    'description': 'An agent for the AdminIQ service.',
    'author': 'Thomas Quintana',
    'author_email': 'thomas.quintana@adminiq.ai',
    'install_requires': [
        'aiohttp==3.8.5',
        'psutil==5.9.8',
        'py-cpuinfo==9.0.0',
        'pydantic==2.4.2',
        'pyOpenSSL==24.0.0',
        'requests==2.31.0',
        'tenacity==8.2.3',
        'toml==0.10.2'
    ],
    'packages': [
        'iq',
        'iq.agent',
        'iq.agent.services',
    ],
    'scripts': [
        'scripts/iq-agent',
        'scripts/iq-agent-config'
    ]
}

# Add OS-specific dependencies
system_name = platform.system()
if system_name == 'Linux':
    setup_args['install_requires'].append('systemd-python==235')

if system_name == 'Windows':
    setup_args['install_requires'].append('pywin32==306')

# Finally, call setup with the constructed arguments
setup(**setup_args)














