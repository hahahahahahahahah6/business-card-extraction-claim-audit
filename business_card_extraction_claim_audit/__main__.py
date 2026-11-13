"""Command line interface."""
import argparse
import json
import sys
from . import __version__
from .audit import audit


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, 'error: ' + message + '\n')


def main(argv=None):
    parser = Parser(description='Offline documentation claim auditor')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    command = commands.add_parser('audit')
    command.add_argument('repo', nargs='?', default='.')
    command.add_argument('--json', action='store_true')
    command.add_argument('--verbose', action='store_true')
    command.add_argument('--ignore', action='append', default=[])
    command.add_argument('--fail-on', choices=('high', 'medium'), default='high')
    args = parser.parse_args(argv)
    try:
        result = audit(args.repo, args.ignore)
    except (OSError, UnicodeError) as error:
        print('error: ' + str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result['verdict'])
        for finding in result['findings']:
            print('{severity} {id}: {message}'.format(**finding))
        if args.verbose:
            print('Production evidence: ' + ', '.join(result['production_evidence']))
            print('Test evidence: ' + ', '.join(result['test_evidence']))
    return 2 if any(f['severity'] == 'HIGH' or args.fail_on == 'medium' for f in result['findings']) else 0


if __name__ == '__main__':
    sys.exit(main())
