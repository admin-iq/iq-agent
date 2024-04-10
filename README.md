IQ Agent Service
================

The IQ Agent operates as a background process, performing the following tasks:
1. It collects system vitals, including performance metrics and status information, then transmits this data to the AdminIQ service.
2. It actively monitors the system's Journald logs for entries that may require further investigation and reports these to the AdminIQ service.
3. It periodically polls the AdminIQ service for any outstanding commands to execute and carries out those commands as directed by user requests.

## Dependencies

For the system to operate with the IQ Agent, the following dependencies must be installed:

- Python 3
- Python 3 Development Files
- Python 3 PIP
- Python 3 Virtualenv
- libsystemd library

## Installation

To install IQ Agent, you need to run the setup script provided in the repository. 

```shell
pip install --upgrade .
```

This will install all the necessary dependencies listed in the `setup.py` file.

## Configuration

Before running the IQ Agent, you need to configure it. The configuration is stored in the `agent.toml` file located in the `conf` directory.

Here are the configuration options you need to set:

- `access_token`: Your access token for the AdminIQ service.
- `client_id`: Your client ID for the AdminIQ service.
- `client_secret`: Your client secret for the AdminIQ service.
- `logging`: Configuration for the logging system. You can set the encoding, log level, log format, and log file path.
- `executors.shell`: Configuration for the shell executor. You can set the interval, poll timeout, reply timeout, reply retries, and URL for the shell executor service.
- `monitors.journald`: Configuration for the journald monitor. You can set the interval, timeout, retries, and URL for the journald monitor service.
- `monitors.vitals`: Configuration for the vitals monitor. You can set the interval, timeout, and URL for the vitals monitor service.

## Configuring the Agent

To interactively configure the agent, please execute the `iq-agent-config` script.

```sh
iq-agent-config --config conf/agent.toml
```

The script will set up the agent's necessary configuration, and a confirmation message will be displayed upon successful configuration.

## Running the Agent

After you have configured the agent, you can run it using the `iq-agent` script.

```shell
iq-agent --config conf/agent.toml
```


## License

IQ Agent is licensed under the GNU General Public License (GPL), whose terms are detailed in the LICENSE file located in the repository.