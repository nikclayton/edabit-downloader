# README

This code downloads a local copy of the Edabit coding challenges and can
convert the tests to standard Javascript unit tests.

This makes it possible to try the exercises offline, run the tests with
"npm test", save the results in a local version control repository, etc.

According to the Edabit terms of service (https://edabit.com/docs/terms),
forking and editing content is allowed:

> In submitting Content, including authored challenges, you agree to
> allow others to view, fork and edit your Content.

At the moment the conversion process involves two steps.

The first step (Javascript, using Apify) downloads a JSON representation
of the content.

The second step (Python) converts this representation to Javascript.

Edabit unit tests appear to use their own testing framework, the conversion
process re-writes the tests to use the Jest framework.

## Installation

Install Javascript dependencies with:

```shell
npm install
```

## Fetch content

Download challenges from Edabit by running:

```shell
apify run
```

Pass the `-p` flag to delete locally stored content.

This generates JSON files in `apify_storage/datasets/default`.

## Process content

To convert the downloaded JSON files to Javascript code and tests
run

```shell
main.py
```

## Exercises that don't work

Not all exercises are currently converted. Some have tests that
are too complex -- for example, dedicated setup or teardown functions,
or use Javascript syntax I haven't covered in the Python code yet. 

## Future work

Replace the Python process with something using Acorn and Astring
(https://www.npmjs.com/package/astring).

