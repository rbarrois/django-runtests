# coding: utf-8
# Copyright (c) 2012 Raphaël Barrois
# Distributed under the MIT license


from __future__ import unicode_literals

import optparse
import os
import sys
import time

import django
from django.conf import settings as django_settings
from django.utils import crypto, importlib


#: Shortcut for --db-engine options.
DB_ENGINES = {
    'sqlite': 'django.db.backends.sqlite3',
    'psql': 'django.db.backends.postgresql_psycopg2',
    'mysql': 'django.db.backends.mysql',
    'oracle': 'django.db.backends.oracle',
    'postgis': 'django.contrib.gis.db.backends.postgis',
}


class RunTests(object):
    """Handle running the tests and parsing command line arguments.

    Class attributes:
        TESTED_APPS (str list): names of Django apps to test
        EXTRA_APPS (str list): names of other Django apps that need testing
        EXTRA_SETTINGS (dict): additional settings to use beyond those generated
            in make_settings
        URLCONF (str): name of the base urlconf module, if needed
        DEFAULT_DB_* (str): defaults for the DATABASE['default'] setting

    Attributes:
        app_names (str list): short name of the apps to test
    """
    EXTRA_APPS = ()
    EXTRA_SETTINGS = {}
    TESTED_APPS = ()
    URLCONF = ''

    DEFAULT_DB_ENGINE = 'sqlite'
    DEFAULT_DB_NAME = 'db.sqlite'
    DEFAULT_DB_USER = ''
    DEFAULT_DB_PASSWORD = ''
    DEFAULT_DB_HOST = ''
    DEFAULT_DB_PORT = ''

    BASE_PATH = ''

    DISABLED_LOGGERS = ()

    def __init__(self):
        self.app_names = set(app.split('.')[-1] for app in self.TESTED_APPS)

    def info(self, msg, *args):
        line = msg + '\n'
        sys.stdout.write(line % args)

    def get_usage(self):
        """Prepare the usage string"""
        usage = """%prog [options] app1 app2 ...

Run tests for the selected Python apps (if empty, run tests for all apps)

Valid apps: """ + ', '.join(sorted(self.app_names))
        return usage

    def make_db_options(self, parser):
        """Prepare all db-related options."""
        db_options = optparse.OptionGroup(parser, "Database options")

        db_options.add_option('--db-engine', dest='db_engine',
            help="Use DBENGINE database engine. Valid options are %s or other "
            "relevant values for the 'ENGINE' setting" % ', '.join(DB_ENGINES),
            metavar='DBENGINE')
        db_options.add_option('--db-name', dest='db_name',
            help='Connect to DBNAME database', metavar='DBNAME')
        db_options.add_option('--db-user', dest='db_user',
            help='Connect to database using DBUSER role', metavar='DBUSER')
        db_options.add_option('--db-password', dest='db_password',
            help='Connect to database with DBPASSWORD', metavar='DBPASSWORD')
        db_options.add_option('--db-host', dest='db_host',
            help='Connect to database at DBHOST', metavar='DBHOST')
        db_options.add_option('--db-port', dest='db_port',
            help='Connect to database port DBPORT', metavar='DBPORT')
        return db_options

    def make_output_options(self, parser):
        """Prepare all output-related options."""
        output_options = optparse.OptionGroup(parser, "Output options")

        output_options.add_option('-v', '--verbose', action='store_true',
            dest='verbose', help='Increase test verbosity')
        output_options.add_option('-q', '--quiet', action='store_true',
            dest='quiet', help='Decrease test verbosity')
        output_options.add_option('--log-to-stderr', action='store_true',
            dest='log_to_stderr', help="Send logging output to stderr.")
        output_options.add_option('--disable-logger', action='append',
            dest='disabled_loggers', default=list(self.DISABLED_LOGGERS),
            help="Disable logger LOGGER (repeat for more loggers)")
        output_options.add_option('--report-format', dest='report_format',
            help="Generate reports in FORMAT format", metavar='FORMAT')
        output_options.add_option('--report-destination', dest='report_dest',
            help="Store reports in DEST folder/file", metavar='DEST')

        return output_options

    def prepare_parser(self):
        """Prepare the option parser."""
        usage = self.get_usage()
        parser = optparse.OptionParser(usage=usage)
        parser.add_option('--no-alter-path', action='store_true', default=False,
            dest='no_alter_path', help="Don't alter sys.path for tests")
        parser.add_option('--noinput', action='store_false', default=True,
            dest='interactive', help="No input")
        parser.add_option('--failfast', action='store_true', default=False,
            dest='fail_fast', help="Abort tests at the first failure")

        parser.add_option_group(self.make_db_options(parser))
        parser.add_option_group(self.make_output_options(parser))
        return parser


    def enhance_parser(self, parser):
        """Extension point for adding custom options and groups to the option parser."""
        pass

    def check_options(self, parser, options, apps):
        """Check all options.

        Args:
            parser (optparse.OptionParser): the parser used to parse the command line
            options (optparse.Options): the parsed options
            apps (str list): the provided application names

        The main use of `parser` is for `parser.error()` calls
        """
        for app in apps:
            if app.split('.')[0] not in self.app_names:
                parser.error("Invalid application %s" % app)

    def parse_options(self, argv):
        """Handle all command line arguments.

        Args:
            argv (str list): the list of command line arguments

        Returns:
            options, apps: parsed options, and list of application names
        """
        parser = self.prepare_parser()
        self.enhance_parser(parser)
        options, apps = parser.parse_args(argv)
        self.check_options(parser, options, apps)
        return options, apps

    def make_secret_key(self):
        """Generate a secret key."""
        # Shamelessly stolen from django.core.management.commands.startproject
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        return crypto.get_random_string(50, chars)

    def make_settings(self, options):
        """Prepare the settings from the given set of options.

        Args:
            options (optparse.OptionParser): parsed options

        Returns:
            settings (dict): the generated settings
        """

        secret_key = self.make_secret_key()

        settings = {
            'DATABASES': {
                'default': {
                    'ENGINE': DB_ENGINES.get(options.db_engine or self.DEFAULT_DB_ENGINE, options.db_engine),
                    'NAME': options.db_name or self.DEFAULT_DB_NAME,
                    'USER': options.db_user or self.DEFAULT_DB_USER,
                    'PASSWORD': options.db_password or self.DEFAULT_DB_PASSWORD,
                    'HOST': options.db_host or self.DEFAULT_DB_HOST,
                    'PORT': options.db_port or self.DEFAULT_DB_PORT,
                }
            },
            'LOGGING': {
                'version': 1,
                'formatters': {},
                'handlers': {
                    'console': {
                        'class': 'logging.StreamHandler',
                        'level': 'INFO',
                    },
                    'null': {
                        'class': 'django.utils.log.NullHandler',
                    },
                },
                'loggers': {},
                'root': {
                    'handlers': ['console' if options.log_to_stderr else 'null'],
                },
            },
            'SECRET_KEY': secret_key,
            'ROOT_URLCONF': self.URLCONF,
            'STATIC_URL': '/static/',
            'INSTALLED_APPS': self.TESTED_APPS + self.EXTRA_APPS,
        }

        for logger in options.disabled_loggers:
            settings['LOGGING']['loggers'][logger] = {
                'handlers': ['null'],
                'propagate': False,
            }

        settings.update(self.EXTRA_SETTINGS)
        return settings

    def _setup_tz(self, timezone):
        """Shamelessly stolen from django/conf/__init__.py:112"""
        # When we can, attempt to validate the timezone. If we can't find
        # this file, no check happens and it's harmless.
        zoneinfo_root = '/usr/share/zoneinfo'
        if (os.path.exists(zoneinfo_root) and not
                os.path.exists(os.path.join(zoneinfo_root, *(timezone.split('/'))))):
            raise ValueError("Incorrect timezone setting: %s" % timezone)
        # Move the time zone info into os.environ. See ticket #2315 for why
        # we don't do this unconditionally (breaks Windows).
        os.environ['TZ'] = timezone
        time.tzset()

    def _setup_logging(self, logging_config_handler, logging_config):
        """Shamelessly stolen from django/conf/__init__.py:125."""
        # First find the logging configuration function ...
        logging_config_path, logging_config_func_name = logging_config_handler.rsplit('.', 1)
        logging_config_module = importlib.import_module(logging_config_path)
        logging_config_func = getattr(logging_config_module, logging_config_func_name)

        # ... then invoke it with the logging settings
        logging_config_func(logging_config)

    def configure_settings(self, settings):
        """Configure the settings.

        Due to Django's bug https://code.djangoproject.com/ticket/18316, we need to
        replicate part of django.conf.Settings.
        """
        django_settings.configure(**settings)
        if django.VERSION[:2] >= (1, 4):
            self._setup_tz(django_settings.TIME_ZONE)

        if django_settings.LOGGING_CONFIG:
            self._setup_logging(django_settings.LOGGING_CONFIG, django_settings.LOGGING)

    def setup_test_environment(self, options):
        """Setup the test environment from the given options."""
        settings = self.make_settings(options)
        if self.BASE_PATH and not options.no_alter_path:
            self.info("Inserting %s on sys.path", self.BASE_PATH)
            sys.path.insert(0, os.path.abspath(self.BASE_PATH))
        self.configure_settings(settings)

    def get_runner(self, options):
        """Retrieve the test runner"""
        from django.test.simple import DjangoTestSuiteRunner

        if options.verbose:
            verbosity = 2
        elif options.quiet:
            verbosity = 0
        else:
            verbosity = 1
        return DjangoTestSuiteRunner(verbosity=verbosity, interactive=options.interactive, failfast=options.fail_fast)

    def run(self, argv):
        """Main entry point for the RunTests instance.

        This handles all logic:
            - Parse options
            - Setup test environment
            - Retrieve the TestRunner
            - Run the tests
        """
        options, apps = self.parse_options(argv)
        self.setup_test_environment(options)
        runner = self.get_runner(options)
        apps_to_tests = sorted(apps or self.app_names)
        self.info("Running tests for %s", ', '.join(apps_to_tests))
        return runner.run_tests(apps_to_tests)


    @classmethod
    def runtests(cls, argv=()):
        """Run the tests with a given argv."""
        runner = cls()
        return runner.run(argv or [])

    @classmethod
    def main(cls):
        """Main entry point, to use from a shell."""
        failures = cls.runtests(sys.argv[1:])
        if failures:
            sys.exit(1)
