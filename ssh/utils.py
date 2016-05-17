import abc
import datetime
import json
import logging
import os

log = logging.getLogger(__name__)


class CommandChain():
    '''
    Add command to execute on a remote host.

    :param cmd: String, command to execute
    :param rollback: String (optional) a rollback command
    :param stage: String (optional)
    :return:
    '''
    execute_flag = 'execute'
    copy_flag = 'copy'

    def __init__(self, namespace):
        self.commands_stack = []
        self.namespace = namespace

    def add_execute(self, cmd, rollback=None, stage=None):
        assert isinstance(cmd, list) or callable(cmd)
        self.commands_stack.append((self.execute_flag, cmd, rollback, stage))

    def add_copy(self, local_path, remote_path, remote_to_local=False, recursive=False, stage=None):
        self.commands_stack.append((self.copy_flag, local_path, remote_path, remote_to_local, recursive, stage))

    def get_commands(self):
        # Return all commands
        return self.commands_stack

    def prepend_command(self, cmd, rollback=None, stage=None):
        # We can specify a command to be executed before the main chain of commands, for example some setup commands
        assert isinstance(cmd, list)
        self.commands_stack.insert(0, (self.execute_flag, cmd, rollback, stage))


class AbstractSSHLibDelegate(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def on_update(self, future, callback):
        '''
        A method called on update
        :param future: An instance of asyncio.Future() passed by a callback
        :param callback: should run callback.set_result(True) to indicate that callback was successfully executed
        :return:
        '''
        pass

    @abc.abstractmethod
    def on_done(self, name, result, host_status_count=None, host_status=None):
        '''
        A method called when chain execution is finished
        :param name: A unique chain identifier
        :param result: asyncio.Future().result()
        :param host_status_count: String
        :param host_status: String
        :return:
        '''
        pass


class JsonDelegate(AbstractSSHLibDelegate):
    def __init__(self, state_dir, targets_len, total_hosts=None, total_masters=None, total_agents=None, **kwargs):
        self.state_dir = state_dir
        self.total_hosts = total_hosts if total_hosts else targets_len
        self.total_masters = total_masters
        self.total_agents = total_agents

    def _update_chain_props(self, status_json, name):
        # Update chain properties. We may update the properties
        if 'hosts' not in status_json:
            status_json['hosts'] = {}

        # Use this hack to update number of total hosts/masters/agent on the fly. This is used on deploy 'retry'.
        if status_json.get('total_hosts') != self.total_hosts:
            status_json['total_hosts'] = self.total_hosts

        if status_json.get('total_masters') != self.total_masters:
            status_json['total_masters'] = self.total_masters

        if status_json.get('total_agents') != self.total_agents:
            status_json['total_agents'] = self.total_agents

        status_json['chain_name'] = name

    def _read_json_state(self, name):
        status_file = os.path.join(self.state_dir, '{}.json'.format(name))
        if os.path.isfile(status_file):
            with open(status_file) as f:
                return json.load(f)
        return {}

    def _dump_json_state(self, name, status_json):
        status_file = os.path.join(self.state_dir, '{}.json'.format(name))

        with open(status_file, 'w') as f:
            try:
                json.dump(status_json, f)
            except IOError:
                log.error('Could not update state file {}'.format(status_file))

    def on_update(self, future, callback_called):
        self._update_json_file(*future.result(), future_update=True, callback_called=callback_called)

    def on_done(self, name, result, host_status=None):
        self._update_json_file(name, result, None, host_status=host_status)

    def _update_json_file(self, name, result, host_object, future_update=None, host_status=None, callback_called=None):
        status_json = self._read_json_state(name)
        self._update_chain_props(status_json, name)

        for host, return_values in result.items():
            # Block is executed for on_update callback
            if future_update:
                return_values.update({
                    'date': str(datetime.datetime.now())
                })

                # Append to commands
                if host in status_json['hosts']:
                    status_json['hosts'][host]['commands'].append(return_values)
                else:
                    status_json['hosts'][host] = {
                        'commands': [return_values]
                    }

                if host_object.tags and 'tags' not in status_json['hosts'][host]:
                    status_json['hosts'][host]['tags'] = host_object.tags

                # Update chain status to running if not other state found.
                if 'host_status' not in status_json['hosts'][host]:
                    status_json['hosts'][host]['host_status'] = 'running'

        # Update chain status: success or fail
        if host_status:
            status_json['hosts'][host]['host_status'] = host_status

        self._dump_json_state(name, status_json)
        if callback_called:
                callback_called.set_result(True)


class SyncCmdDelegate(AbstractSSHLibDelegate):
    """Used for running synchronous commands in CLI or general orchestration
    without a long-running server process
    """
    def on_update(self, future, callback_called):
        chain_name, result_object, host = future.result()
        callback_called.set_result(True)

    def on_done(self, name, result, host_status=None):
        pass
