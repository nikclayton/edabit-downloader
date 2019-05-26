import click
import json
from pathlib import Path
import tomd
from slugify import slugify
from pyjsparser import PyJsParser
from tqdm import tqdm


@click.command()
@click.option('--json_dir', default='apify_storage/datasets/default',
              help='Path to read JSON files from',
              type=click.Path(exists=True, resolve_path=True, file_okay=False))
@click.option('--exercise_dir', default='../edabit-javascript-challenges',
              help='Path to write exercises to',
              type=click.Path(exists=False, resolve_path=True, file_okay=False))
@click.option('--golden_file', default=None, help='File to save golden data',
              type=click.File(mode='w'))
def main(json_dir, exercise_dir, golden_file):
    filenames = Path(json_dir).glob('*.json')
    exercise_path = Path(exercise_dir)
    exercise_path.mkdir(exist_ok=True)

    t = tqdm(unit='files')
    code_problems = []
    test_problems = []
    goldens = []

    for filename in filenames:
        with open(filename, 'rb') as json_file:
            j = json.load(json_file)

            slug_difficulty = slugify(j['difficulty'])
            slug_title = slugify(j['title'])
            t.set_postfix(file=slug_title)
            t.update(1)

            try:
                new_code = fixup_function(j['code'])
            except ParseError as err:
                tqdm.write('Problem parsing the code for this exercise, skipping')
                code_problems.append('{}/{}'.format(slug_difficulty, slug_title))
                continue

            try:
                new_tests = fixup_tests(j['tests'])
            except (FixupError, ParseError) as err:
                tqdm.write('Problem parsing the test for this exercise, skipping')
                test_problems.append('{}/{}'.format(slug_difficulty, slug_title))
                continue

            exercise_dir = exercise_path / slug_difficulty / slug_title
            exercise_dir.mkdir(parents=True, exist_ok=True)

            with open(exercise_dir / 'README.md', 'wb') as markdown:
                markdown.write(str.encode(tomd.convert(j['instructions'])))
            with open(exercise_dir / 'code.js', 'wb') as code:
                code.write(str.encode(new_code))
            with open(exercise_dir / 'code.spec.js', 'wb') as tests:
                tests.write(str.encode(new_tests))
            with open(exercise_dir / 'package.json', 'wb') as package:
                package.write(str.encode(create_package_dot_json_contents(slug_title)))
            with open(exercise_dir / 'challenge.json', 'w') as challenge:
                json.dump(j, challenge, sort_keys=True, indent=2)

            goldens.append({
                'original_code': j['code'],
                'new_code': new_code,
                'original_tests': j['tests'],
                'new_tests': new_tests
            })

    t.close()

    if golden_file:
        json.dump(goldens, golden_file, indent=2)

    print('{} code problems'.format(len(code_problems)))
    for problem in code_problems:
        print('  {}'.format(problem))
    print()
    print('{} test problems'.format(len(test_problems)))
    for problem in test_problems:
        print('  {}'.format(problem))


def fixup_function(text):
    p = PyJsParser()
    try:
        ast = p.parse(text)
    except NotImplementedError as err:
        # PyJsParser can't pass class definitions
        raise ParseError(err)
    except Exception as err:
        # Shouldn't be necessary, but PyJsParser has bugs.
        # TODO(nik): Come back here, remove this, track down the problems and fix them.
        raise ParseError(err)

    function_name = None

    # function hello() { ... }
    if ast['body'][0]['type'] == 'FunctionDeclaration':
        function_name = ast['body'][0]['id']['name']
        params = [param['name'] for param in ast['body'][0]['params']]

    # var recursivSum = function(n) { ... }
    if ast['body'][0]['type'] == 'VariableDeclaration':
        function_name = ast['body'][0]['declarations'][0]['id']['name']
        params = [param['name'] for param in ast['body'][0]['declarations'][0]['init']['params']]

    if not function_name:
        raise ParseError('Could not parse function name')

    return """function {0}({1}) {{
  // Your code here.
}}

module.exports = {0};
""".format(function_name, ', '.join(params))


class ParseError(Exception):
    pass


def fixup_tests(text):
    p = PyJsParser()
    try:
        ast = p.parse(text)
    except Exception as err:
        raise ParseError(err)

    tests_with_names = []
    tests_without_names = []

    expected_function = None

    for statement in ast['body']:
        if statement['type'] == 'EmptyStatement':
            continue
        if statement['type'] == 'VariableDeclaration':
            # This is a complex test with local state. Bail on trying to
            # parse it.
            raise ParseError

        if statement['type'] == 'FunctionDeclaration':
            # This is a test with embedded helper functions. Bail on trying to
            # parse it at the moment.
            raise ParseError

        expression = statement['expression']
        if expression['type'] != 'CallExpression':
            continue

        if expression['callee']['object']['name'] != 'Test':
            continue

        # The test_method is a string like 'assertEquals', etc
        test_method = expression['callee']['property']['name']
        if test_method in ['assertEquals', 'assertSimilar', 'assertNotEquals']:
            fixed_test = fixup_Test_assertEquals(expression, invert=test_method == 'assertNotEquals')
            if fixed_test[1]:
                tests_with_names.append({'code': fixed_test[0], 'name': fixed_test[1]})
            else:
                tests_without_names.append(fixed_test[0])
            # Most tests have the name of the function to call as the first
            # parameter, but not all.
            if 'callee' in expression['arguments'][0]:
                expected_function = expression['arguments'][0]['callee']['name']
            else:
                expected_function = expression['arguments'][1]['callee']['name']
            continue

        raise Exception('Unknown Test method called, Test.{}'.format(test_method))

    def format_named_test(test):
        return """test({}, () => {{
        {}
    }});""".format(test['name'], test['code'])

    def format_unnamed_tests(tests):
        return """test('the tests', () => {{
        {}
    }});""".format('\n        '.join(tests))

    # Shouldn't happen -- if it does then we've failed to convert a test.
    if len(tests_with_names) == 0 and len(tests_without_names) == 0:
        raise Exception('No tests created! Test parsing is broken')

    # TODO(nik): This (and the function definition style) should be based
    # on a command line flag -- see the related commented out code where
    # the function template is emitted.
    return """const {0} = require('./code');

describe('Tests', () => {{
    {1}
    
    {2}
}});
""".format(expected_function,
           '\n\n'.join([format_named_test(test) for test in tests_with_names]),
           format_unnamed_tests(tests_without_names))


