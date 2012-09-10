# coding: utf-8
# Copyright (c) 2012 Raphaël Barrois
# Distributed under the MIT license


from __future__ import unicode_literals

import sys

from django.core.management.commands import test as django_test


class RunTests(django_test.Command):

    def should_test_app(self, app):
        """Whether an application should be tested."""
        return not app.startswith('django.')

    def get_testable_apps(self):
        """Retrieve the list of applications to test.

        Called if the list of tests to run is empty, in order to avoid
        testing all "INSTALLED_APPS".
        """
        from django.conf import settings
        all_apps = sorted(settings.INSTALLED_APPS)
        all_apps = [app for app in all_apps if self.should_test_app(app)]
        return [app.split('.')[-1] for app in all_apps]

    def handle(self, *apps, **options):
        if not apps:
            apps = self.get_testable_apps()
            if options.get('verbosity', 1) >= 1:
                self.stdout.write("Running tests for %s\n" % ', '.join(apps))

        return super(RunTests, self).handle(*apps, **options)

    @classmethod
    def runtests(cls, argv=()):
        """Run the tests with a given argv."""
        argv = argv or [__name__]
        argv = [argv[0], 'test'] + list(argv[1:])
        command = cls()
        return command.run_from_argv(argv)

    @classmethod
    def main(cls):
        """Main entry point, to use from a shell."""
        cls.runtests(sys.argv)
