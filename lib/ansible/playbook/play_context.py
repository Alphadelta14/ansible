# -*- coding: utf-8 -*-

# (c) 2012-2014, Michael DeHaan <michael.dehaan@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pipes
import random
import re

from ansible import constants as C
from ansible.errors import AnsibleError
from ansible.playbook.attribute import Attribute, FieldAttribute
from ansible.playbook.base import Base
from ansible.template import Templar
from ansible.utils.boolean import boolean
from ansible.utils.unicode import to_unicode

__all__ = ['PlayContext']

SU_PROMPT_LOCALIZATIONS = [
    'Password',
    '암호',
    'パスワード',
    'Adgangskode',
    'Contraseña',
    'Contrasenya',
    'Hasło',
    'Heslo',
    'Jelszó',
    'Lösenord',
    'Mật khẩu',
    'Mot de passe',
    'Parola',
    'Parool',
    'Pasahitza',
    'Passord',
    'Passwort',
    'Salasana',
    'Sandi',
    'Senha',
    'Wachtwoord',
    'ססמה',
    'Лозинка',
    'Парола',
    'Пароль',
    'गुप्तशब्द',
    'शब्दकूट',
    'సంకేతపదము',
    'හස්පදය',
    '密码',
    '密碼',
]

# the magic variable mapping dictionary below is used to translate
# host/inventory variables to fields in the PlayContext
# object. The dictionary values are tuples, to account for aliases
# in variable names.

MAGIC_VARIABLE_MAPPING = dict(
   connection       = ('ansible_connection',),
   remote_addr      = ('ansible_ssh_host', 'ansible_host'),
   remote_user      = ('ansible_ssh_user', 'ansible_user'),
   port             = ('ansible_ssh_port', 'ansible_port'),
   password         = ('ansible_ssh_pass', 'ansible_password'),
   private_key_file = ('ansible_ssh_private_key_file', 'ansible_private_key_file'),
   shell            = ('ansible_shell_type',),
   become           = ('ansible_become',),
   become_method    = ('ansible_become_method',),
   become_user      = ('ansible_become_user',),
   become_pass      = ('ansible_become_password','ansible_become_pass'),
   become_exe       = ('ansible_become_exe',),
   become_flags     = ('ansible_become_flags',),
   sudo             = ('ansible_sudo',),
   sudo_user        = ('ansible_sudo_user',),
   sudo_pass        = ('ansible_sudo_password', 'ansible_sudo_pass'),
   sudo_exe         = ('ansible_sudo_exe',),
   sudo_flags       = ('ansible_sudo_flags',),
   su               = ('ansible_su',),
   su_user          = ('ansible_su_user',),
   su_pass          = ('ansible_su_password', 'ansible_su_pass'),
   su_exe           = ('ansible_su_exe',),
   su_flags         = ('ansible_su_flags',),
)

SU_PROMPT_LOCALIZATIONS = [
    'Password',
    '암호',
    'パスワード',
    'Adgangskode',
    'Contraseña',
    'Contrasenya',
    'Hasło',
    'Heslo',
    'Jelszó',
    'Lösenord',
    'Mật khẩu',
    'Mot de passe',
    'Parola',
    'Parool',
    'Pasahitza',
    'Passord',
    'Passwort',
    'Salasana',
    'Sandi',
    'Senha',
    'Wachtwoord',
    'ססמה',
    'Лозинка',
    'Парола',
    'Пароль',
    'गुप्तशब्द',
    'शब्दकूट',
    'సంకేతపదము',
    'හස්පදය',
    '密码',
    '密碼',
]

TASK_ATTRIBUTE_OVERRIDES = (
    'become',
    'become_user',
    'become_pass',
    'become_method',
    'connection',
    'delegate_to',
    'no_log',
    'remote_user',
)


