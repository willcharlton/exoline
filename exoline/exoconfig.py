import os, re
import ruamel.yaml as yaml
from exoline.exocommon import ExoException

class ExoConfig:
    '''Manages the config file, grouping all realted actions'''
    regex_rid = re.compile("[0-9a-fA-F]{40}")

    def __init__(self, configfile='~/.exoline'):
        # remember the config file requested
        self.askedconfigfile = configfile
        # look in some by-convention locations
        self.configfile = self.realConfigFile(configfile)
        self.loadConfig(self.configfile)

    def realConfigFile(self, configfile):
        '''Find real path for a config file'''
        # Does the file as passed exist?
        cfgf = os.path.expanduser(configfile)

        if os.path.exists(cfgf):
            return cfgf

        # Is it in the exoline folder?
        cfgf = os.path.join('~/.exoline', configfile)
        cfgf = os.path.expanduser(cfgf)
        if os.path.exists(cfgf):
            return cfgf

        # Or is it a dashed file?
        cfgf = '~/.exoline-' + configfile
        cfgf = os.path.expanduser(cfgf)
        if os.path.exists(cfgf):
            return cfgf

        # No such file to load.
        return None

    def loadConfig(self, configfile):
        if configfile is None:
            self.config = {}
        else:
            try:
                with open(configfile) as f:
                    self.config = yaml.load(f, yaml.RoundTripLoader)
            except IOError as ex:
                self.config = {}

    def lookup_shortcut(self, cik):
        '''If a CIK has client/resource parts, seperate and look thouse up'''
        if ':c' in cik:
            # break into parts, then lookup each.
            c,g,r = cik.partition(':c')
            cik = { 'cik': self._lookup_shortcut(c),
                    'client_id': self._lookup_shortcut(r) }
        elif ':r' in cik:
            c,g,r = cik.partition(':r')
            cik = { 'cik': self._lookup_shortcut(c),
                    'resource_id': self._lookup_shortcut(r) }
        else:
            # look it up, then check again for parts.
            cik = self._lookup_shortcut(cik)
            if ':c' in cik:
                c,g,r = cik.partition(':c')
                cik = {'cik': c, 'client_id': r}
            elif ':r' in cik:
                c,g,r = cik.partition(':r')
                cik = {'cik': c, 'resource_id': r}

        return cik


    def _lookup_shortcut(self, cik):
        '''Look up what was passed for cik in config file
            if it doesn't look like a CIK.'''
        if self.regex_rid.match(cik) is None:
            if 'keys' in self.config:
                if cik in self.config['keys']:
                    return self.config['keys'][cik].strip()
                elif cik.isdigit() and int(cik) in self.config['keys']:
                    return self.config['keys'][int(cik)].strip()
                else:
                    raise ExoException('No CIK shortcut {0}\n{1}'.format(
                        cik, '\n'.join(sorted(map(str, self.config['keys'])))))
            else:
                raise ExoException('Tried a CIK shortcut {0}, but found no keys'.format(cik))
        else:
            return cik

    def mingleArguments(self, args):
        '''This mixes the settings applied from the configfile, the command line and the ENV.
        Command line always overrides ENV which always overrides configfile.
        '''
        # This ONLY works with options that take a parameter.
        toMingle = ['host', 'port', 'httptimeout', 'useragent', 'portals', 'vendortoken', 'vendor']

        # Precedence: ARGV then ENV then CFG

        # Looks for ENV vars and pull them in, unless in ARGV
        for arg in toMingle:
            if args['--'+arg] is None:
                env = os.getenv('EXO_'+arg.upper())
                if env is not None:
                    args['--'+arg] = env

        # Look for CFG vars and pull them in, unless in ARGV
        for arg in toMingle:
            if arg in self.config and args['--'+arg] is None:
                args['--'+arg] = self.config[arg]

        # Copy all ARGV vars to CFG for uniform lookups.
        for arg in toMingle:
            self.config[arg] = args['--'+arg]