def fixup_Test_assertEquals(expression, invert=False):
    """Fix an expression of the form

Test.assertEquals(actual, expected, [optional name])

to

expect(actual).toEqual(expected);

Returns a tuple of two values. The first is the text of the test to run, the
second (which may be None) is the name of the test.

If invert is True then '.not' is inserted to invert the sense of the test.
"""
    arguments = expression['arguments']
    actual = fixup_Argument(arguments[0])
    # Some tests don't bother with an 'expected' parameter if the result
    # expected is 'undefined'. So put one in.
    if len(arguments) == 1:
        expected = 'undefined'
    else:
        expected = fixup_Argument(arguments[1])
    name = None
    if len(arguments) == 3:
        name = fixup_Argument(arguments[2])

    return ('expect({0}){2}.toEqual({1});'.format(actual, expected,
                                                  '.not' if invert else ''), name)


class FixupError(Exception):
    pass


def fixup_Argument(argument):
    """Convert arguments in the AST back to Javascript strings."""
    if argument['type'] == 'CallExpression':
        if 'name' not in argument['callee']:
            raise FixupError
        callee_name = argument['callee']['name']
        args = [fixup_Argument(arg) for arg in argument['arguments']]

        return '{}({})'.format(callee_name, ', '.join(args))

    if argument['type'] == 'Literal':
        val = argument['value']
        if isinstance(val, str):
            return "'{}'".format(val.replace("'", "\\\'"))

        val_as_str = str(val)
        if val_as_str.endswith('.0'):
            val_as_str = val_as_str[0:-2]

        # Convert from Python types in the AST back to Javascript types.
        type_map = {
            'None': 'undefined',
            'True': 'true',
            'False': 'false'
        }

        if val_as_str in type_map:
            val_as_str = type_map[val_as_str]
        return val_as_str

    # Unary expression, like '-9'
    if argument['type'] == 'UnaryExpression':
        fmt_str = '{0}{1}'
        if not argument['prefix']:
            fmt_str = '{1}{0}'
        return fmt_str.format(argument['operator'], fixup_Argument(argument['argument']))

    if argument['type'] == 'ArrayExpression':
        els = [fixup_Argument(el) for el in argument['elements']]
        return '[{}]'.format(', '.join(els))

    # E.g., 'undefined'
    if argument['type'] == 'Identifier':
        return argument['name']

    if argument['type'] == 'ObjectExpression':
        if len(argument['properties']) == 0:
            return '{}'
        props = {}
        for property in argument['properties']:
            if property['key']['type'] == 'Identifier':
                key = property['key']['name']
            if property['key']['type'] == 'Literal':
                key = fixup_Argument(property['key'])
            value = fixup_Argument(property['value'])
            props[key] = value
        return '{{{}}}'.format(', '.join(['{}: {}'.format(key, value) for key, value in props.items()]))

    # e.g., "new Date(...., .., ..)"
    # Very similar to the code for CallExpression
    if argument['type'] == 'NewExpression':
        callee_name = argument['callee']['name']
        args = [fixup_Argument(arg) for arg in argument['arguments']]
        return 'new {}({})'.format(callee_name, ', '.join(args))

    if argument['type'] == 'FunctionExpression':
        raise ParseError('Can not pass function expressions yet.')

    # A backtick template: `some text with ${var} interpolations`
    if argument['type'] == 'TemplateLiteral':
        if len(argument['quasis']) == 1:
            return '`{}`'.format(argument['quasis'][0]['value']['raw'])

    raise UnknownArgumentException(repr(argument))


class UnknownArgumentException(Exception):
    pass


def create_package_dot_json_contents(name):
    return """{{
  "name": "edabit-javascript-{}",
  "version": "0.0.0",
  "description": "Edabit exercises in Javascript.",
  "private": true,
  "repository": {{
    "type": "git",
    "url": "https://github.com/nikclayton/edabit-javascript-challenges.git"
  }},
  "devDependencies": {{
    "@babel/core": "^7.3.3",
    "@babel/preset-env": "^7.3.1",
    "babel-jest": "^24.1.0",
    "jest": "^24.1.0"
  }},
  "jest": {{
    "modulePathIgnorePatterns": [
      "package.json"
    ]
  }},
  "babel": {{
    "presets": [
      "@babel/preset-env"
    ]
  }},
  "scripts": {{
    "test": "jest --no-cache ./*",
    "watch": "jest --no-cache --watch ./*"
  }},
  "license": "MIT",
  "dependencies": {{}}
}}
""".format(name)


if __name__ == '__main__':
    main()