class PlayContext(Base):

    '''
    This class is used to consolidate the connection information for
    hosts in a play and child tasks, where the task may override some
    connection/authentication information.
    '''

    # connection fields, some are inherited from Base:
    # (connection, port, remote_user, environment, no_log)
    _remote_addr      = FieldAttribute(isa='string')
    _password         = FieldAttribute(isa='string')
    _private_key_file = FieldAttribute(isa='string', default=C.DEFAULT_PRIVATE_KEY_FILE)
    _timeout          = FieldAttribute(isa='int', default=C.DEFAULT_TIMEOUT)
    _shell            = FieldAttribute(isa='string')

    # privilege escalation fields
    _become           = FieldAttribute(isa='bool')
    _become_method    = FieldAttribute(isa='string')
    _become_user      = FieldAttribute(isa='string')
    _become_pass      = FieldAttribute(isa='string')
    _become_exe       = FieldAttribute(isa='string')
    _become_flags     = FieldAttribute(isa='string')
    _prompt           = FieldAttribute(isa='string')

    # backwards compatibility fields for sudo/su
    _sudo_exe         = FieldAttribute(isa='string')
    _sudo_flags       = FieldAttribute(isa='string')
    _sudo_pass        = FieldAttribute(isa='string')
    _su_exe           = FieldAttribute(isa='string')
    _su_flags         = FieldAttribute(isa='string')
    _su_pass          = FieldAttribute(isa='string')

    # general flags
    _verbosity        = FieldAttribute(isa='int', default=0)
    _only_tags        = FieldAttribute(isa='set', default=set())
    _skip_tags        = FieldAttribute(isa='set', default=set())
    _check_mode       = FieldAttribute(isa='bool', default=False)
    _force_handlers   = FieldAttribute(isa='bool', default=False)
    _start_at_task    = FieldAttribute(isa='string')
    _step             = FieldAttribute(isa='bool', default=False)
    _diff             = FieldAttribute(isa='bool', default=False)

    def __init__(self, play=None, options=None, passwords=None):

        super(PlayContext, self).__init__()

        if passwords is None:
            passwords = {}

        self.password    = passwords.get('conn_pass','')
        self.become_pass = passwords.get('become_pass','')

        # set options before play to allow play to override them
        if options:
            self.set_options(options)

        if play:
            self.set_play(play)

    def set_play(self, play):
        '''
        Configures this connection information instance with data from
        the play class.
        '''

        if play.connection:
            self.connection = play.connection

        if play.remote_user:
            self.remote_user = play.remote_user

        if play.port:
            self.port = int(play.port)

        if play.become is not None:
            self.become = play.become
        if play.become_method:
            self.become_method = play.become_method
        if play.become_user:
            self.become_user = play.become_user

        # non connection related
        self.no_log      = play.no_log

        if play.force_handlers is not None:
            self.force_handlers = play.force_handlers

    def set_options(self, options):
        '''
        Configures this connection information instance with data from
        options specified by the user on the command line. These have a
        lower precedence than those set on the play or host.
        '''

        if options.connection:
            self.connection = options.connection

        self.remote_user = options.remote_user
        self.private_key_file = options.private_key_file

        # privilege escalation
        self.become        = options.become
        self.become_method = options.become_method
        self.become_user   = options.become_user

        # general flags (should we move out?)
        if options.verbosity:
            self.verbosity  = options.verbosity
        #if options.no_log:
        #    self.no_log     = boolean(options.no_log)
        if options.check:
            self.check_mode = boolean(options.check)
        if hasattr(options, 'force_handlers') and options.force_handlers:
            self.force_handlers = boolean(options.force_handlers)
        if hasattr(options, 'step') and options.step:
            self.step = boolean(options.step)
        if hasattr(options, 'start_at_task') and options.start_at_task:
            self.start_at_task = to_unicode(options.start_at_task)
        if hasattr(options, 'diff') and options.diff:
            self.diff = boolean(options.diff)

        # get the tag info from options, converting a comma-separated list
        # of values into a proper list if need be. We check to see if the
        # options have the attribute, as it is not always added via the CLI
        if hasattr(options, 'tags'):
            if isinstance(options.tags, list):
                self.only_tags.update(options.tags)
            elif isinstance(options.tags, basestring):
                self.only_tags.update(options.tags.split(','))

        if len(self.only_tags) == 0:
            self.only_tags = set(['all'])

        if hasattr(options, 'skip_tags'):
            if isinstance(options.skip_tags, list):
                self.skip_tags.update(options.skip_tags)
            elif isinstance(options.skip_tags, basestring):
                self.skip_tags.update(options.skip_tags.split(','))

    def set_task_and_variable_override(self, task, variables):
        '''
        Sets attributes from the task if they are set, which will override
        those from the play.
        '''

        new_info = self.copy()

        # loop through a subset of attributes on the task object and set
        # connection fields based on their values
        for attr in TASK_ATTRIBUTE_OVERRIDES:
            if hasattr(task, attr):
                attr_val = getattr(task, attr)
                if attr_val is not None:
                    setattr(new_info, attr, attr_val)

        # finally, use the MAGIC_VARIABLE_MAPPING dictionary to update this
        # connection info object with 'magic' variables from the variable list
        for (attr, variable_names) in MAGIC_VARIABLE_MAPPING.iteritems():
            for variable_name in variable_names:
                if variable_name in variables:
                    setattr(new_info, attr, variables[variable_name])

        # make sure we get port defaults if needed
        if new_info.port is None and C.DEFAULT_REMOTE_PORT is not None:
            new_info.port = int(C.DEFAULT_REMOTE_PORT)

        # become legacy updates
        if not new_info.become_pass:
            if new_info.become_method == 'sudo' and new_info.sudo_pass:
               setattr(new_info, 'become_pass', new_info.sudo_pass)
            elif new_info.become_method == 'su' and new_info.su_pass:
               setattr(new_info, 'become_pass', new_info.su_pass)

        return new_info

    def make_become_cmd(self, cmd, executable=None):
        """ helper function to create privilege escalation commands """

        prompt      = None
        success_key = None

        if executable is None:
            executable = C.DEFAULT_EXECUTABLE

        if self.become:

            becomecmd   = None
            randbits    = ''.join(chr(random.randint(ord('a'), ord('z'))) for x in xrange(32))
            success_key = 'BECOME-SUCCESS-%s' % randbits
            success_cmd = pipes.quote('echo %s; %s' % (success_key, cmd))

            if self.become_method == 'sudo':
                # Rather than detect if sudo wants a password this time, -k makes sudo always ask for
                # a password if one is required. Passing a quoted compound command to sudo (or sudo -s)
                # directly doesn't work, so we shellquote it with pipes.quote() and pass the quoted
                # string to the user's shell.  We loop reading output until we see the randomly-generated
                # sudo prompt set with the -p option.
                prompt = '[sudo via ansible, key=%s] password: ' % randbits
                exe = self.become_exe or self.sudo_exe or 'sudo'
                flags = self.become_flags or self.sudo_flags or C.DEFAULT_SUDO_FLAGS

                # force quick error if password is required but not supplied, should prevent sudo hangs.
                if not self.become_pass:
                    flags += " -n "

                becomecmd = '%s %s -S -p "%s" -u %s %s -c %s' % (exe, flags, prompt, self.become_user, executable, success_cmd)

            elif self.become_method == 'su':

                def detect_su_prompt(data):
                    SU_PROMPT_LOCALIZATIONS_RE = re.compile("|".join(['(\w+\'s )?' + x + ' ?: ?' for x in SU_PROMPT_LOCALIZATIONS]), flags=re.IGNORECASE)
                    return bool(SU_PROMPT_LOCALIZATIONS_RE.match(data))

                prompt = detect_su_prompt
                exe = self.become_exe or self.su_exe or 'su'
                flags = self.become_flags or self.su_flags or ''
                becomecmd = '%s %s %s -c "%s -c %s"' % (exe, flags, self.become_user, executable, success_cmd)

            elif self.become_method == 'pbrun':

                prompt='assword:'
                exe = self.become_exe or 'pbrun'
                flags = self.become_flags or ''
                becomecmd = '%s -b %s -u %s %s' % (exe, flags, self.become_user, success_cmd)

            elif self.become_method == 'pfexec':

                exe = self.become_exe or 'pfexec'
                flags = self.become_flags or ''
                # No user as it uses it's own exec_attr to figure it out
                becomecmd = '%s %s "%s"' % (exe, flags, success_cmd)

            elif self.become_method == 'runas':
                raise AnsibleError("'runas' is not yet implemented")
                #TODO: figure out prompt
                # this is not for use with winrm plugin but if they ever get ssh native on windoez
                exe = self.become_exe or 'runas'
                flags = self.become_flags or ''
                becomecmd = '%s %s /user:%s "%s"' % (exe, flags, self.become_user, success_cmd)

            else:
                raise AnsibleError("Privilege escalation method not found: %s" % self.become_method)

            self.prompt      = prompt
            self.success_key = success_key
            return ('%s -c %s' % (executable, pipes.quote(becomecmd)))

        return cmd

    def update_vars(self, variables):
        '''
        Adds 'magic' variables relating to connections to the variable dictionary provided.
        In case users need to access from the play, this is a legacy from runner.
        '''

        #FIXME: remove password? possibly add become/sudo settings
        for special_var in  ['ansible_connection', 'ansible_ssh_host', 'ansible_ssh_pass', 'ansible_ssh_port', 'ansible_ssh_user', 'ansible_ssh_private_key_file']:
            if special_var not in variables:
                for prop, varnames in MAGIC_VARIABLE_MAPPING.items():
                    if special_var in varnames:
                        variables[special_var] = getattr(self, prop)
